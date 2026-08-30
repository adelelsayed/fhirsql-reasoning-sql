"""
Physician-attribution and bed-occupancy/operational archetypes.
participant_npi/requester_npi are available on encounter/medication_request;
real class_code values in the data are AMB/EMER/IMP/HH/VR (IMP = inpatient,
33,818 encounters, enough volume for occupancy-style queries).

Two shapes:
  - CONCEPT_ARCHETYPES: parameterized by a concept (like the main archetype
    factory) -- doctor-level counts tied to a specific condition/medication/
    encounter-type. Lookup-based, carries a `plan`.
  - STRUCTURAL_ARCHETYPES: no concept parameter at all -- pure operational
    queries about the encounter table's structure (bed occupancy, length of
    stay). Instantiated exactly once each, not per-concept. Still carry a
    `plan` (with empty `entities`) since the SFT target is always
    `plan + sql`, even when there's no concept to resolve.
"""

CONCEPT_ARCHETYPES = [
    {
        "id": "doctor_top5_by_encounter_type",
        "tier": 3,
        "source_table": "encounter",
        "description": "top 5 physicians by number of encounters of a given type",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "encounter", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "top_n", "group_by": "participant_name", "order_by": "count_desc", "limit": 5, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'encounter' AND display ILIKE '%{display}%'
            )
            SELECT participant_name, COUNT(*) AS encounter_count
            FROM encounter, resolved
            WHERE encounter.type_code = resolved.code AND encounter.type_system = resolved.code_system
            GROUP BY participant_name
            ORDER BY encounter_count DESC, participant_name
            LIMIT 5
        """,
    },
    {
        "id": "doctor_top5_prescribers",
        "tier": 3,
        "source_table": "medication_request",
        "description": "top 5 prescribing physicians for a given medication",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "medication_request", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [],
            "aggregation": {"type": "top_n", "group_by": "requester_name", "order_by": "count_desc", "limit": 5, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'medication_request' AND display ILIKE '%{display}%'
            )
            SELECT requester_name, COUNT(*) AS rx_count
            FROM medication_request, resolved
            WHERE medication_request.code = resolved.code AND medication_request.system = resolved.code_system
            GROUP BY requester_name
            ORDER BY rx_count DESC, requester_name
            LIMIT 5
        """,
    },
    {
        "id": "doctor_top5_by_condition_diagnosed",
        "tier": 4,
        "source_table": "condition",
        "description": "top 5 physicians by number of distinct patients diagnosed with a given condition at their encounter",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [
                {"table": "encounter", "field": "participant_name", "purpose": "group_by"},
            ],
            "constraints": [],
            "aggregation": {"type": "top_n", "group_by": "participant_name", "order_by": "count_desc", "limit": 5, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            )
            SELECT e.participant_name, COUNT(DISTINCT c.patient_id) AS patient_count
            FROM condition c
            JOIN resolved r ON c.code = r.code AND c.system = r.code_system
            JOIN encounter e ON c.encounter_id = e.id
            GROUP BY e.participant_name
            ORDER BY patient_count DESC, e.participant_name
            LIMIT 5
        """,
    },
]

STRUCTURAL_ARCHETYPES = [
    {
        "id": "bed_occupancy_at_date",
        "tier": 3,
        "description": "number of inpatient beds occupied at a fixed point in time",
        "plan": {
            "entities": [],
            "joins": [],
            "constraints": [
                {"type": "status", "field": "class_code", "value": "IMP"},
                {"type": "point_in_time", "field": "period_start/period_end", "date": "2025-01-15"},
            ],
            "aggregation": {"type": "count", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            SELECT COUNT(*) AS beds_occupied
            FROM encounter
            WHERE class_code = 'IMP'
              AND period_start <= DATE '2025-01-15'
              AND (period_end IS NULL OR period_end >= DATE '2025-01-15')
        """,
    },
    {
        "id": "bed_occupancy_by_month",
        "tier": 2,
        "description": "number of inpatient admissions per month",
        "plan": {
            "entities": [],
            "joins": [],
            "constraints": [
                {"type": "status", "field": "class_code", "value": "IMP"},
                {"type": "existence", "field": "period_start", "negate": False},
            ],
            "aggregation": {"type": "count", "group_by": "month:period_start", "order_by": "chronological", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            SELECT DATE_TRUNC('month', period_start) AS admit_month, COUNT(*) AS admission_count
            FROM encounter
            WHERE class_code = 'IMP' AND period_start IS NOT NULL
            GROUP BY admit_month
            ORDER BY admit_month
        """,
    },
    {
        "id": "avg_length_of_stay",
        "tier": 2,
        "description": "average inpatient length of stay in days",
        "plan": {
            "entities": [],
            "joins": [],
            "constraints": [
                {"type": "status", "field": "class_code", "value": "IMP"},
                {"type": "existence", "field": "period_end", "negate": False},
            ],
            "aggregation": {"type": "avg", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            SELECT AVG(DATE_DIFF('day', period_start, period_end)) AS avg_los_days
            FROM encounter
            WHERE class_code = 'IMP' AND period_end IS NOT NULL
        """,
    },
    {
        "id": "current_inpatient_census_by_month",
        "tier": 4,
        "description": "average daily inpatient census (beds occupied), sampled monthly across the study period",
        "plan": {
            "entities": [],
            "joins": [],
            "constraints": [
                {"type": "status", "field": "class_code", "value": "IMP"},
                {"type": "existence", "field": "period_start", "negate": False},
            ],
            "aggregation": {"type": "count", "group_by": "month:period_start", "order_by": "chronological", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH months AS (
                SELECT DISTINCT DATE_TRUNC('month', period_start) AS sample_month
                FROM encounter WHERE class_code = 'IMP' AND period_start IS NOT NULL
            )
            SELECT m.sample_month,
                   COUNT(e.id) AS beds_occupied_at_month_start
            FROM months m
            LEFT JOIN encounter e
              ON e.class_code = 'IMP'
              AND e.period_start <= m.sample_month
              AND (e.period_end IS NULL OR e.period_end >= m.sample_month)
            GROUP BY m.sample_month
            ORDER BY m.sample_month
        """,
    },
]
