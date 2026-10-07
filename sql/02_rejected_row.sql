CREATE SCHEMA IF NOT EXISTS raw_deltafiles;

CREATE TABLE IF NOT EXISTS raw_deltafiles.rejected_row (
    source_file  text         NOT NULL,
    line_number  integer      NOT NULL,
    raw_record   text         NOT NULL,
    reason       text         NOT NULL,
    load_time    timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (source_file, line_number)
);