BEGIN;

ALTER TABLE public.rfqs
    ADD COLUMN IF NOT EXISTS rejection_reason TEXT;

UPDATE public.rfqs
SET rejection_reason = extracted_json #>> '{review_decision,reason}'
WHERE processing_status = 'REJECTED'
  AND rejection_reason IS NULL
  AND extracted_json #>> '{review_decision,reason}' IS NOT NULL;

COMMIT;
