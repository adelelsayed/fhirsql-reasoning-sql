"""
Hospital quality-KPI, demographics, and imaging volume archetypes.

Readmission rate, fall-risk screening volume, and mortality review are
standard hospital quality indicators used across accreditation and
value-based-care quality programs generally (not modeled on any single
jurisdiction's specific KPI catalog -- just the same broad category of
measure common to hospital quality reporting).

Demographics: patient-mix reporting by race/ethnicity/state, standard
categories already present on the `patient` table (Synthea's US-based
synthetic patients don't carry a nationality field, so race/ethnicity/state
are the available demographic breakdowns here).

Imaging: promoted imaging_study table (see schema.sql) -- radiology order
VOLUME is answerable; radiology-BY-DEPARTMENT is not (no department/
service-line concept exists anywhere in Synthea's FHIR output).

Two shapes, same convention as operational_archetypes.py:
  - CONCEPT_ARCHETYPES: parameterized by a concept. Lookup-based, carries a
    `plan`.
  - STRUCTURAL_ARCHETYPES: no per-instantiation concept parameter, instantiated
    once each. Two of these (mortality/fall-risk) always filter on the SAME
    fixed code every time -- converted to an exact-match lookup CTE too (same
    treatment as archetypes.py's "companion" concepts), for the same reason:
    no hardcoded code anywhere, even a fixed structural one. All structural
    archetypes carry a `plan` (empty `entities` where there's truly no
    concept at all) since the SFT target is always `plan + sql`.
"""

CONCEPT_ARCHETYPES = [
    {
        "id": "condition_by_race",
        "tier": 3,
        "source_table": "condition",
        "description": "count of patients with a given condition, broken down by race",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [
                {"table": "patient", "field": "race", "purpose": "group_by"},
            ],
            "constraints": [],
            "aggregation": {"type": "count_distinct_patient", "group_by": "race", "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            )
            SELECT p.race, COUNT(DISTINCT c.patient_id) AS patient_count
            FROM condition c
            JOIN patient p ON c.patient_id = p.id
            JOIN resolved r ON c.code = r.code AND c.system = r.code_system
            GROUP BY p.race
        """,
    },
    {
        "id": "condition_by_ethnicity",
        "tier": 3,
        "source_table": "condition",
        "description": "count of patients with a given condition, broken down by ethnicity",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [
                {"table": "patient", "field": "ethnicity", "purpose": "group_by"},
            ],
            "constraints": [],
            "aggregation": {"type": "count_distinct_patient", "group_by": "ethnicity", "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            )
            SELECT p.ethnicity, COUNT(DISTINCT c.patient_id) AS patient_count
            FROM condition c
            JOIN patient p ON c.patient_id = p.id
            JOIN resolved r ON c.code = r.code AND c.system = r.code_system
            GROUP BY p.ethnicity
        """,
    },
]

STRUCTURAL_ARCHETYPES = [
    {
        "id": "physician_monthly_case_volume",
        "tier": 4,
        "description": "for each physician, number of distinct patients seen per month",
        "plan": {
            "entities": [],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "period_start", "negate": False},
                {"type": "existence", "field": "participant_name", "negate": False},
            ],
            "aggregation": {"type": "count_distinct_patient", "group_by": "participant_name", "order_by": "chronological", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            SELECT participant_name, DATE_TRUNC('month', period_start) AS visit_month,
                   COUNT(DISTINCT patient_id) AS patient_count
            FROM encounter
            WHERE period_start IS NOT NULL AND participant_name IS NOT NULL
            GROUP BY participant_name, visit_month
            ORDER BY visit_month, patient_count DESC
        """,
    },
    {
        "id": "readmission_rate_30day",
        "tier": 4,
        "description": "count of patients readmitted as inpatient within 30 days of a prior inpatient discharge",
        "plan": {
            "entities": [],
            "joins": [],
            "constraints": [
                {"type": "status", "field": "class_code", "value": "IMP"},
                {"type": "existence", "field": "period_end", "negate": False},
                {"type": "temporal_window", "relation": "within", "value": 30, "unit": "days",
                 "anchor": "discharge_to_next_admission"},
            ],
            "aggregation": {"type": "count_distinct_patient", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH imp AS (
                SELECT patient_id, period_start, period_end,
                       LEAD(period_start) OVER (PARTITION BY patient_id ORDER BY period_start) AS next_admission
                FROM encounter
                WHERE class_code = 'IMP' AND period_end IS NOT NULL
            )
            SELECT COUNT(DISTINCT patient_id) AS readmitted_patient_count
            FROM imp
            WHERE next_admission IS NOT NULL
              AND DATE_DIFF('day', period_end, next_admission) BETWEEN 0 AND 30
        """,
    },
    {
        "id": "mortality_review_monthly",
        "tier": 2,
        "description": "count of death-certification encounters per month, for mortality review",
        "plan": {
            "entities": [
                {"role": "primary", "concept": "Death Certification", "domain": "encounter", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "period_start", "negate": False},
            ],
            "aggregation": {"type": "count", "group_by": "month:period_start", "order_by": "chronological", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'encounter' AND display = 'Death Certification'
            )
            SELECT DATE_TRUNC('month', period_start) AS review_month, COUNT(*) AS death_count
            FROM encounter, resolved
            WHERE encounter.type_code = resolved.code AND encounter.type_system = resolved.code_system
              AND period_start IS NOT NULL
            GROUP BY review_month
            ORDER BY review_month
        """,
    },
    {
        "id": "fall_risk_screening_monthly",
        "tier": 2,
        "description": "count of Morse Fall Scale screenings performed per month, a standard patient-safety KPI",
        "plan": {
            "entities": [
                {"role": "primary", "concept": "Assessment using Morse Fall Scale (procedure)", "domain": "procedure", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "performedDateTime", "negate": False},
            ],
            "aggregation": {"type": "count", "group_by": "month:performedDateTime", "order_by": "chronological", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'procedure' AND display = 'Assessment using Morse Fall Scale (procedure)'
            )
            SELECT DATE_TRUNC('month', performedDateTime) AS screening_month, COUNT(*) AS screening_count
            FROM procedure, resolved
            WHERE procedure.code = resolved.code AND procedure.system = resolved.code_system
              AND performedDateTime IS NOT NULL
            GROUP BY screening_month
            ORDER BY screening_month
        """,
    },
    {
        "id": "patients_by_race",
        "tier": 1,
        "description": "count of patients broken down by race",
        "plan": {
            "entities": [],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "count", "group_by": "race", "order_by": "count_desc", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            SELECT race, COUNT(*) AS patient_count
            FROM patient
            GROUP BY race
            ORDER BY patient_count DESC
        """,
    },
    {
        "id": "patients_by_ethnicity",
        "tier": 1,
        "description": "count of patients broken down by ethnicity",
        "plan": {
            "entities": [],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "count", "group_by": "ethnicity", "order_by": "count_desc", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            SELECT ethnicity, COUNT(*) AS patient_count
            FROM patient
            GROUP BY ethnicity
            ORDER BY patient_count DESC
        """,
    },
    {
        "id": "patients_by_state",
        "tier": 1,
        "description": "count of patients broken down by state",
        "plan": {
            "entities": [],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "count", "group_by": "state", "order_by": "count_desc", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            SELECT state, COUNT(*) AS patient_count
            FROM patient
            GROUP BY state
            ORDER BY patient_count DESC
        """,
    },
    {
        "id": "imaging_volume_by_month",
        "tier": 2,
        "description": "count of imaging studies (radiology orders) performed per month",
        "plan": {
            "entities": [],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "started", "negate": False},
            ],
            "aggregation": {"type": "count", "group_by": "month:started", "order_by": "chronological", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            SELECT DATE_TRUNC('month', started) AS study_month, COUNT(*) AS study_count
            FROM imaging_study
            WHERE started IS NOT NULL
            GROUP BY study_month
            ORDER BY study_month
        """,
    },
    {
        "id": "imaging_volume_by_modality",
        "tier": 2,
        "description": "count of imaging studies broken down by modality (X-ray, CT, MRI, etc.)",
        "plan": {
            "entities": [],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "modality_display", "negate": False},
            ],
            "aggregation": {"type": "count", "group_by": "modality_display", "order_by": "count_desc", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            SELECT modality_display, COUNT(*) AS study_count
            FROM imaging_study
            WHERE modality_display IS NOT NULL
            GROUP BY modality_display
            ORDER BY study_count DESC
        """,
    },
]
