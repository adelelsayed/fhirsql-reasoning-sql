"""
"Regulatory reportable" archetypes, modeled on the general pattern of
periodic hospital regulatory reporting common to public health /
pharmaceutical-oversight regimes (illustrative of the category of reporting
obligation, not a citation of any single jurisdiction's statute):

  - Notifiable communicable disease surveillance: HIV/AIDS, viral hepatitis
    B/C, and COVID-19 are commonly designated notifiable diseases, reported
    by treating facilities to the relevant public health authority.
  - Controlled/narcotic drug consumption reporting: periodic (commonly
    quarterly for narcotics, monthly for other controlled substances)
    aggregate dispensing reports to the relevant regulatory body, plus
    time-sensitive review of recent controlled-substance dispensing.

These concepts were checked to actually exist in the generated corpus before
building archetypes around them (data/train.duckdb) -- HIV and Hepatitis B/C
have low patient counts (5-39), well below the general >=50-patient
concept-selection floor used elsewhere. Deliberately included anyway: low
prevalence is *why* these are mandated reportables in the first place (a
hospital must report even a single case in some surveillance frameworks) --
this is a documented, justified exception to the general filtering rule, not
an oversight.

Converted to lookup-based like archetypes.py, for consistency -- even though
this whitelist is small and fixed, the model should never need a memorized
code, regulatory or otherwise. `SOURCE_TO_TABLE` gives the table each
archetype's lookup CTE resolves against. Each archetype also carries a
`plan`.
"""

NOTIFIABLE_DISEASE_CONCEPTS = [
    {"table_name": "condition", "code": "61977001", "code_system": "http://snomed.info/sct", "display": "Chronic type B viral hepatitis (disorder)"},
    {"table_name": "condition", "code": "128302006", "code_system": "http://snomed.info/sct", "display": "Chronic hepatitis C (disorder)"},
    {"table_name": "observation", "code": "55277-8", "code_system": "http://loinc.org", "display": "HIV status"},
    {"table_name": "observation", "code": "7917-8", "code_system": "http://loinc.org", "display": "HIV 1 Ab [Presence] in Serum"},
    {"table_name": "observation", "code": "20447-9", "code_system": "http://loinc.org", "display": "HIV 1 RNA [#/volume] (viral load) in Serum or Plasma by NAA with probe detection"},
    {"table_name": "observation", "code": "94531-1", "code_system": "http://loinc.org", "display": "SARS-CoV-2 (COVID-19) RNA panel - Respiratory system specimen by NAA with probe detection"},
]

# Opioids -- narcotics, quarterly regulatory reporting cadence
NARCOTIC_CONCEPTS = [
    {"table_name": "medication_request", "code": "1049221", "code_system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Acetaminophen 325 MG / Oxycodone Hydrochloride 5 MG Oral Tablet"},
    {"table_name": "medication_request", "code": "1049625", "code_system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Acetaminophen 325 MG / Oxycodone Hydrochloride 10 MG Oral Tablet [Percocet]"},
    {"table_name": "medication_request", "code": "856987", "code_system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Acetaminophen 300 MG / Hydrocodone Bitartrate 5 MG Oral Tablet"},
    {"table_name": "medication_request", "code": "857005", "code_system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Acetaminophen 325 MG / Hydrocodone Bitartrate 7.5 MG Oral Tablet"},
    {"table_name": "medication_request", "code": "1860491", "code_system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "12 HR Hydrocodone Bitartrate 10 MG Extended Release Oral Capsule"},
    {"table_name": "medication_request", "code": "245134", "code_system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "72 HR Fentanyl 0.025 MG/HR Transdermal System"},
    {"table_name": "medication_request", "code": "1860154", "code_system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Abuse-Deterrent 12 HR Oxycodone Hydrochloride 15 MG Extended Release Oral Tablet"},
    {"table_name": "medication_request", "code": "993770", "code_system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Acetaminophen 300 MG / Codeine Phosphate 15 MG Oral Tablet"},
    {"table_name": "medication_request", "code": "835603", "code_system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "tramadol hydrochloride 50 MG Oral Tablet"},
    {"table_name": "medication_request", "code": "351266", "code_system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "buprenorphine 2 MG / naloxone 0.5 MG Sublingual Tablet"},
]

# Benzodiazepines/stimulants -- controlled but non-narcotic, monthly regulatory reporting cadence
CONTROLLED_NONNARCOTIC_CONCEPTS = [
    {"table_name": "medication_request", "code": "197591", "code_system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Diazepam 5 MG Oral Tablet"},
    {"table_name": "medication_request", "code": "204892", "code_system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "clonazePAM 0.25 MG Oral Tablet"},
    {"table_name": "medication_request", "code": "1091392", "code_system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Methylphenidate Hydrochloride 20 MG Oral Tablet"},
]

CORPUS_REFERENCE_DATE = "2026-08-02"  # frozen reference date used for all Synthea generation, see METHODOLOGY_LOG.md

SOURCE_TO_TABLE = {
    "notifiable_condition": "condition",
    "notifiable_observation": "observation",
    "narcotic": "medication_request",
    "controlled_nonnarcotic": "medication_request",
}

REGULATORY_ARCHETYPES = [
    {
        "id": "reg_notifiable_condition_monthly",
        "tier": 2,
        "source": "notifiable_condition",
        "description": "monthly new-case count of a notifiable communicable disease diagnosis, for public-health reporting",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "onsetDateTime", "negate": False},
            ],
            "aggregation": {"type": "count_distinct_patient", "group_by": "month:onsetDateTime", "order_by": "chronological", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            )
            SELECT DATE_TRUNC('month', onsetDateTime) AS report_month, COUNT(DISTINCT patient_id) AS new_case_count
            FROM condition, resolved
            WHERE condition.code = resolved.code AND condition.system = resolved.code_system
              AND onsetDateTime IS NOT NULL
            GROUP BY report_month
            ORDER BY report_month
        """,
    },
    {
        "id": "reg_notifiable_lab_monthly",
        "tier": 2,
        "source": "notifiable_observation",
        "description": "monthly count of a notifiable-disease lab test/result, for public-health surveillance reporting",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "observation", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "effectiveDateTime", "negate": False},
            ],
            "aggregation": {"type": "count_distinct_patient", "group_by": "month:effectiveDateTime", "order_by": "chronological", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'observation' AND display ILIKE '%{display}%'
            )
            SELECT DATE_TRUNC('month', effectiveDateTime) AS report_month, COUNT(DISTINCT patient_id) AS test_count
            FROM observation, resolved
            WHERE observation.code = resolved.code AND observation.system = resolved.code_system
              AND effectiveDateTime IS NOT NULL
            GROUP BY report_month
            ORDER BY report_month
        """,
    },
    {
        "id": "reg_notifiable_active_case_list",
        "tier": 2,
        "source": "notifiable_condition",
        "description": "list of patients with an active notifiable disease diagnosis, for case management/contact tracing",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "condition", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "status", "field": "clinicalStatus", "value": "active"},
            ],
            "aggregation": {"type": "list_distinct_patient", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'condition' AND display ILIKE '%{display}%'
            )
            SELECT DISTINCT patient_id
            FROM condition, resolved
            WHERE condition.code = resolved.code AND condition.system = resolved.code_system
              AND clinicalStatus = 'active'
        """,
    },
    {
        "id": "reg_narcotic_quarterly_consumption",
        "tier": 2,
        "source": "narcotic",
        "description": "quarterly dispensing count of a narcotic medication, for the quarterly narcotic consumption report",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "medication_request", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "authoredOn", "negate": False},
            ],
            "aggregation": {"type": "count", "group_by": "quarter:authoredOn", "order_by": "chronological", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'medication_request' AND display ILIKE '%{display}%'
            )
            SELECT DATE_TRUNC('quarter', authoredOn) AS report_quarter, COUNT(*) AS dispense_count
            FROM medication_request, resolved
            WHERE medication_request.code = resolved.code AND medication_request.system = resolved.code_system
              AND authoredOn IS NOT NULL
            GROUP BY report_quarter
            ORDER BY report_quarter
        """,
    },
    {
        "id": "reg_controlled_monthly_consumption",
        "tier": 2,
        "source": "controlled_nonnarcotic",
        "description": "monthly dispensing count of a controlled (non-narcotic) medication, for the monthly controlled-drug consumption report",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "medication_request", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "existence", "field": "authoredOn", "negate": False},
            ],
            "aggregation": {"type": "count", "group_by": "month:authoredOn", "order_by": "chronological", "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": """
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'medication_request' AND display ILIKE '%{display}%'
            )
            SELECT DATE_TRUNC('month', authoredOn) AS report_month, COUNT(*) AS dispense_count
            FROM medication_request, resolved
            WHERE medication_request.code = resolved.code AND medication_request.system = resolved.code_system
              AND authoredOn IS NOT NULL
            GROUP BY report_month
            ORDER BY report_month
        """,
    },
    {
        "id": "reg_recent_narcotic_patients",
        "tier": 2,
        "source": "narcotic",
        "description": "patients dispensed a narcotic medication in the last 30 days, for time-sensitive utilization review",
        "lookup_based": True,
        "plan": {
            "entities": [
                {"role": "primary", "concept": "{display}", "domain": "medication_request", "terminology_lookup": True},
            ],
            "joins": [],
            "constraints": [
                {"type": "recency", "relation": "within_last", "value": 30, "unit": "days"},
            ],
            "aggregation": {"type": "list_distinct_patient", "group_by": None, "order_by": None, "limit": None, "per_patient_metric": None},
            "abstain": False,
        },
        "sql": f"""
            WITH resolved AS (
                SELECT code, code_system FROM valuesets
                WHERE table_name = 'medication_request' AND display ILIKE '%{{display}}%'
            )
            SELECT DISTINCT patient_id
            FROM medication_request, resolved
            WHERE medication_request.code = resolved.code AND medication_request.system = resolved.code_system
              AND authoredOn >= DATE '{CORPUS_REFERENCE_DATE}' - INTERVAL 30 DAY
        """,
    },
]

SOURCE_TO_CONCEPTS = {
    "notifiable_condition": [c for c in NOTIFIABLE_DISEASE_CONCEPTS if c["table_name"] == "condition"],
    "notifiable_observation": [c for c in NOTIFIABLE_DISEASE_CONCEPTS if c["table_name"] == "observation"],
    "narcotic": NARCOTIC_CONCEPTS,
    "controlled_nonnarcotic": CONTROLLED_NONNARCOTIC_CONCEPTS,
}
