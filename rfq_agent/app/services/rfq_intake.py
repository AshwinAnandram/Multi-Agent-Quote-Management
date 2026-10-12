"""Prepare provider-neutral emails for On Hold RFQ review."""

from typing import Any

from app.models.inbound_email import InboundEmail
from app.services.document_parser import (
    AttachmentParseError,
    extract_attachment_text,
)


def extract_inbound_email(
    email: InboundEmail,
    extraction_agent: Any,
) -> dict:
    """Extract each source independently and report any field conflicts."""
    sources: list[dict] = []
    attachment_details: list[dict] = []
    issues: list[dict] = []
    email_text = "\n".join(
        part for part in (
            f"Subject: {email.subject}" if email.subject else "",
            f"From: {email.sender}" if email.sender else "",
            email.body,
        ) if part
    ).strip()

    if email_text:
        source = _extract_source("email", email_text, extraction_agent)
        sources.append(source)
        if source["status"] != "EXTRACTED":
            issues.append({
                "source": "email",
                "code": "SOURCE_EXTRACTION_FAILED",
                "message": source["error"],
            })
    else:
        issues.append({
            "source": "email",
            "code": "EMPTY_EMAIL",
            "message": "The email has no readable subject or body.",
        })

    for attachment in email.attachments:
        detail = {
            "filename": attachment.filename,
            "mime_type": attachment.mime_type,
        }
        try:
            text = extract_attachment_text(
                filename=attachment.filename,
                content=attachment.content,
                mime_type=attachment.mime_type,
            )
            detail["status"] = "EXTRACTED"
            detail["extracted_text"] = text
            source = _extract_source(
                f"attachment:{attachment.filename}",
                text,
                extraction_agent,
            )
            sources.append(source)
            if source["status"] != "EXTRACTED":
                issues.append({
                    "source": source["name"],
                    "code": "SOURCE_EXTRACTION_FAILED",
                    "message": source["error"],
                })
        except AttachmentParseError as error:
            detail["status"] = "NEEDS_REVIEW"
            detail["error"] = str(error)
            issues.append({
                "source": f"attachment:{attachment.filename}",
                "code": "ATTACHMENT_UNREADABLE",
                "message": str(error),
            })
        attachment_details.append(detail)

    extracted_sources = [source for source in sources if source["data"] is not None]
    merged, conflicts = _merge_sources(extracted_sources)
    if not merged:
        merged = {
            "customer": {"name": None, "email": None},
            "rfq": {},
            "bid_outcome": {
                "bid_id": None,
                "status": None,
                "final_quote_price": None,
                "lost_reason": None,
            },
            "line_items": [],
            "special_requirements": [],
        }

    missing_fields = _find_missing_fields(merged)
    review_reasons = []
    if conflicts:
        review_reasons.append("SOURCE_CONFLICT")
    if issues:
        review_reasons.append("SOURCE_EXTRACTION_ISSUE")
    if missing_fields:
        review_reasons.append("MISSING_REQUIRED_FIELDS")

    return {
        "version": 1,
        "merged": merged,
        "sources": sources,
        "attachments": attachment_details,
        "conflicts": conflicts,
        "issues": issues,
        "missing_fields": missing_fields,
        "review_reasons": review_reasons,
    }


def resolve_bid_outcome(intake: dict) -> dict | None:
    """Return a safe, matchable outcome only when ID and status are unambiguous."""
    merged = intake.get("merged") or {}
    outcome = merged.get("bid_outcome") or {}
    conflicts = {
        conflict.get("field")
        for conflict in intake.get("conflicts") or []
    }
    if any(field in conflicts for field in (
        "bid_outcome.bid_id",
        "bid_outcome.status",
    )):
        return None

    bid_id = outcome.get("bid_id")
    status = outcome.get("status")
    if not isinstance(bid_id, int) or status not in {"WON", "LOST"}:
        return None

    missing_fields = []
    final_quote_price = outcome.get("final_quote_price")
    lost_reason = outcome.get("lost_reason")
    if status == "WON":
        if "bid_outcome.final_quote_price" in conflicts or final_quote_price is None:
            missing_fields.append("final_quote_price")
            final_quote_price = None
        lost_reason = None
    else:
        if "bid_outcome.lost_reason" in conflicts or not str(lost_reason or "").strip():
            missing_fields.append("lost_reason")
            lost_reason = None
        final_quote_price = None

    return {
        "bid_id": bid_id,
        "status": status,
        "final_quote_price": final_quote_price,
        "lost_reason": str(lost_reason).strip() if lost_reason else None,
        "missing_fields": missing_fields,
    }


def _extract_source(name: str, text: str, extraction_agent: Any) -> dict:
    try:
        extracted = extraction_agent.extract(text)
        if hasattr(extracted, "model_dump"):
            data = extracted.model_dump(mode="json")
        else:
            data = dict(extracted)
        return {"name": name, "data": data, "status": "EXTRACTED"}
    except Exception as error:
        return {
            "name": name,
            "data": None,
            "status": "NEEDS_REVIEW",
            "error": str(error),
        }


def _merge_sources(sources: list[dict]) -> tuple[dict | None, list[dict]]:
    if not sources:
        return None, []

    merged = sources[0]["data"]
    merged = _copy_json(merged)
    source_for_path: dict[str, str] = {}
    _record_paths(merged, "", sources[0]["name"], source_for_path)
    conflicts: list[dict] = []

    for source in sources[1:]:
        _merge_value(
            merged,
            source["data"],
            "",
            source["name"],
            source_for_path,
            conflicts,
        )

    return merged, conflicts


def _merge_value(
    target: Any,
    incoming: Any,
    path: str,
    incoming_source: str,
    source_for_path: dict[str, str],
    conflicts: list[dict],
) -> Any:
    if isinstance(target, dict) and isinstance(incoming, dict):
        for key, value in incoming.items():
            child_path = f"{path}.{key}" if path else key
            if key not in target:
                target[key] = _copy_json(value)
                _record_paths(value, child_path, incoming_source, source_for_path)
            else:
                target[key] = _merge_value(
                    target[key],
                    value,
                    child_path,
                    incoming_source,
                    source_for_path,
                    conflicts,
                )
        return target

    if path.endswith("special_requirements") and isinstance(target, list) and isinstance(incoming, list):
        combined = list(target)
        for value in incoming:
            if value not in combined:
                combined.append(value)
        return combined

    if path.endswith("line_items") and isinstance(target, list) and isinstance(incoming, list):
        return _merge_line_items(
            target,
            incoming,
            path,
            incoming_source,
            source_for_path,
            conflicts,
        )

    if isinstance(target, list) and isinstance(incoming, list):
        return target if target else _copy_json(incoming)

    if _is_empty(target):
        if not _is_empty(incoming):
            source_for_path[path] = incoming_source
            return incoming
        return target

    if _is_empty(incoming) or _values_equal(target, incoming):
        return target

    conflicts.append({
        "field": path,
        "source_a": source_for_path.get(path, "unknown"),
        "value_a": target,
        "source_b": incoming_source,
        "value_b": incoming,
    })
    return target


def _merge_line_items(
    target: list,
    incoming: list,
    path: str,
    incoming_source: str,
    source_for_path: dict[str, str],
    conflicts: list[dict],
) -> list:
    merged = target
    by_name = {
        _normalize(item.get("product_name")): index
        for index, item in enumerate(merged)
        if isinstance(item, dict) and item.get("product_name")
    }
    for index, item in enumerate(incoming):
        if not isinstance(item, dict):
            continue
        name = _normalize(item.get("product_name"))
        match_index = by_name.get(name) if name else None
        if match_index is None:
            merged.append(_copy_json(item))
            new_path = f"{path}[{len(merged) - 1}]"
            _record_paths(item, new_path, incoming_source, source_for_path)
            if name:
                by_name[name] = len(merged) - 1
            continue

        _merge_value(
            merged[match_index],
            item,
            f"{path}[{match_index}]",
            incoming_source,
            source_for_path,
            conflicts,
        )
    return merged


def _find_missing_fields(extracted: dict) -> list[str]:
    # These remain executive-entered fields even when the source parsed cleanly.
    missing = ["sales_rep_id", "opening_quote_price"]
    if not extracted.get("customer", {}).get("name"):
        missing.append("customer.name")
    if not extracted.get("rfq", {}).get("subject"):
        missing.append("rfq.subject")
    line_items = extracted.get("line_items") or []
    if not line_items:
        missing.append("line_items")
    for index, item in enumerate(line_items):
        if not item.get("product_name"):
            missing.append(f"line_items[{index}].product_name")
        if item.get("quantity") is None:
            missing.append(f"line_items[{index}].quantity")
        missing.append(f"line_items[{index}].catalog_product_mapping")
    return missing


def _record_paths(value: Any, path: str, source: str, output: dict[str, str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            _record_paths(child, child_path, source, output)
    elif not _is_empty(value):
        output[path] = source


def _copy_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _copy_json(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_copy_json(child) for child in value]
    return value


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(left) == float(right)
    return left == right
