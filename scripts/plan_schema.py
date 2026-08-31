"""
The structured intermediate query-plan schema. Every SFT target is `plan
JSON` followed by the compiled `SQL` in one continuous completion, not raw
SQL alone: the model first states what it thinks the question is asking for
in this structured form, then compiles that plan into the actual query. RL
resumes training from this same combined completion and rewards only the
compiled SQL's execution correctness + efficiency -- giving RL an actual
reasoning trace to refine, unlike flat single-shot SQL generation (see
PAPER.md, Section 1).

Every archetype in archetypes.py (and operational/regulatory/quality_kpi
archetypes) gets a `plan` template alongside its existing `sql` template,
instantiated together from the same concept parameters -- exactly parallel
to how `sql` is a format string today. Both are generated, verified, and
shipped together: the plan is not free-form model output during data
generation, it's as deterministic and execute-verified an artifact as the
SQL always has been (the plan's `aggregation`/`constraints` shape is fixed
per archetype; only `entities[].concept` varies per instantiation).

---

## Top-level shape

    {
        "entities": [ <Entity>, ... ],
        "joins": [ <Join>, ... ],                # may be empty
        "constraints": [ <Constraint>, ... ],    # may be empty
        "aggregation": <Aggregation>,
        "abstain": false
    }

Abstention rows (question genuinely unanswerable from this schema) use:

    {"abstain": true}

with no other keys -- the compiled "SQL" for an abstention row is the fixed
`UNANSWERABLE` token, exactly as in the flat SQL-only design.

## Entity

    {
        "role": "primary" | "companion",
        "concept": "<display text, or a fixed companion string>",
        "domain": "<source table: condition | procedure | medication_request |
                    observation | immunization | allergy | diagnostic_report |
                    encounter | patient>",
        "terminology_lookup": true | false
    }

`role: "primary"` entities are the concept(s) the *question* is actually
about -- their `concept` string is drawn from the current instantiation's
`{display}` (or an equivalent question-derived phrase for a back-translated
paraphrase). `role: "companion"` entities are a fixed second clinical anchor
some tier-3/4 archetypes join against (hypertension, lisinopril, colonoscopy,
anemia, body weight) -- same fixed string in every instance of that
archetype, never varied per-instantiation, never what the question asks
about (see archetypes.py's existing companion design note).
`terminology_lookup: true` means this entity's `concept` string must be
resolved against `valuesets` via a lookup CTE at compile time -- true for
every `entities[]` member in this schema, since a concept entity by
definition has no literal code to fall back on (kept as an explicit field
rather than assumed, so a future archetype needing an already-coded entity
isn't a schema-breaking change). Structural table touches that need no
terminology resolution at all (joining to `patient` for `gender`, to
`encounter` for its `type`/`class`) are *not* modeled as entities -- see
Join below.

## Join

    {"table": "patient" | "encounter" | "observation" | "procedure" |
              "medication_request",
     "field": "<column this join exists to expose, e.g. 'gender', 'birthDate',
               'type_code', 'class_code'>",
     "purpose": "group_by" | "filter" | "output_column"}

A structural join to a table that isn't a lookup-resolved concept entity --
exists purely to expose a field the aggregation or a constraint needs
(patient demographics, encounter type/class, or a companion table's own
non-coded column). Distinct from `entities[]` specifically so "which tables
does this query touch and why" (this field) stays separable from "which
concepts does this query need to resolve via terminology lookup" (that
field) -- two different questions the plan should let a reader (or a later
diagnostic) answer independently.

## Constraint

One of:

    {"type": "status", "field": "clinicalStatus" | "status" | "criticality",
     "value": "<literal>"}
        -- an equality filter on a non-coded status/criticality field.

    {"type": "existence", "field": "<column>", "negate": false}
        -- an IS NOT NULL check (e.g. abatementDateTime recorded at all).

    {"type": "threshold", "field": "valueQuantity", "comparison": ">",
     "value": "{threshold}"}
        -- a numeric comparison; {threshold} is filled in the same way the
        existing SQL templates already compute it (a concept-specific
        percentile, precomputed per-instantiation).

    {"type": "age", "comparison": ">=", "value": 65}
        -- a patient-age-at-event comparison.

    {"type": "temporal_window", "relation": "within", "value": 90,
     "unit": "days", "anchor": "<what this is relative to, e.g.
     'condition_onset_to_companion_procedure'>"}
        -- a bounded time window between two dated events.

    {"type": "recency", "relation": "within_last", "value": 30, "unit": "days"}
        -- a bounded window relative to the corpus's frozen reference date
        (used by the regulatory "recent narcotic patients" archetype).

    {"type": "having", "field": "count", "comparison": ">=", "value": 3}
        -- a post-aggregation filter (SQL `HAVING`), distinct from the other
        constraint types above which all compile to `WHERE`.

    {"type": "point_in_time", "field": "<interval-start/end column pair>",
     "date": "2025-01-15"}
        -- a fixed-date "still open at this point" filter (start <= date AND
        (end IS NULL OR end >= date)); used by the one operational archetype
        with a frozen reference date baked in, not concept-derived.

## Aggregation

    {
        "type": "count" | "count_distinct_patient" | "list_distinct_patient" |
                "avg" | "count_and_avg" | "avg_per_patient" |
                "avg_age_at_event" | "avg_days_between_events" | "top_n" |
                "top_n_by_value" | "window_first_vs_last" |
                "window_most_recent" | "yearly_trend_delta",
        "group_by": null | "year:<date_column>" | "gender" | "race" |
                    "ethnicity" | "state" | "status" | "criticality" |
                    "encounter_type" | "encounter_class" | "unit" |
                    "patient_id" | "participant_name" | "requester_name" |
                    "month:<date_column>",
        "order_by": null | "count_desc" | "value_desc" | "chronological",
        "limit": null | <int>,
        "per_patient_metric": null | "procedure_count" | "encounter_count",
                              # only set when type == "avg_per_patient":
                              # what's being counted per patient before
                              # averaging across patients (a subquery in the
                              # compiled SQL, not a plain GROUP BY)
        "anchor": null | "<description of which two dated events this spans>"
                              # only set when type == "avg_days_between_events"
                              # (e.g. "condition_onset_to_companion_first_rx")
    }

Grouping is orthogonal to the aggregation `type` (e.g. `"count"` with
`group_by: "status"` is a grouped count; `"count"` with `group_by: null` is
a single scalar) rather than a separate `*_grouped` type, so the vocabulary
doesn't double for every type that can optionally be grouped. `"top_n"`
groups by whatever concept/patient is being ranked and orders by its count
(the 40 archetypes' actual top-N shapes are always "N patients by count of
X"); `"top_n_by_value"` ranks by a computed per-row value instead of a count
(used once, for oldest-first-diagnosis-age). `"count_and_avg"` is for the
single archetype that reports both an ungrouped count and an ungrouped
average side by side in one row (high-value-reading count + their average).

This is a closed, enumerable vocabulary by design -- not because the real
space of possible aggregations is small, but because every value in it maps
1:1 to a concrete clause shape already present in some archetype's existing
`sql` template. Extending to a new archetype shape means extending this
vocabulary deliberately (and updating this docstring), not letting the model
invent new categories freely.

---

## Example (tier-1, matches PAPER.md's example shape)

Archetype `t1_list_patients_with_procedure`, concept "Biopsy of breast
(procedure)":

    {
        "entities": [
            {"role": "primary", "concept": "Biopsy of breast (procedure)",
             "domain": "procedure", "terminology_lookup": true}
        ],
        "joins": [],
        "constraints": [
            {"type": "status", "field": "status", "value": "completed"}
        ],
        "aggregation": {"type": "list_distinct_patient", "group_by": null,
                         "order_by": null, "limit": null, "per_patient_metric": null},
        "abstain": false
    }

## Example with a join and a companion (tier-3)

Archetype `t3_condition_by_gender`, concept "Essential hypertension
(disorder)":

    {
        "entities": [
            {"role": "primary", "concept": "Essential hypertension (disorder)",
             "domain": "condition", "terminology_lookup": true}
        ],
        "joins": [
            {"table": "patient", "field": "gender", "purpose": "group_by"}
        ],
        "constraints": [],
        "aggregation": {"type": "count_distinct_patient", "group_by": "gender",
                         "order_by": null, "limit": null, "per_patient_metric": null},
        "abstain": false
    }

compiled SQL:

    WITH resolved AS (
        SELECT code, code_system FROM valuesets
        WHERE table_name = 'condition' AND display ILIKE '%Essential hypertension (disorder)%'
    )
    SELECT p.gender, COUNT(DISTINCT c.patient_id) AS patient_count
    FROM condition c
    JOIN patient p ON c.patient_id = p.id
    JOIN resolved r ON c.code = r.code AND c.system = r.code_system
    GROUP BY p.gender
"""
