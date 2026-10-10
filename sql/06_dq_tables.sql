CREATE SCHEMA IF NOT EXISTS dq;

-- Rule catalogue: one row per rule and version (loaded from the STTM)
CREATE TABLE IF NOT EXISTS dq.dq_rule (
    rule_id            text    NOT NULL,
    rule_version       integer NOT NULL DEFAULT 1,
    dimension          text    NOT NULL,
    severity           text    NOT NULL CHECK (severity IN ('critical','important','optional')),
    check_description  text    NOT NULL,
    fix_type           text    NOT NULL CHECK (fix_type IN ('ai','lookup','human','none')),
    counts_against_score boolean NOT NULL DEFAULT true,
    PRIMARY KEY (rule_id, rule_version)
);

-- Failure log: one row per product, rule, rule version and source file
CREATE TABLE IF NOT EXISTS dq.dq_failure (
    failure_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    barcode       text        NOT NULL,
    rule_id       text        NOT NULL,
    rule_version  integer     NOT NULL,
    source_file   text        NOT NULL,
    field         text,
    evidence      jsonb,
    reason        text        NOT NULL,
    detected_at   timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (rule_id, rule_version) REFERENCES dq.dq_rule (rule_id, rule_version),
    UNIQUE (barcode, rule_id, rule_version, source_file)
);
