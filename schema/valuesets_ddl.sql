-- Terminology lookup table -- ABLATION FRAGMENT, NOT PART OF THE FROZEN SCHEMA.
--
-- IMPORTANT: this block was NOT present in schema/schema.sql during the published
-- training and evaluation runs. The `valuesets` table existed in both DuckDB
-- databases and every gold query resolved terminology through it, but its DDL was
-- never shown to the model -- fine-tuned models learned its columns implicitly from
-- thousands of training targets, while the frozen baseline had only the table name
-- to go on.
--
-- valuesets_ablation.ipynb prepends this fragment to schema.sql and re-runs the
-- held-out evaluation on the published checkpoints, to measure how much of the
-- frozen model's failure is attributable to the missing table description rather
-- than to reasoning ability. See PAPER.md Section 5.6.
--
-- Do NOT merge this into schema.sql: doing so would break correspondence between
-- the committed schema and the runs reported in the paper.

CREATE TABLE valuesets (
    table_name            VARCHAR,     -- which fact table this concept belongs to
    code                  VARCHAR,
    code_system           VARCHAR,     -- joins against that table's `system`-suffixed column
    display               VARCHAR,     -- human-readable concept name; the ILIKE search target
    lookup_ambiguous      BOOLEAN      -- display text matches >1 row in the same table under ILIKE containment
);
