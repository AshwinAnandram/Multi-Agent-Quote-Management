BEGIN;

ALTER TABLE public.sales_reps
    ADD COLUMN IF NOT EXISTS email VARCHAR(320);

ALTER TABLE public.bids
    ADD COLUMN IF NOT EXISTS lost_reason TEXT,
    ADD COLUMN IF NOT EXISTS outcome_missing_fields TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    ADD COLUMN IF NOT EXISTS outcome_source_message_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS ux_bids_outcome_source_message_id
    ON public.bids (outcome_source_message_id)
    WHERE outcome_source_message_id IS NOT NULL;

COMMIT;
