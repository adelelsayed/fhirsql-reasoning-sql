"""
Archetype library: ~40 parameterized SQL query templates across tiers 1-4
(tier 5 / unanswerable is handled separately by synthesize_unanswerable.py).

Each archetype is instantiated against ONE concept at a time (an
"archetype x concept factory": ~40 archetypes x ~100 concepts x ~0.8 verified
survival rate =~ 3,200 verified artifacts).

Every archetype carries a `plan` template alongside `sql` -- see
plan_schema.py for the full schema and rationale. The SFT target is
`plan JSON` + compiled `sql` in one completion, not raw SQL alone. `sql`
uses the lookup-then-answer CTE pattern (`WITH resolved AS
(SELECT code, code_system FROM valuesets WHERE table_name = '...' AND
display ILIKE '%{display}%') ...`) rather than a hardcoded literal code --
the model never needs to memorize a code, only produce a plausible search
phrase, resolved deterministically by DuckDB at execution time. Concepts
flagged `lookup_ambiguous` in `valuesets` must be excluded by the
instantiation script, not force-resolved with `LIMIT 1`.

`sql` and `plan` are both Python format templates taking {display} (and, for
a few archetypes, {threshold} -- a concrete value precomputed per-concept by
the instantiation script, e.g. a percentile of that concept's observed
valueQuantity distribution). `sql`'s {display} must be pre-escaped for SQL
string-literal embedding by the caller; `plan`'s {display} must NOT be --
it's human-readable text inside a JSON value, not a SQL literal, so the two
need separately prepared inputs (see generate_gold_plan_sql.py).

Companion-concept archetypes (a fixed second clinical anchor: hypertension,
lisinopril, colonoscopy, anemia, body weight) resolve the companion via a
SECOND lookup CTE too, using EXACT display match (`display = '...'`), not
the primary concept's `ILIKE '%...%'` -- a companion is a fixed constant
reproduced identically in every instance of the archetype, not something the
model derives from a paraphrased question, so there's no paraphrase-
tolerance need, and exact match sidesteps a real ambiguity (lisinopril
10mg's ILIKE pattern also matches the lisinopril/HCTZ combo pill; exact
match resolves it uniquely). In `plan`, the companion is a second entity
with `role: "companion"`.

Column names match schema/schema.sql's FHIR-element-aligned naming: primary
key `id`, coding triple `code`/`system`/`display` (or a
FHIR-field-prefixed variant like `type_code`/`vaccineCode` where the source
field isn't literally called "code"), camelCase FHIR date/status fields
(onsetDateTime, clinicalStatus, effectiveDateTime, authoredOn, etc).

`source_table` says which table in data/profile/train/selected_concepts.csv
this archetype draws its concept parameter from.
`requires_numeric` (observation archetypes only) restricts to concepts where
valueQuantity is the primary value type, since some archetypes need a
numeric threshold.
"""

ARCHETYPES = [
    # ---------------- TIER 1: single table, single filter ----------------
    {
        "id": "t1_count_patients_with_condition",
        "tier": 1,
        "source_table": "condition",
        "description": "count of distinct patients who have a given condition",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "count_distinct_patient", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            )
            SELECT COUNT(DISTINCT patient_id) AS patient_count
            FROM condition, resolved
            WHERE condition.code = resolved.code AND condition.system = resolved.code_system
        """,
    },
    {
        "id": "t1_list_patients_on_medication",
        "tier": 1,
        "source_table": "medication_request",
        "description": "list of distinct patients currently prescribed a given medication",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "medication_request", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "status", "field": "status", "value": "active"},
            ],
            "aggregation": {"type": "list_distinct_patient", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'medication_request' AND display ILIKE '%{display}%'
            )
            SELECT DISTINCT patient_id
            FROM medication_request, resolved
            WHERE medication_request.code = resolved.code AND medication_request.system = resolved.code_system
              AND status = 'active'
        """,
    },
    {
        "id": "t1_count_patients_allergic",
        "tier": 1,
        "source_table": "allergy",
        "description": "count of distinct patients allergic to a given substance",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "allergy", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "count_distinct_patient", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'allergy' AND display ILIKE '%{display}%'
            )
            SELECT COUNT(DISTINCT patient_id) AS patient_count
            FROM allergy, resolved
            WHERE allergy.code = resolved.code AND allergy.system = resolved.code_system
        """,
    },
    {
        "id": "t1_count_immunizations_given",
        "tier": 1,
        "source_table": "immunization",
        "description": "count of administered doses of a given vaccine",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "immunization", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "status", "field": "status", "value": "completed"},
            ],
            "aggregation": {"type": "count", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'immunization' AND display ILIKE '%{display}%'
            )
            SELECT COUNT(*) AS dose_count
            FROM immunization, resolved
            WHERE immunization.vaccineCode = resolved.code AND immunization.vaccineCode_system = resolved.code_system
              AND status = 'completed'
        """,
    },
    {
        "id": "t1_list_patients_with_procedure",
        "tier": 1,
        "source_table": "procedure",
        "description": "list of distinct patients who had a given procedure performed",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "procedure", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "status", "field": "status", "value": "completed"},
            ],
            "aggregation": {"type": "list_distinct_patient", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'procedure' AND display ILIKE '%{display}%'
            )
            SELECT DISTINCT patient_id
            FROM procedure, resolved
            WHERE procedure.code = resolved.code AND procedure.system = resolved.code_system
              AND status = 'completed'
        """,
    },
    {
        "id": "t1_avg_observation_value",
        "tier": 1,
        "source_table": "observation",
        "requires_numeric": True,
        "description": "average recorded value of a given observation across all patients",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "observation", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "avg", "group_by": "unit", "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'observation' AND display ILIKE '%{display}%'
            )
            SELECT ROUND(AVG(valueQuantity), 4) AS avg_value, unit
            FROM observation, resolved
            WHERE observation.code = resolved.code AND observation.system = resolved.code_system
            GROUP BY unit
        """,
    },
    {
        "id": "t1_count_diagnostic_reports",
        "tier": 1,
        "source_table": "diagnostic_report",
        "description": "count of a given diagnostic report type issued",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "diagnostic_report", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "count", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'diagnostic_report' AND display ILIKE '%{display}%'
            )
            SELECT COUNT(*) AS report_count
            FROM diagnostic_report, resolved
            WHERE diagnostic_report.code = resolved.code AND diagnostic_report.system = resolved.code_system
        """,
    },
    {
        "id": "t1_count_encounters_of_type",
        "tier": 1,
        "source_table": "encounter",
        "description": "count of encounters of a given type",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "encounter", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "count", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'encounter' AND display ILIKE '%{display}%'
            )
            SELECT COUNT(*) AS encounter_count
            FROM encounter, resolved
            WHERE encounter.type_code = resolved.code AND encounter.type_system = resolved.code_system
        """,
    },

    # ---------------- TIER 2: single table, multi-filter/dates/grouping ----------------
    {
        "id": "t2_active_condition_count",
        "tier": 2,
        "source_table": "condition",
        "description": "count of distinct patients with a given condition currently marked active",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "status", "field": "clinicalStatus", "value": "active"},
            ],
            "aggregation": {"type": "count_distinct_patient", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            )
            SELECT COUNT(DISTINCT patient_id) AS patient_count
            FROM condition, resolved
            WHERE condition.code = resolved.code AND condition.system = resolved.code_system
              AND clinicalStatus = 'active'
        """,
    },
    {
        "id": "t2_resolved_condition_count",
        "tier": 2,
        "source_table": "condition",
        "description": "count of a given condition's diagnoses that have since resolved (abatement recorded)",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "abatementDateTime", "negate": False},
            ],
            "aggregation": {"type": "count", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            )
            SELECT COUNT(*) AS resolved_count
            FROM condition, resolved
            WHERE condition.code = resolved.code AND condition.system = resolved.code_system
              AND abatementDateTime IS NOT NULL
        """,
    },
    {
        "id": "t2_condition_diagnoses_by_year",
        "tier": 2,
        "source_table": "condition",
        "description": "count of new diagnoses of a given condition, grouped by year",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "onsetDateTime", "negate": False},
            ],
            "aggregation": {"type": "count", "group_by": "year:onsetDateTime", "order_by": "chronological", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            )
            SELECT EXTRACT(YEAR FROM onsetDateTime) AS diagnosis_year, COUNT(*) AS diagnosis_count
            FROM condition, resolved
            WHERE condition.code = resolved.code AND condition.system = resolved.code_system
              AND onsetDateTime IS NOT NULL
            GROUP BY diagnosis_year
            ORDER BY diagnosis_year
        """,
    },
    {
        "id": "t2_medication_status_breakdown",
        "tier": 2,
        "source_table": "medication_request",
        "description": "count of a given medication's prescriptions broken down by status",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "medication_request", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "count", "group_by": "status", "order_by": "count_desc", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'medication_request' AND display ILIKE '%{display}%'
            )
            SELECT status, COUNT(*) AS request_count
            FROM medication_request, resolved
            WHERE medication_request.code = resolved.code AND medication_request.system = resolved.code_system
            GROUP BY status
            ORDER BY request_count DESC
        """,
    },
    {
        "id": "t2_medication_by_year",
        "tier": 2,
        "source_table": "medication_request",
        "description": "count of prescriptions for a given medication issued per year",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "medication_request", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "authoredOn", "negate": False},
            ],
            "aggregation": {"type": "count", "group_by": "year:authoredOn", "order_by": "chronological", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'medication_request' AND display ILIKE '%{display}%'
            )
            SELECT EXTRACT(YEAR FROM authoredOn) AS rx_year, COUNT(*) AS rx_count
            FROM medication_request, resolved
            WHERE medication_request.code = resolved.code AND medication_request.system = resolved.code_system
              AND authoredOn IS NOT NULL
            GROUP BY rx_year
            ORDER BY rx_year
        """,
    },
    {
        "id": "t2_observation_high_values",
        "tier": 2,
        "source_table": "observation",
        "requires_numeric": True,
        "description": "count and average of a given observation's readings above a clinically notable threshold",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "observation", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "threshold", "field": "valueQuantity", "comparison": ">", "value": "{threshold}"},
            ],
            "aggregation": {"type": "count_and_avg", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'observation' AND display ILIKE '%{display}%'
            )
            SELECT COUNT(*) AS high_reading_count, ROUND(AVG(observation.valueQuantity), 4) AS avg_high_value
            FROM observation, resolved
            WHERE observation.code = resolved.code AND observation.system = resolved.code_system
              AND observation.valueQuantity > {threshold}
        """,
    },
    {
        "id": "t2_observation_by_year",
        "tier": 2,
        "source_table": "observation",
        "requires_numeric": True,
        "description": "average value of a given observation grouped by year recorded",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "observation", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "effectiveDateTime", "negate": False},
            ],
            "aggregation": {"type": "avg", "group_by": "year:effectiveDateTime", "order_by": "chronological", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'observation' AND display ILIKE '%{display}%'
            )
            SELECT EXTRACT(YEAR FROM effectiveDateTime) AS obs_year, ROUND(AVG(observation.valueQuantity), 4) AS avg_value
            FROM observation, resolved
            WHERE observation.code = resolved.code AND observation.system = resolved.code_system
              AND effectiveDateTime IS NOT NULL
            GROUP BY obs_year
            ORDER BY obs_year
        """,
    },
    {
        "id": "t2_procedure_by_year",
        "tier": 2,
        "source_table": "procedure",
        "description": "count of a given procedure performed per year",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "procedure", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "performedDateTime", "negate": False},
            ],
            "aggregation": {"type": "count", "group_by": "year:performedDateTime", "order_by": "chronological", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'procedure' AND display ILIKE '%{display}%'
            )
            SELECT EXTRACT(YEAR FROM performedDateTime) AS proc_year, COUNT(*) AS proc_count
            FROM procedure, resolved
            WHERE procedure.code = resolved.code AND procedure.system = resolved.code_system
              AND performedDateTime IS NOT NULL
            GROUP BY proc_year
            ORDER BY proc_year
        """,
    },
    {
        "id": "t2_allergy_criticality_breakdown",
        "tier": 2,
        "source_table": "allergy",
        "description": "count of patients allergic to a given substance broken down by criticality",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "allergy", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "count_distinct_patient", "group_by": "criticality", "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'allergy' AND display ILIKE '%{display}%'
            )
            SELECT criticality, COUNT(DISTINCT patient_id) AS patient_count
            FROM allergy, resolved
            WHERE allergy.code = resolved.code AND allergy.system = resolved.code_system
            GROUP BY criticality
        """,
    },
    {
        "id": "t2_careplan_active_duration",
        "tier": 2,
        "source_table": "encounter",
        "description": "count of encounters of a given type per status",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "encounter", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "count", "group_by": "status", "order_by": "count_desc", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'encounter' AND display ILIKE '%{display}%'
            )
            SELECT status, COUNT(*) AS encounter_count
            FROM encounter, resolved
            WHERE encounter.type_code = resolved.code AND encounter.type_system = resolved.code_system
            GROUP BY status
            ORDER BY encounter_count DESC
        """,
    },

    # ---------------- TIER 3: 2-3 table join + aggregation ----------------
    {
        "id": "t3_condition_by_gender",
        "tier": 3,
        "source_table": "condition",
        "description": "count of patients with a given condition, broken down by gender",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [
                {"table": "patient", "field": "gender", "purpose": "group_by"},
            ],
            "constraints": [],
            "aggregation": {"type": "count_distinct_patient", "group_by": "gender", "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            )
            SELECT p.gender, COUNT(DISTINCT c.patient_id) AS patient_count
            FROM condition c
            JOIN patient p ON c.patient_id = p.id
            JOIN resolved r ON c.code = r.code AND c.system = r.code_system
            GROUP BY p.gender
        """,
    },
    {
        "id": "t3_condition_over_age",
        "tier": 3,
        "source_table": "condition",
        "description": "count of patients over 65 who have a given condition",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [
                {"table": "patient", "field": "birthDate", "purpose": "filter"},
            ],
            "constraints": [
                {"type": "age", "comparison": ">=", "value": 65},
            ],
            "aggregation": {"type": "count_distinct_patient", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            )
            SELECT COUNT(DISTINCT c.patient_id) AS patient_count
            FROM condition c
            JOIN patient p ON c.patient_id = p.id
            JOIN resolved r ON c.code = r.code AND c.system = r.code_system
            WHERE DATE_DIFF('year', p.birthDate, c.onsetDateTime) >= 65
        """,
    },
    {
        "id": "t3_condition_avg_observation",
        "tier": 3,
        "source_table": "condition",
        "companion": "observation:29463-7:http://loinc.org",  # Body Weight, always present -- lookup-resolved too
        "description": "average body weight of patients who have a given condition",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
                {"role": "companion", "concept": "Body Weight", "domain": "observation", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "avg", "group_by": "unit", "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            ),
            companion AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'observation' AND display = 'Body Weight'
            )
            SELECT ROUND(AVG(o.valueQuantity), 4) AS avg_weight, o.unit
            FROM condition c
            JOIN resolved r ON c.code = r.code AND c.system = r.code_system
            JOIN observation o ON c.patient_id = o.patient_id
            JOIN companion co ON o.code = co.code AND o.system = co.code_system
            GROUP BY o.unit
        """,
    },
    {
        "id": "t3_medication_and_condition",
        "tier": 3,
        "source_table": "medication_request",
        "companion_table": "condition",
        "description": "count of patients on a given medication who also have a given condition (paired with a fixed common condition -- hypertension)",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "medication_request", "terminology_lookup": True},
                {"role": "companion", "concept": "Essential hypertension (disorder)", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "count_distinct_patient", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'medication_request' AND display ILIKE '%{display}%'
            ),
            companion AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display = 'Essential hypertension (disorder)'
            )
            SELECT COUNT(DISTINCT m.patient_id) AS patient_count
            FROM medication_request m
            JOIN resolved r ON m.code = r.code AND m.system = r.code_system
            JOIN condition c ON m.patient_id = c.patient_id
            JOIN companion co ON c.code = co.code AND c.system = co.code_system
        """,
    },
    {
        "id": "t3_procedure_with_encounter_type",
        "tier": 3,
        "source_table": "procedure",
        "description": "count of a given procedure broken down by the encounter type it occurred in",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "procedure", "terminology_lookup": True},
            ],
            "joins": [
                {"table": "encounter", "field": "type_code", "purpose": "group_by"},
            ],
            "constraints": [],
            "aggregation": {"type": "count", "group_by": "encounter_type", "order_by": "count_desc", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'procedure' AND display ILIKE '%{display}%'
            )
            SELECT e.type_code AS encounter_code, e.type_display AS encounter_display, COUNT(*) AS procedure_count
            FROM procedure pr
            JOIN resolved r ON pr.code = r.code AND pr.system = r.code_system
            JOIN encounter e ON pr.encounter_id = e.id
            GROUP BY e.type_code, e.type_display
            ORDER BY procedure_count DESC
        """,
    },
    {
        "id": "t3_immunization_by_gender",
        "tier": 3,
        "source_table": "immunization",
        "description": "count of patients who received a given immunization, broken down by gender",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "immunization", "terminology_lookup": True},
            ],
            "joins": [
                {"table": "patient", "field": "gender", "purpose": "group_by"},
            ],
            "constraints": [],
            "aggregation": {"type": "count_distinct_patient", "group_by": "gender", "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'immunization' AND display ILIKE '%{display}%'
            )
            SELECT p.gender, COUNT(DISTINCT i.patient_id) AS patient_count
            FROM immunization i
            JOIN patient p ON i.patient_id = p.id
            JOIN resolved r ON i.vaccineCode = r.code AND i.vaccineCode_system = r.code_system
            GROUP BY p.gender
        """,
    },
    {
        "id": "t3_avg_procedures_per_patient_with_condition",
        "tier": 3,
        "source_table": "condition",
        "description": "average number of procedures performed per patient among those who have a given condition",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [
                {"table": "procedure", "field": "id", "purpose": "output_column"},
            ],
            "constraints": [],
            "aggregation": {"type": "avg_per_patient", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": "procedure_count"},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            )
            SELECT AVG(proc_count) AS avg_procedures_per_patient
            FROM (
                SELECT c.patient_id, COUNT(pr.id) AS proc_count
                FROM condition c
                JOIN resolved r ON c.code = r.code AND c.system = r.code_system
                LEFT JOIN procedure pr ON c.patient_id = pr.patient_id
                GROUP BY c.patient_id
            ) sub
        """,
    },
    {
        "id": "t3_diagnostic_report_with_condition",
        "tier": 3,
        "source_table": "diagnostic_report",
        "companion": "condition:59621000:http://snomed.info/sct",
        "description": "count of a given diagnostic report type generated for patients who have hypertension",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "diagnostic_report", "terminology_lookup": True},
                {"role": "companion", "concept": "Essential hypertension (disorder)", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "count", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'diagnostic_report' AND display ILIKE '%{display}%'
            ),
            companion AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display = 'Essential hypertension (disorder)'
            )
            SELECT COUNT(*) AS report_count
            FROM diagnostic_report dr
            JOIN resolved r ON dr.code = r.code AND dr.system = r.code_system
            JOIN condition c ON dr.patient_id = c.patient_id
            JOIN companion co ON c.code = co.code AND c.system = co.code_system
        """,
    },
    {
        "id": "t3_observation_and_medication",
        "tier": 3,
        "source_table": "observation",
        "requires_numeric": True,
        "companion": "medication_request:314076:http://www.nlm.nih.gov/research/umls/rxnorm",  # lisinopril 10mg
        "description": "count of patients whose given observation reading exceeds a threshold and who are prescribed lisinopril",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "observation", "terminology_lookup": True},
                {"role": "companion", "concept": "lisinopril 10 MG Oral Tablet", "domain": "medication_request", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "threshold", "field": "valueQuantity", "comparison": ">", "value": "{threshold}"},
            ],
            "aggregation": {"type": "count_distinct_patient", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'observation' AND display ILIKE '%{display}%'
            ),
            companion AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'medication_request' AND display = 'lisinopril 10 MG Oral Tablet'
            )
            SELECT COUNT(DISTINCT o.patient_id) AS patient_count
            FROM observation o
            JOIN resolved r ON o.code = r.code AND o.system = r.code_system
            JOIN medication_request m ON o.patient_id = m.patient_id
            JOIN companion co ON m.code = co.code AND m.system = co.code_system
            WHERE o.valueQuantity > {threshold}
        """,
    },
    {
        "id": "t3_allergy_and_condition_count",
        "tier": 3,
        "source_table": "allergy",
        "companion": "condition:271737000:http://snomed.info/sct",  # Anemia
        "description": "count of patients with a given allergy who also have anemia",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "allergy", "terminology_lookup": True},
                {"role": "companion", "concept": "Anemia (disorder)", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "count_distinct_patient", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'allergy' AND display ILIKE '%{display}%'
            ),
            companion AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display = 'Anemia (disorder)'
            )
            SELECT COUNT(DISTINCT a.patient_id) AS patient_count
            FROM allergy a
            JOIN resolved r ON a.code = r.code AND a.system = r.code_system
            JOIN condition c ON a.patient_id = c.patient_id
            JOIN companion co ON c.code = co.code AND c.system = co.code_system
        """,
    },
    {
        "id": "t3_condition_encounter_count",
        "tier": 3,
        "source_table": "condition",
        "description": "average number of encounters per patient among those diagnosed with a given condition",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [
                {"table": "encounter", "field": "id", "purpose": "output_column"},
            ],
            "constraints": [],
            "aggregation": {"type": "avg_per_patient", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": "encounter_count"},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            )
            SELECT AVG(enc_count) AS avg_encounters_per_patient
            FROM (
                SELECT c.patient_id, COUNT(DISTINCT e.id) AS enc_count
                FROM condition c
                JOIN resolved r ON c.code = r.code AND c.system = r.code_system
                LEFT JOIN encounter e ON c.patient_id = e.patient_id
                GROUP BY c.patient_id
            ) sub
        """,
    },
    {
        "id": "t3_medication_by_encounter_class",
        "tier": 3,
        "source_table": "medication_request",
        "description": "count of a given medication's prescriptions broken down by the encounter class they were authored in",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "medication_request", "terminology_lookup": True},
            ],
            "joins": [
                {"table": "encounter", "field": "class_code", "purpose": "group_by"},
            ],
            "constraints": [],
            "aggregation": {"type": "count", "group_by": "encounter_class", "order_by": "count_desc", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'medication_request' AND display ILIKE '%{display}%'
            )
            SELECT e.class_code, COUNT(*) AS rx_count
            FROM medication_request m
            JOIN resolved r ON m.code = r.code AND m.system = r.code_system
            JOIN encounter e ON m.encounter_id = e.id
            GROUP BY e.class_code
            ORDER BY rx_count DESC
        """,
    },
    {
        "id": "t3_procedure_avg_patient_age",
        "tier": 3,
        "source_table": "procedure",
        "description": "average patient age at the time a given procedure was performed",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "procedure", "terminology_lookup": True},
            ],
            "joins": [
                {"table": "patient", "field": "birthDate", "purpose": "output_column"},
            ],
            "constraints": [
                {"type": "existence", "field": "performedDateTime", "negate": False},
            ],
            "aggregation": {"type": "avg_age_at_event", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'procedure' AND display ILIKE '%{display}%'
            )
            SELECT AVG(DATE_DIFF('year', p.birthDate, pr.performedDateTime)) AS avg_age_at_procedure
            FROM procedure pr
            JOIN resolved r ON pr.code = r.code AND pr.system = r.code_system
            JOIN patient p ON pr.patient_id = p.id
            WHERE pr.performedDateTime IS NOT NULL
        """,
    },

    # ---------------- TIER 4: longitudinal delta, cohort+outcome, temporal windows, top-N in group ----------------
    {
        "id": "t4_observation_first_vs_last",
        "tier": 4,
        "source_table": "observation",
        "requires_numeric": True,
        "description": "for each patient, the change in a given observation's value between their first and most recent recorded reading",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "observation", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "valueQuantity", "negate": False},
            ],
            "aggregation": {"type": "window_first_vs_last", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'observation' AND display ILIKE '%{display}%'
            ),
            ranked AS (
                SELECT observation.patient_id, observation.valueQuantity, observation.effectiveDateTime,
                       ROW_NUMBER() OVER (PARTITION BY observation.patient_id ORDER BY observation.effectiveDateTime ASC, observation.id ASC) AS rn_first,
                       ROW_NUMBER() OVER (PARTITION BY observation.patient_id ORDER BY observation.effectiveDateTime DESC, observation.id ASC) AS rn_last
                FROM observation, resolved
                WHERE observation.code = resolved.code AND observation.system = resolved.code_system
                  AND observation.valueQuantity IS NOT NULL
            )
            SELECT f.patient_id, f.valueQuantity AS first_value, l.valueQuantity AS last_value,
                   l.valueQuantity - f.valueQuantity AS delta
            FROM (SELECT * FROM ranked WHERE rn_first = 1) f
            JOIN (SELECT * FROM ranked WHERE rn_last = 1) l ON f.patient_id = l.patient_id
            WHERE f.patient_id != l.patient_id OR f.effectiveDateTime != l.effectiveDateTime
        """,
    },
    {
        "id": "t4_most_recent_observation_per_patient",
        "tier": 4,
        "source_table": "observation",
        "requires_numeric": True,
        "companion": "condition:59621000:http://snomed.info/sct",  # hypertension, lookup-resolved
        "description": "for each patient with a given condition, their most recent reading of a given observation (uses a fixed anchor condition -- hypertension)",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "observation", "terminology_lookup": True},
                {"role": "companion", "concept": "Essential hypertension (disorder)", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "window_most_recent", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'observation' AND display ILIKE '%{display}%'
            ),
            companion AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display = 'Essential hypertension (disorder)'
            )
            SELECT o.patient_id, o.valueQuantity, o.effectiveDateTime
            FROM observation o
            JOIN resolved r ON o.code = r.code AND o.system = r.code_system
            JOIN condition c ON o.patient_id = c.patient_id
            JOIN companion co ON c.code = co.code AND c.system = co.code_system
            QUALIFY ROW_NUMBER() OVER (PARTITION BY o.patient_id ORDER BY o.effectiveDateTime DESC, o.id DESC) = 1
        """,
    },
    {
        "id": "t4_condition_then_procedure_30d",
        "tier": 4,
        "source_table": "condition",
        "companion": "procedure:73761001:http://snomed.info/sct",  # Colonoscopy
        "description": "patients diagnosed with a given condition who had a colonoscopy within 90 days afterward",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
                {"role": "companion", "concept": "Colonoscopy (procedure)", "domain": "procedure", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "temporal_window", "relation": "within", "value": 90, "unit": "days",
                 "anchor": "condition_onset_to_companion_procedure"},
            ],
            "aggregation": {"type": "list_distinct_patient", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            ),
            companion AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'procedure' AND display = 'Colonoscopy (procedure)'
            )
            SELECT DISTINCT c.patient_id
            FROM condition c
            JOIN resolved r ON c.code = r.code AND c.system = r.code_system
            JOIN procedure pr ON c.patient_id = pr.patient_id
            JOIN companion co ON pr.code = co.code AND pr.system = co.code_system
            WHERE pr.performedDateTime BETWEEN c.onsetDateTime AND c.onsetDateTime + INTERVAL 90 DAY
        """,
    },
    {
        "id": "t4_top5_patients_by_medication_count",
        "tier": 4,
        "source_table": "medication_request",
        "description": "the 5 patients with the most prescriptions of a given medication",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "medication_request", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "top_n", "group_by": "patient_id", "order_by": "count_desc", "limit": 5, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'medication_request' AND display ILIKE '%{display}%'
            )
            SELECT patient_id, COUNT(*) AS rx_count
            FROM medication_request, resolved
            WHERE medication_request.code = resolved.code AND medication_request.system = resolved.code_system
            GROUP BY patient_id
            ORDER BY rx_count DESC, patient_id
            LIMIT 5
        """,
    },
    {
        "id": "t4_patients_with_3plus_encounters_12mo",
        "tier": 4,
        "source_table": "encounter",
        "description": "patients who had 3 or more encounters of a given type within any 12-month window (approximated via calendar-year grouping)",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "encounter", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "period_start", "negate": False},
                {"type": "having", "field": "count", "comparison": ">=", "value": 3},
            ],
            "aggregation": {"type": "count", "group_by": "patient_id", "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'encounter' AND display ILIKE '%{display}%'
            )
            SELECT patient_id, EXTRACT(YEAR FROM period_start) AS enc_year, COUNT(*) AS encounter_count
            FROM encounter, resolved
            WHERE encounter.type_code = resolved.code AND encounter.type_system = resolved.code_system
              AND period_start IS NOT NULL
            GROUP BY patient_id, enc_year
            HAVING COUNT(*) >= 3
        """,
    },
    {
        "id": "t4_top5_patients_by_condition_recurrence",
        "tier": 4,
        "source_table": "condition",
        "description": "the 5 patients with the most recorded diagnoses of a given condition (recurrence)",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "top_n", "group_by": "patient_id", "order_by": "count_desc", "limit": 5, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            )
            SELECT patient_id, COUNT(*) AS diagnosis_count
            FROM condition, resolved
            WHERE condition.code = resolved.code AND condition.system = resolved.code_system
            GROUP BY patient_id
            ORDER BY diagnosis_count DESC, patient_id
            LIMIT 5
        """,
    },
    {
        "id": "t4_time_from_condition_to_medication",
        "tier": 4,
        "source_table": "condition",
        "companion": "medication_request:314076:http://www.nlm.nih.gov/research/umls/rxnorm",
        "description": "average number of days between diagnosis of a given condition and the first lisinopril prescription for the same patient",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
                {"role": "companion", "concept": "lisinopril 10 MG Oral Tablet", "domain": "medication_request", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "avg_days_between_events", "group_by": None, "order_by": None, "limit": None,
                             "per_patient_metric": None, "anchor": "condition_onset_to_companion_first_rx"},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            ),
            companion AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'medication_request' AND display = 'lisinopril 10 MG Oral Tablet'
            )
            SELECT AVG(DATE_DIFF('day', c.onsetDateTime, m.first_rx)) AS avg_days_to_treatment
            FROM condition c
            JOIN resolved r ON c.code = r.code AND c.system = r.code_system
            JOIN (
                SELECT medication_request.patient_id, MIN(authoredOn) AS first_rx
                FROM medication_request, companion
                WHERE medication_request.code = companion.code AND medication_request.system = companion.code_system
                GROUP BY medication_request.patient_id
            ) m ON c.patient_id = m.patient_id
            WHERE m.first_rx >= c.onsetDateTime
        """,
    },
    {
        "id": "t4_observation_trend_yearly_delta",
        "tier": 4,
        "source_table": "observation",
        "requires_numeric": True,
        "description": "year-over-year change in the average value of a given observation",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "observation", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "effectiveDateTime", "negate": False},
            ],
            "aggregation": {"type": "yearly_trend_delta", "group_by": None, "order_by": "chronological", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'observation' AND display ILIKE '%{display}%'
            ),
            yearly AS (
                SELECT EXTRACT(YEAR FROM effectiveDateTime) AS yr, ROUND(AVG(observation.valueQuantity), 4) AS avg_val
                FROM observation, resolved
                WHERE observation.code = resolved.code AND observation.system = resolved.code_system
                  AND effectiveDateTime IS NOT NULL
                GROUP BY yr
            )
            SELECT yr, avg_val, avg_val - LAG(avg_val) OVER (ORDER BY yr) AS yoy_delta
            FROM yearly
            ORDER BY yr
        """,
    },
    {
        "id": "t4_first_diagnosis_age_per_patient",
        "tier": 4,
        "source_table": "condition",
        "description": "for each patient, their age at first diagnosis of a given condition, oldest 5 shown",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [
                {"table": "patient", "field": "birthDate", "purpose": "output_column"},
            ],
            "constraints": [],
            "aggregation": {"type": "top_n_by_value", "group_by": "patient_id", "order_by": "value_desc", "limit": 5, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            )
            SELECT c.patient_id, MIN(DATE_DIFF('year', p.birthDate, c.onsetDateTime)) AS age_at_first_diagnosis
            FROM condition c
            JOIN resolved r ON c.code = r.code AND c.system = r.code_system
            JOIN patient p ON c.patient_id = p.id
            GROUP BY c.patient_id
            ORDER BY age_at_first_diagnosis DESC, c.patient_id
            LIMIT 5
        """,
    },
]


def archetype_ids_by_tier():
    from collections import defaultdict
    d = defaultdict(list)
    for a in ARCHETYPES:
        d[a["tier"]].append(a["id"])
    return dict(d)


if __name__ == "__main__":
    print(f"Total archetypes: {len(ARCHETYPES)}")
    for tier, ids in sorted(archetype_ids_by_tier().items()):
        print(f"  tier {tier}: {len(ids)} archetypes")
