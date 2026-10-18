-- Failures reported by the n8n error workflow (one row per failed execution).
-- Columns follow the Error Trigger output; execution fields can be absent
-- when the error comes from the workflow's own trigger, so they are nullable.
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.pipeline_error (
    error_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    logged_at     timestamptz NOT NULL DEFAULT now(),
    workflow_id   text,
    workflow_name text,
    execution_id  text,
    execution_url text,
    last_node     text,
    error_message text,
    mode          text
);
