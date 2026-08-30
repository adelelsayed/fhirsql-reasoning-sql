"""
Unanswerable training data: the model must be trained to decline. Generates
questions referencing columns deliberately excluded from the schema, with
the gold output being an explicit refusal. Target ~8% of the final training set.

Gold target for every row here is the literal string ABSTENTION_TOKEN, not
SQL -- this is what the model must learn to produce instead of hallucinating
a plausible-looking query against columns that don't exist. Matches the RL
reward structure, which treats correct abstention and
confident-wrong-answer-on-unanswerable as distinct, oppositely-signed reward
categories.

Every category here was checked against the actual frozen schema (11 core
tables: patient, condition, observation, medication_request, encounter,
procedure, immunization, allergy, careplan, diagnostic_report, imaging_study)
to confirm the referenced data is genuinely absent -- not merely a concept
that wasn't selected, but a column/field that does not exist in any core
table. This distinction matters: a false "unanswerable" label (something
that's actually answerable) would train the model to wrongly refuse valid
questions, which is a worse failure mode than the one this phase targets.

Two shapes:
  - FIXED: a single scenario, no parameter, several paraphrases each.
  - PARAMETERIZED: the missing-data category is independent of which concept
    is mentioned (e.g. billing amount is unanswerable regardless of which
    procedure), so parameterizing over real concepts (reusing
    selected_concepts.csv) or a curated instance list gives volume while
    training refusal to generalize across surface variation, not memorize
    one fixed phrase.
"""

ABSTENTION_TOKEN = "UNANSWERABLE"

FIXED = [
    {
        "id": "unans_admitting_vs_attending",
        "excluded_concept": "Encounter.participant only ever has one entry (typed 'primary performer'); admitting/attending/consulting are not distinguishable roles in this schema",
        "questions": [
            ("physician", "Who was the admitting physician, as distinct from the attending physician, for this encounter?"),
            ("admission_clerk", "I need the admitting physician's name specifically, not just whoever is listed as the provider -- who was it?"),
            ("hospital_ceo", "For this stay, who was the attending physician versus the consulting physician?"),
            ("icu_manager", "Which physician admitted this patient, as opposed to the one who's currently attending?"),
        ],
    },
    {
        "id": "unans_nationality",
        "excluded_concept": "no nationality/country-of-origin field exists anywhere in this data (Synthea only generates US-based synthetic patients with state/city addresses)",
        "questions": [
            ("admission_clerk", "What is this patient's nationality?"),
            ("hospital_ceo", "How many of our patients are foreign nationals versus US citizens?"),
            ("population_health_analyst", "Can you break down our patient population by country of origin?"),
            ("admission_clerk", "What passport country does this patient hold?"),
        ],
    },
    {
        "id": "unans_future_appointment",
        "excluded_concept": "Synthea only generates completed historical encounters up to the frozen reference date; there is no scheduled/future-dated encounter data anywhere",
        "questions": [
            ("outpatient_clerk", "When is this patient's next scheduled appointment?"),
            ("admission_clerk", "Does this patient have any upcoming visits booked?"),
            ("outpatient_clerk", "What appointments do we have scheduled for next week?"),
            ("physician", "When is my next follow-up with this patient?"),
        ],
    },
    {
        "id": "unans_department_assignment",
        "excluded_concept": "no department/ward/service-line concept exists anywhere in the schema (FHIR/Synthea doesn't model hospital departments as a resource)",
        "questions": [
            ("admission_clerk", "Which department is this patient currently assigned to?"),
            ("hospital_ceo", "How many patients are currently in the cardiology department versus oncology?"),
            ("icu_manager", "What ward is this patient on?"),
            ("ed_manager", "Which service line handled this case?"),
        ],
    },
    {
        "id": "unans_facility_address",
        "excluded_concept": "no facility/location table exists in the core schema (Location data was not promoted from the extra_ tables)",
        "questions": [
            ("admission_clerk", "What is the address of the facility where this encounter took place?"),
            ("hospital_ceo", "Which of our facility locations saw the most encounters this year?"),
            ("outpatient_clerk", "What room or building was this appointment held in?"),
            ("finance_reviewer", "Break down encounter volume by facility address."),
        ],
    },
    {
        "id": "unans_care_team_roles",
        "excluded_concept": "encounter has a single participant_name field only; there is no multi-provider care-team-with-roles structure in the schema",
        "questions": [
            ("nurse", "List everyone on this patient's care team, along with their roles."),
            ("icu_manager", "Who besides the primary physician is involved in this patient's care?"),
            ("physician", "Show me the full care team assigned to this patient, with each person's role."),
            ("nurse", "Which nurses, specialists, and consultants are on this patient's care team?"),
        ],
    },
    {
        "id": "unans_provenance",
        "excluded_concept": "no audit-trail/provenance data (who last modified a record and when) exists in the core schema",
        "questions": [
            ("hospital_ceo", "Who last modified this patient's record, and when?"),
            ("infection_control_officer", "What's the audit trail for changes to this patient's chart?"),
            ("admission_clerk", "When was this record last updated, and by whom?"),
            ("population_health_analyst", "Show me the edit history for this diagnosis entry."),
        ],
    },
    {
        "id": "unans_radiology_department",
        "excluded_concept": "imaging_study has no department/ordering-service field; no department concept exists anywhere in the schema",
        "questions": [
            ("ed_manager", "Which department ordered this imaging study?"),
            ("finance_reviewer", "Break down imaging study volume by ordering department."),
            ("hospital_ceo", "Which service line orders the most radiology studies?"),
            ("ed_manager", "Was this X-ray ordered by the ED or by an inpatient team?"),
        ],
    },
    {
        "id": "unans_practitioner_specialty",
        "excluded_concept": "only participant_name/npi and requester_name/npi are captured; no specialty, qualification, or license field exists for practitioners",
        "questions": [
            ("admission_clerk", "What is this physician's medical specialty?"),
            ("hospital_ceo", "How many of our physicians are board-certified in cardiology?"),
            ("outpatient_clerk", "Is this doctor a specialist or a general practitioner?"),
            ("finance_reviewer", "Break down our physicians by specialty."),
        ],
    },
]

# (persona, question_template) pairs reused across all parameterized categories below
PARAMETERIZED_TEMPLATES = {
    "unans_claim_amount": [
        ("finance_reviewer", "How much was billed for this patient's {concept}?"),
        ("hospital_ceo", "What's the total claim amount for {concept} treatment this year?"),
        ("finance_reviewer", "What did we charge the insurer for {concept}?"),
        ("hospital_ceo", "Show me the average reimbursement for {concept}."),
    ],
    "unans_claim_status": [
        ("finance_reviewer", "Was the claim for this patient's {concept} approved or rejected?"),
        ("hospital_ceo", "How many {concept} claims are still pending with the insurer?"),
        ("finance_reviewer", "What's the denial rate on claims involving {concept}?"),
        ("finance_reviewer", "Which {concept} claims were resubmitted after rejection?"),
    ],
    "unans_document_content": [
        ("physician", "What does the clinical note say about this patient's {concept}?"),
        ("nurse", "Summarize the discharge summary's notes on {concept}."),
        ("physician", "What did the consulting note recommend regarding {concept}?"),
        ("population_health_analyst", "What free-text details exist about {concept} in the clinical documentation?"),
    ],
    "unans_medication_administration_actual": [
        ("nurse", "Was {concept} actually administered to the patient, and at what time?"),
        ("pharmacist", "Confirm whether the {concept} dose was given as ordered, not just prescribed."),
        ("nurse", "Which nurse administered the {concept} dose?"),
        ("pharmacist", "Was there a discrepancy between the {concept} order and what was actually given?"),
    ],
    "unans_pharmacy_stock": [
        ("pharmacist", "How many units of {concept} do we currently have in pharmacy stock?"),
        ("finance_reviewer", "What's our current inventory level for {concept}?"),
        ("pharmacist", "Do we need to reorder {concept} based on current stock?"),
        ("pharmacist", "How many {concept} units were used from inventory this month?"),
    ],
    "unans_device_implanted": [
        ("physician", "Does this patient have a {concept} implanted?"),
        ("nurse", "How many of our patients currently have a {concept}?"),
        ("physician", "When was the {concept} implanted, and by which surgeon?"),
        ("population_health_analyst", "Break down patients by whether they have a {concept}."),
    ],
    "unans_insurance_payer": [
        ("admission_clerk", "Is this patient covered by {concept}?"),
        ("finance_reviewer", "How many of our patients are insured through {concept}?"),
        ("admission_clerk", "What's this patient's {concept} policy number?"),
        ("finance_reviewer", "What's our reimbursement rate from {concept}?"),
    ],
    "unans_department_by_name": [
        ("hospital_ceo", "How many patients are currently in the {concept} department?"),
        ("admission_clerk", "Which patients are assigned to {concept}?"),
        ("finance_reviewer", "What's the average length of stay for patients in {concept}?"),
        ("hospital_ceo", "How is the {concept} department performing this quarter?"),
    ],
    "unans_supply_inventory": [
        ("pharmacist", "How many {concept} do we have in stock?"),
        ("finance_reviewer", "What's our current inventory count for {concept}?"),
        ("nurse", "Do we need to reorder {concept}?"),
        ("finance_reviewer", "How many {concept} were used this month?"),
    ],
}

# Curated instance lists for categories that aren't concept-bank-derived
DEVICE_TYPES = [
    "pacemaker", "cochlear implant", "artificial hip", "coronary stent", "insulin pump",
    "implantable defibrillator", "prosthetic knee", "dental implant", "intrauterine device",
    "hearing aid", "spinal fusion hardware", "breast implant", "ventricular assist device",
    "arterial graft", "corneal implant", "penile implant", "orthopedic screw",
    "gastric band", "artificial heart valve", "nerve stimulator",
]

INSURANCE_PAYERS = [
    "Blue Cross Blue Shield", "Aetna", "UnitedHealthcare", "Cigna", "Daman", "Medicare",
    "Medicaid", "Humana", "Kaiser Permanente", "AXA", "Bupa", "MetLife", "Allianz",
    "Anthem", "Molina Healthcare",
]

DEPARTMENT_NAMES = [
    "cardiology", "radiology", "oncology", "pediatrics", "emergency", "intensive care",
    "orthopedics", "dermatology", "neurology", "psychiatry", "obstetrics", "urology",
    "ENT", "ophthalmology", "general surgery",
]

SUPPLY_ITEMS = [
    "surgical gauze", "syringes", "IV bags", "surgical masks", "examination gloves",
    "sutures", "urinary catheters", "adhesive bandages", "antiseptic wipes",
    "blood collection tubes", "surgical gowns", "N95 respirators", "wound dressings",
    "IV cannulas", "oxygen masks",
]
