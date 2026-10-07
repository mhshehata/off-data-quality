CREATE SCHEMA IF NOT EXISTS raw_deltafiles;

CREATE TABLE raw_deltafiles.off_product (
    source_file     text    NOT NULL,
    line_number   integer   NOT NULL,
    record        jsonb     NOT NULL,
    load_time       timestamptz   NOT NULL DEFAULT now(),
    PRIMARY KEY (source_file, line_number)
);