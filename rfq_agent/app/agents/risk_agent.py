from pydantic import BaseModel
from openai import OpenAI

from app.agents.tools import risk_evidence_service


class RiskAssessment(BaseModel):
    assessment: str
    primary_concerns: list[str]


class RiskAgent:
    def __init__(
        self,
        client: OpenAI,
        deployment_name: str,
    ):
        self.client = client
        self.deployment_name = deployment_name

    def run(
        self,
        bid_id: int,
        proposed_quote_price: float | None = None,
    ) -> dict:

        evidence = risk_evidence_service.evaluate(
            bid_id=bid_id,
            proposed_quote_price=proposed_quote_price,
        )

        response = self.client.responses.parse(
            model=self.deployment_name,
            instructions=(
                "You are a sales deal risk analyst. "
                "Your role is to interpret authoritative risk evidence provided by the "
                "RiskEvidenceService and explain the risk profile of the proposed quote. "

                "The RiskEvidenceService is the sole authority for all risk classifications. "
                "Use the supplied margin risk, discount risk, win probability risk, "
                "deal-size risk band, and overall risk exactly as provided. "
                "Never recalculate, reinterpret, override, or change these classifications. "

                "Do not independently determine whether a numerical value is high, low, "
                "moderate, safe, or concerning. "
                "Do not infer business consequences, causes, commercial implications, "
                "or assumptions that are not explicitly supported by the evidence. "

                "Do not present the deal-size band as a risk classification or as a primary "
                "risk concern unless the evidence explicitly contains a deal-size risk classification."

                "When explaining a risk factor, state the supplied value and its "
                "authoritative risk classification. You may explain that the value falls "
                "within the applicable risk classification only when this relationship "
                "is directly supported by the supplied evidence. "

                "Do not make pricing recommendations. "
                "Do not recommend increasing or decreasing the quote. "
                "Do not recommend accepting, rejecting, or pursuing the deal. "
                "Recommendations belong to the Quoting Agent. "

                "Provide a concise assessment of the overall risk and identify the "
                "primary risk factors supported by the evidence."
            ),
            input=(
                "Analyze the following authoritative risk evidence "
                "for the bid.\n\n"
                f"{evidence}"
            ),
            text_format=RiskAssessment,
        )

        assessment = response.output_parsed

        return {
            "bid_id": bid_id,
            "overall_risk": evidence["overall_risk"],
            "assessment": assessment.assessment,
            "primary_concerns": assessment.primary_concerns,
            "evidence": evidence,
        }