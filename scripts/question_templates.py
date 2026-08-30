"""
Question templates, parameterized version of back_translations_batch1.py.

Batch 1 hand-composed 160 questions (one concept per archetype) to validate
phrasing quality. These are the same 160 sentences, with the specific concept
name replaced by a {concept} placeholder (and {threshold} where the archetype
needs a numeric cutoff) -- so the same carefully-written, persona-appropriate
phrasing can be instantiated across every concept an archetype applies to,
not just the one concept used in batch 1.

`clean_concept()` strips the FHIR-style trailing qualifier ("(disorder)",
"(finding)", "(procedure)", etc.) that isn't natural in a spoken question.
"""
import re

QUALIFIER_SUFFIX_RE = re.compile(r"\s*\((disorder|finding|situation|procedure|substance|organism|regime/therapy|environment)\)\s*$", re.IGNORECASE)


def clean_concept(display):
    cleaned = QUALIFIER_SUFFIX_RE.sub("", display).strip()
    # Some raw Synthea concept display names have double-space artifacts baked
    # in (e.g. "sealant  per tooth" -- a source-data quirk, not something
    # introduced by templating). Collapse before use.
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    # All templates place {concept} mid-sentence (never sentence-initial), so
    # lowercasing the first letter reads naturally ("a mold allergy", not
    # "a Mold allergy") without needing per-template position tracking --
    # EXCEPT when the first word is an acronym (HIV, MMR, COVID...), where
    # lowercasing the first letter alone would produce "hIV" instead of
    # leaving it as "HIV" or fully lowercasing to "hiv".
    if len(cleaned) >= 2 and cleaned[0].isupper() and cleaned[1].isupper():
        # First two characters both uppercase -> treat as acronym-led (HIV,
        # MMR, SARS-CoV-2...) and leave capitalization alone. A whole-first-
        # word .isupper() check isn't enough: "SARS-CoV-2" fails that (the
        # embedded lowercase o/v in "CoV") despite clearly being acronym-led.
        pass
    elif cleaned:
        cleaned = cleaned[0].lower() + cleaned[1:]
    return cleaned


def fix_articles(question):
    """Fix 'a <vowel-starting word>' -> 'an <vowel-starting word>' after
    template substitution -- general post-process, not template-specific."""
    return re.sub(r"\ba (?=[aeiouAEIOU])", "an ", question)


def extract_threshold(sql):
    m = re.search(r"valueQuantity\s*>\s*([0-9.]+)", sql)
    return m.group(1) if m else None


# archetype_id -> list of (persona, template) with {concept} and, where needed, {threshold}
TEMPLATES = {
    "t1_count_patients_with_condition": [
        ("physician", "How many of my patients have been diagnosed with {concept}?"),
        ("population_health_analyst", "What is the total number of distinct patients with a {concept} diagnosis in our records?"),
        ("hospital_ceo", "How many patients in our system have a {concept} diagnosis on file?"),
        ("physician", "Can you tell me the count of patients who have {concept} recorded in their chart?"),
    ],
    "t1_list_patients_on_medication": [
        ("pharmacist", "Which patients currently have an active prescription for {concept}?"),
        ("physician", "Give me the list of patients who are currently on {concept}."),
        ("nurse", "Who are the patients with an active order for {concept} right now?"),
        ("pharmacist", "List every patient with a currently active {concept} prescription."),
    ],
    "t1_count_patients_allergic": [
        ("nurse", "How many patients have a {concept} allergy noted in their chart?"),
        ("pharmacist", "What's the count of patients flagged with a {concept} allergy?"),
        ("physician", "How many patients in our records have been noted as having a {concept} allergy?"),
        ("nurse", "Can you tell me how many patients have '{concept}' listed as an allergy?"),
    ],
    "t1_count_immunizations_given": [
        ("nurse", "How many {concept} doses have we administered?"),
        ("population_health_analyst", "What is the total count of completed {concept} vaccine doses given?"),
        ("hospital_ceo", "How many {concept} vaccinations have we given out?"),
        ("nurse", "Total number of completed {concept} immunizations on record?"),
    ],
    "t1_list_patients_with_procedure": [
        ("physician", "Which patients have completed a {concept}?"),
        ("finance_reviewer", "List all patients with a completed {concept} procedure on file, for billing reconciliation."),
        ("outpatient_clerk", "Who are the patients that have a completed {concept} in their record?"),
        ("physician", "Give me every patient who's had a {concept} done."),
    ],
    "t1_avg_observation_value": [
        ("physician", "What's the average {concept} across all our patients?"),
        ("nurse", "On average, what {concept} are we seeing across the patient population?"),
        ("population_health_analyst", "What is the mean {concept} recorded across all patients, and in what unit?"),
        ("physician", "Across all patients, what's the average {concept}?"),
    ],
    "t1_count_diagnostic_reports": [
        ("physician", "How many {concept} reports have been generated in total?"),
        ("finance_reviewer", "What is the total count of {concept} reports on file?"),
        ("population_health_analyst", "How many {concept} reports exist in our records?"),
        ("physician", "Total number of {concept} documentation reports we have?"),
    ],
    "t1_count_encounters_of_type": [
        ("admission_clerk", "How many {concept} encounters have we recorded?"),
        ("ed_manager", "What's the total number of '{concept}' encounters logged?"),
        ("hospital_ceo", "How many {concept} visits have taken place in total?"),
        ("admission_clerk", "Total count of encounters coded as {concept}?"),
    ],
    "t2_active_condition_count": [
        ("physician", "How many patients currently have active {concept} that hasn't resolved?"),
        ("population_health_analyst", "What's the count of patients with an active {concept} diagnosis right now?"),
        ("nurse", "How many patients on our list have {concept} marked as still active?"),
        ("physician", "Give me the number of patients whose {concept} is currently active."),
    ],
    "t2_resolved_condition_count": [
        ("physician", "How many {concept} diagnoses have since resolved?"),
        ("population_health_analyst", "What is the count of {concept} cases that have a recorded resolution (abatement) date?"),
        ("physician", "Of all the {concept} diagnoses, how many have actually resolved?"),
        ("population_health_analyst", "How many {concept} diagnoses in our data show an abatement date, meaning they were resolved?"),
    ],
    "t2_condition_diagnoses_by_year": [
        ("population_health_analyst", "How many new {concept} diagnoses were recorded each year?"),
        ("hospital_ceo", "Can you break down the number of new {concept} diagnoses by year?"),
        ("population_health_analyst", "Show me the yearly trend of new {concept} diagnoses."),
        ("hospital_ceo", "Year by year, how many {concept} cases were newly diagnosed?"),
    ],
    "t2_medication_status_breakdown": [
        ("pharmacist", "For {concept}, how many prescriptions are active versus stopped versus completed?"),
        ("finance_reviewer", "Break down {concept} prescription counts by status."),
        ("pharmacist", "What's the status breakdown -- active, stopped, completed -- for {concept} orders?"),
        ("finance_reviewer", "Give me the prescription status distribution for {concept}."),
    ],
    "t2_medication_by_year": [
        ("pharmacist", "How many {concept} prescriptions were written each year?"),
        ("finance_reviewer", "Show me {concept} prescription volume by year."),
        ("hospital_ceo", "Year over year, how many {concept} orders have we issued?"),
        ("pharmacist", "Break down the count of {concept} prescriptions by the year they were authored."),
    ],
    "t2_observation_high_values": [
        ("physician", "How many {concept} readings came back above {threshold}, and what's their average?"),
        ("nurse", "For {concept} over {threshold}, how many are there and what's the average value?"),
        ("physician", "What's the count and average of {concept} results exceeding {threshold}?"),
        ("nurse", "How many patients had a {concept} reading above {threshold}, and what was the average of those readings?"),
    ],
    "t2_observation_by_year": [
        ("physician", "How has the average {concept} trended by year across our patients?"),
        ("population_health_analyst", "Show me the average {concept} broken down by year."),
        ("physician", "What was the average {concept} reading for each year on record?"),
        ("population_health_analyst", "Give me a year-by-year average of {concept} results."),
    ],
    "t2_procedure_by_year": [
        ("finance_reviewer", "How many {concept} procedures were performed each year?"),
        ("hospital_ceo", "Break down {concept} volume by year."),
        ("outpatient_clerk", "Year by year, how many {concept} procedures have we done?"),
        ("finance_reviewer", "Show annual counts of completed {concept} procedures."),
    ],
    "t2_allergy_criticality_breakdown": [
        ("nurse", "For patients with a {concept} allergy noted, how do they break down by criticality level?"),
        ("pharmacist", "What's the criticality distribution for patients flagged with a {concept} allergy?"),
        ("physician", "How many patients with a {concept} allergy fall into each criticality category?"),
        ("nurse", "Break down patients with a {concept} allergy by how critical it's marked."),
    ],
    "t2_careplan_active_duration": [
        ("admission_clerk", "For {concept} encounters, how many are in each status -- finished, in-progress, etc.?"),
        ("ed_manager", "Break down {concept} encounters by their status."),
        ("icu_manager", "What's the status breakdown of {concept} encounters?"),
        ("admission_clerk", "How many {concept} visits are finished versus still in progress?"),
    ],
    "t3_condition_by_gender": [
        ("population_health_analyst", "How does the {concept} patient count break down by gender?"),
        ("hospital_ceo", "Of our patients with {concept}, what's the split between male and female?"),
        ("population_health_analyst", "Show me {concept} diagnosis counts split out by patient gender."),
        ("hospital_ceo", "How many male versus female patients have a {concept} diagnosis?"),
    ],
    "t3_condition_over_age": [
        ("population_health_analyst", "How many patients were 65 or older when diagnosed with {concept}?"),
        ("physician", "Of the patients with {concept}, how many were age 65 or above at diagnosis?"),
        ("population_health_analyst", "How many {concept} patients were seniors, 65 or older, at the time of diagnosis?"),
        ("physician", "Count of patients aged 65 and older who have a {concept} diagnosis."),
    ],
    "t3_condition_avg_observation": [
        ("physician", "What's the average body weight of patients who have {concept}?"),
        ("population_health_analyst", "Among patients diagnosed with {concept}, what is their mean recorded body weight?"),
        ("physician", "For our {concept} patients, what's their average weight?"),
        ("population_health_analyst", "What is the average body weight for the {concept} patient cohort?"),
    ],
    "t3_medication_and_condition": [
        ("pharmacist", "How many patients on {concept} also have a hypertension diagnosis?"),
        ("physician", "Of the patients prescribed {concept}, how many also have essential hypertension?"),
        ("pharmacist", "Count of patients taking {concept} who are also hypertensive."),
        ("physician", "How many of my hypertensive patients are also on {concept}?"),
    ],
    "t3_procedure_with_encounter_type": [
        ("finance_reviewer", "Break down {concept} procedures by the type of encounter they occurred in."),
        ("ed_manager", "In which encounter types is {concept} being performed, and how often?"),
        ("outpatient_clerk", "Show me {concept} counts grouped by visit/encounter type."),
        ("finance_reviewer", "What encounter types are associated with {concept}, and how many each?"),
    ],
    "t3_immunization_by_gender": [
        ("population_health_analyst", "How does {concept} vaccine uptake break down by gender?"),
        ("nurse", "How many male versus female patients received the {concept} vaccine?"),
        ("population_health_analyst", "Show {concept} recipient counts split by gender."),
        ("nurse", "What's the gender breakdown of patients who got the {concept} vaccine?"),
    ],
    "t3_avg_procedures_per_patient_with_condition": [
        ("finance_reviewer", "On average, how many procedures does a patient with {concept} undergo?"),
        ("physician", "For patients diagnosed with {concept}, what's the average number of procedures they've had?"),
        ("hospital_ceo", "What's the average procedure count per patient among those with a {concept} diagnosis?"),
        ("finance_reviewer", "How many procedures, on average, do our {concept} patients receive?"),
    ],
    "t3_diagnostic_report_with_condition": [
        ("physician", "How many {concept} reports were generated for patients with hypertension?"),
        ("population_health_analyst", "What's the count of {concept} reports created for our hypertensive patient population?"),
        ("physician", "For patients with essential hypertension, how many {concept} reports exist?"),
        ("population_health_analyst", "How many {concept} reports belong to patients diagnosed with hypertension?"),
    ],
    "t3_observation_and_medication": [
        ("physician", "How many patients with a {concept} above {threshold} are also on lisinopril?"),
        ("pharmacist", "What's the count of patients taking lisinopril whose {concept} reading exceeded {threshold}?"),
        ("physician", "Of patients with elevated {concept}, above {threshold}, how many are prescribed lisinopril?"),
        ("pharmacist", "How many lisinopril patients also have a {concept} over {threshold} recorded?"),
    ],
    "t3_allergy_and_condition_count": [
        ("nurse", "How many patients with a {concept} allergy also have anemia?"),
        ("physician", "Of the patients flagged with a {concept} allergy, how many are also anemic?"),
        ("nurse", "What's the count of patients who have both a {concept} allergy and an anemia diagnosis?"),
        ("physician", "How many anemic patients also have a {concept} allergy noted?"),
    ],
    "t3_condition_encounter_count": [
        ("physician", "On average, how many encounters does a patient with {concept} have?"),
        ("hospital_ceo", "What's the average number of visits or encounters for our {concept} patients?"),
        ("finance_reviewer", "What's the average encounter count per patient among those diagnosed with {concept}?"),
        ("physician", "How many encounters, on average, do {concept} patients accumulate?"),
    ],
    "t3_medication_by_encounter_class": [
        ("pharmacist", "Break down {concept} prescriptions by the encounter class they were ordered in."),
        ("ed_manager", "In which encounter classes -- ambulatory, emergency, etc. -- are {concept} orders written, and how many?"),
        ("finance_reviewer", "Show {concept} prescription counts grouped by encounter class."),
        ("pharmacist", "What encounter class is most associated with {concept} prescriptions?"),
    ],
    "t3_procedure_avg_patient_age": [
        ("physician", "What's the average age of patients when they undergo a {concept}?"),
        ("population_health_analyst", "What is the mean patient age at the time of {concept}?"),
        ("physician", "On average, how old are patients when they get a {concept}?"),
        ("population_health_analyst", "What is the average patient age at {concept}?"),
    ],
    "t4_observation_first_vs_last": [
        ("physician", "For each patient, how has their {concept} changed between their first and most recent reading?"),
        ("population_health_analyst", "Show the change in {concept} from each patient's earliest to latest recorded value."),
        ("physician", "What's the difference between each patient's first and last {concept}?"),
        ("population_health_analyst", "For every patient, compute the delta between their initial and most recent {concept} result."),
    ],
    "t4_most_recent_observation_per_patient": [
        ("physician", "For my hypertensive patients, what is each one's most recent {concept}?"),
        ("nurse", "Show the latest {concept} reading for every patient who has hypertension."),
        ("physician", "What's the most recent {concept} result on file for each hypertensive patient?"),
        ("nurse", "Give me each hypertensive patient's newest {concept} reading."),
    ],
    "t4_condition_then_procedure_30d": [
        ("physician", "Which patients diagnosed with {concept} went on to have a colonoscopy within 90 days?"),
        ("population_health_analyst", "List patients whose {concept} diagnosis was followed by a colonoscopy within the next 90 days."),
        ("physician", "Of the {concept} patients, who had a colonoscopy performed within 3 months of diagnosis?"),
        ("population_health_analyst", "Show patients where a colonoscopy occurred within 90 days after their {concept} diagnosis."),
    ],
    "t4_top5_patients_by_medication_count": [
        ("pharmacist", "Who are the top 5 patients with the most {concept} prescriptions?"),
        ("physician", "Which 5 patients have been prescribed {concept} the most times?"),
        ("pharmacist", "List the 5 patients with the highest number of {concept} orders."),
        ("physician", "Top 5 patients by count of {concept} prescriptions -- who are they?"),
    ],
    "t4_patients_with_3plus_encounters_12mo": [
        ("ed_manager", "Which patients had 3 or more '{concept}' visits in the same year?"),
        ("hospital_ceo", "Show patients with 3 or more {concept} encounters within a single year -- possible high utilizers."),
        ("icu_manager", "Who are the patients with 3 or more {concept} visits in one calendar year?"),
        ("ed_manager", "List patients and the year in which they had 3 or more {concept} encounters."),
    ],
    "t4_top5_patients_by_condition_recurrence": [
        ("physician", "Which 5 patients have had {concept} diagnosed the most times?"),
        ("population_health_analyst", "Who are the top 5 patients by number of recorded {concept} diagnoses?"),
        ("physician", "List the 5 patients with the most recurrences of a {concept} diagnosis."),
        ("population_health_analyst", "Top 5 patients ranked by how many times {concept} was diagnosed?"),
    ],
    "t4_time_from_condition_to_medication": [
        ("physician", "On average, how long after a {concept} diagnosis do patients start on lisinopril?"),
        ("pharmacist", "What's the average time between a patient's {concept} diagnosis and their first lisinopril prescription?"),
        ("physician", "How many days, on average, pass between diagnosing {concept} and starting lisinopril?"),
        ("pharmacist", "What's the average days-to-treatment from {concept} diagnosis to first lisinopril order?"),
    ],
    "t4_observation_trend_yearly_delta": [
        ("hospital_ceo", "How has the average {concept} changed year over year?"),
        ("population_health_analyst", "Show the year-over-year change in average {concept}."),
        ("hospital_ceo", "What's the yearly trend and change in mean {concept}?"),
        ("population_health_analyst", "Give me the average {concept} by year along with the change from the prior year."),
    ],
    "t4_first_diagnosis_age_per_patient": [
        ("physician", "What was the age at first {concept} diagnosis for the 5 oldest patients diagnosed?"),
        ("population_health_analyst", "Show the 5 patients who were oldest at the time of their first {concept} diagnosis, with their age."),
        ("physician", "Who were the oldest 5 patients when first diagnosed with {concept}, and how old were they?"),
        ("population_health_analyst", "List the top 5 oldest ages at first {concept} diagnosis, by patient."),
    ],
}
