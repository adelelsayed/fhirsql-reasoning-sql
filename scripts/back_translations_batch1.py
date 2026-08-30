"""
Back-translation, batch 1.

Covers all 40 archetypes (one representative concept each, per
data/training/batch1_sample.jsonl) x 4 persona-varied natural-language
questions = 160 rows. First proof-of-pipeline batch; more concepts per
archetype follow in later batches once this batch's quality is confirmed.

Each question is written to match the SQL's actual filters precisely (no
dropped/added filters) -- e.g. t2_active_condition_count's SQL filters on
clinical_status='active', so every paraphrase for it explicitly says
"active"/"currently"/"not resolved", never just "have gingivitis" (that
phrasing belongs to t1_count_patients_with_condition instead, which has no
status filter).
"""

# archetype_id -> list of (persona, question) pairs
PARAPHRASES = {
    "t1_count_patients_with_condition": [
        ("physician", "How many of my patients have been diagnosed with gingivitis?"),
        ("population_health_analyst", "What is the total number of distinct patients with a gingivitis diagnosis in our records?"),
        ("hospital_ceo", "How many patients in our system have a gingivitis diagnosis on file?"),
        ("physician", "Can you tell me the count of patients who have gingivitis recorded in their chart?"),
    ],
    "t1_list_patients_on_medication": [
        ("pharmacist", "Which patients currently have an active prescription for Acetaminophen 325 MG oral tablets?"),
        ("physician", "Give me the list of patients who are currently on Acetaminophen 325 mg tablets."),
        ("nurse", "Who are the patients with an active order for Acetaminophen 325 MG tablets right now?"),
        ("pharmacist", "List every patient with a currently active Acetaminophen 325 MG oral tablet prescription."),
    ],
    "t1_count_patients_allergic": [
        ("nurse", "How many patients have a general allergic disposition noted in their chart?"),
        ("pharmacist", "What's the count of patients flagged with an allergic disposition finding?"),
        ("physician", "How many patients in our records have been noted as having an allergic disposition?"),
        ("nurse", "Can you tell me how many patients have 'allergic disposition' listed as an allergy?"),
    ],
    "t1_count_immunizations_given": [
        ("nurse", "How many trivalent influenza (split virus, preservative-free) doses have we administered?"),
        ("population_health_analyst", "What is the total count of completed trivalent flu vaccine (split virus, PF) doses given?"),
        ("hospital_ceo", "How many flu shots -- specifically the trivalent split-virus preservative-free formulation -- have we given out?"),
        ("nurse", "Total number of completed influenza (trivalent, split virus, PF) immunizations on record?"),
    ],
    "t1_list_patients_with_procedure": [
        ("physician", "Which patients have completed a depression screening?"),
        ("finance_reviewer", "List all patients with a completed depression screening procedure on file, for billing reconciliation."),
        ("outpatient_clerk", "Who are the patients that have a completed depression screening in their record?"),
        ("physician", "Give me every patient who's had a depression screening done."),
    ],
    "t1_avg_observation_value": [
        ("physician", "What's the average platelet count across all our patients?"),
        ("nurse", "On average, what platelet count are we seeing across the patient population?"),
        ("population_health_analyst", "What is the mean platelet count (automated count) recorded across all patients, and in what unit?"),
        ("physician", "Across all patients, what's the average automated platelet count?"),
    ],
    "t1_count_diagnostic_reports": [
        ("physician", "How many history and physical notes have been generated in total?"),
        ("finance_reviewer", "What is the total count of History and Physical note reports on file?"),
        ("population_health_analyst", "How many H&P (history and physical) reports exist in our records?"),
        ("physician", "Total number of history-and-physical documentation reports we have?"),
    ],
    "t1_count_encounters_of_type": [
        ("admission_clerk", "How many general examination encounters have we recorded?"),
        ("ed_manager", "What's the total number of 'general examination of patient' encounters logged?"),
        ("hospital_ceo", "How many general patient examination visits have taken place in total?"),
        ("admission_clerk", "Total count of encounters coded as a general examination of the patient?"),
    ],
    "t2_active_condition_count": [
        ("physician", "How many patients currently have active gingivitis that hasn't resolved?"),
        ("population_health_analyst", "What's the count of patients with an active gingivitis diagnosis right now?"),
        ("nurse", "How many patients on our list have gingivitis marked as still active?"),
        ("physician", "Give me the number of patients whose gingivitis is currently active."),
    ],
    "t2_resolved_condition_count": [
        ("physician", "How many gingivitis diagnoses have since resolved?"),
        ("population_health_analyst", "What is the count of gingivitis cases that have a recorded resolution (abatement) date?"),
        ("physician", "Of all the gingivitis diagnoses, how many have actually resolved?"),
        ("population_health_analyst", "How many gingivitis diagnoses in our data show an abatement date, meaning they were resolved?"),
    ],
    "t2_condition_diagnoses_by_year": [
        ("population_health_analyst", "How many new gingivitis diagnoses were recorded each year?"),
        ("hospital_ceo", "Can you break down the number of new gingivitis diagnoses by year?"),
        ("population_health_analyst", "Show me the yearly trend of new gingivitis diagnoses."),
        ("hospital_ceo", "Year by year, how many gingivitis cases were newly diagnosed?"),
    ],
    "t2_medication_status_breakdown": [
        ("pharmacist", "For Acetaminophen 325 MG tablets, how many prescriptions are active versus stopped versus completed?"),
        ("finance_reviewer", "Break down Acetaminophen 325 MG prescription counts by status."),
        ("pharmacist", "What's the status breakdown -- active, stopped, completed -- for Acetaminophen 325 mg orders?"),
        ("finance_reviewer", "Give me the prescription status distribution for Acetaminophen 325 MG oral tablets."),
    ],
    "t2_medication_by_year": [
        ("pharmacist", "How many Acetaminophen 325 MG prescriptions were written each year?"),
        ("finance_reviewer", "Show me Acetaminophen 325 MG prescription volume by year."),
        ("hospital_ceo", "Year over year, how many Acetaminophen 325 mg orders have we issued?"),
        ("pharmacist", "Break down the count of Acetaminophen 325 MG prescriptions by the year they were authored."),
    ],
    "t2_observation_high_values": [
        ("physician", "How many platelet readings came back above 370, and what's their average?"),
        ("nurse", "For platelet counts over 370, how many are there and what's the average value?"),
        ("physician", "What's the count and average of platelet results exceeding 370?"),
        ("nurse", "How many patients had a platelet reading above 370, and what was the average of those readings?"),
    ],
    "t2_observation_by_year": [
        ("physician", "How has the average platelet count trended by year across our patients?"),
        ("population_health_analyst", "Show me the average platelet count broken down by year."),
        ("physician", "What was the average platelet reading for each year on record?"),
        ("population_health_analyst", "Give me a year-by-year average of platelet count results."),
    ],
    "t2_procedure_by_year": [
        ("finance_reviewer", "How many depression screenings were performed each year?"),
        ("hospital_ceo", "Break down depression screening volume by year."),
        ("outpatient_clerk", "Year by year, how many depression screenings have we done?"),
        ("finance_reviewer", "Show annual counts of completed depression screening procedures."),
    ],
    "t2_allergy_criticality_breakdown": [
        ("nurse", "For patients with an allergic disposition noted, how do they break down by criticality level?"),
        ("pharmacist", "What's the criticality distribution for patients flagged with allergic disposition?"),
        ("physician", "How many patients with allergic disposition fall into each criticality category?"),
        ("nurse", "Break down patients with an allergic-disposition allergy by how critical it's marked."),
    ],
    "t2_careplan_active_duration": [
        ("admission_clerk", "For general examination encounters, how many are in each status -- finished, in-progress, etc.?"),
        ("ed_manager", "Break down general-examination encounters by their status."),
        ("icu_manager", "What's the status breakdown of general examination of patient encounters?"),
        ("admission_clerk", "How many general examination visits are finished versus still in progress?"),
    ],
    "t3_condition_by_gender": [
        ("population_health_analyst", "How does the gingivitis patient count break down by gender?"),
        ("hospital_ceo", "Of our patients with gingivitis, what's the split between male and female?"),
        ("population_health_analyst", "Show me gingivitis diagnosis counts split out by patient gender."),
        ("hospital_ceo", "How many male versus female patients have a gingivitis diagnosis?"),
    ],
    "t3_condition_over_age": [
        ("population_health_analyst", "How many patients were 65 or older when diagnosed with gingivitis?"),
        ("physician", "Of the patients with gingivitis, how many were age 65 or above at diagnosis?"),
        ("population_health_analyst", "How many gingivitis patients were seniors, 65 or older, at the time of diagnosis?"),
        ("physician", "Count of patients aged 65 and older who have a gingivitis diagnosis."),
    ],
    "t3_condition_avg_observation": [
        ("physician", "What's the average body weight of patients who have gingivitis?"),
        ("population_health_analyst", "Among patients diagnosed with gingivitis, what is their mean recorded body weight?"),
        ("physician", "For our gingivitis patients, what's their average weight?"),
        ("population_health_analyst", "What is the average body weight for the gingivitis patient cohort?"),
    ],
    "t3_medication_and_condition": [
        ("pharmacist", "How many patients on Acetaminophen 325 MG also have a hypertension diagnosis?"),
        ("physician", "Of the patients prescribed Acetaminophen 325 mg, how many also have essential hypertension?"),
        ("pharmacist", "Count of patients taking Acetaminophen 325 MG tablets who are also hypertensive."),
        ("physician", "How many of my hypertensive patients are also on Acetaminophen 325 MG?"),
    ],
    "t3_procedure_with_encounter_type": [
        ("finance_reviewer", "Break down depression screenings by the type of encounter they occurred in."),
        ("ed_manager", "In which encounter types are depression screenings being performed, and how often?"),
        ("outpatient_clerk", "Show me depression screening counts grouped by visit/encounter type."),
        ("finance_reviewer", "What encounter types are associated with depression screening procedures, and how many each?"),
    ],
    "t3_immunization_by_gender": [
        ("population_health_analyst", "How does trivalent flu vaccine (split virus, PF) uptake break down by gender?"),
        ("nurse", "How many male versus female patients received the trivalent influenza (split virus, PF) vaccine?"),
        ("population_health_analyst", "Show flu vaccine (trivalent, PF) recipient counts split by gender."),
        ("nurse", "What's the gender breakdown of patients who got the trivalent split-virus flu shot?"),
    ],
    "t3_avg_procedures_per_patient_with_condition": [
        ("finance_reviewer", "On average, how many procedures does a patient with gingivitis undergo?"),
        ("physician", "For patients diagnosed with gingivitis, what's the average number of procedures they've had?"),
        ("hospital_ceo", "What's the average procedure count per patient among those with a gingivitis diagnosis?"),
        ("finance_reviewer", "How many procedures, on average, do our gingivitis patients receive?"),
    ],
    "t3_diagnostic_report_with_condition": [
        ("physician", "How many history and physical notes were generated for patients with hypertension?"),
        ("population_health_analyst", "What's the count of H&P reports created for our hypertensive patient population?"),
        ("physician", "For patients with essential hypertension, how many history-and-physical notes exist?"),
        ("population_health_analyst", "How many History and Physical note reports belong to patients diagnosed with hypertension?"),
    ],
    "t3_observation_and_medication": [
        ("physician", "How many patients with a platelet count above 370 are also on lisinopril?"),
        ("pharmacist", "What's the count of patients taking lisinopril whose platelet count reading exceeded 370?"),
        ("physician", "Of patients with elevated platelets, above 370, how many are prescribed lisinopril?"),
        ("pharmacist", "How many lisinopril patients also have a platelet count over 370 recorded?"),
    ],
    "t3_allergy_and_condition_count": [
        ("nurse", "How many patients with an allergic disposition also have anemia?"),
        ("physician", "Of the patients flagged with allergic disposition, how many are also anemic?"),
        ("nurse", "What's the count of patients who have both an allergic-disposition allergy and an anemia diagnosis?"),
        ("physician", "How many anemic patients also have an allergic disposition noted?"),
    ],
    "t3_condition_encounter_count": [
        ("physician", "On average, how many encounters does a patient with gingivitis have?"),
        ("hospital_ceo", "What's the average number of visits or encounters for our gingivitis patients?"),
        ("finance_reviewer", "What's the average encounter count per patient among those diagnosed with gingivitis?"),
        ("physician", "How many encounters, on average, do gingivitis patients accumulate?"),
    ],
    "t3_medication_by_encounter_class": [
        ("pharmacist", "Break down Acetaminophen 325 MG prescriptions by the encounter class they were ordered in."),
        ("ed_manager", "In which encounter classes -- ambulatory, emergency, etc. -- are Acetaminophen 325 mg orders written, and how many?"),
        ("finance_reviewer", "Show Acetaminophen 325 MG prescription counts grouped by encounter class."),
        ("pharmacist", "What encounter class is most associated with Acetaminophen 325 MG prescriptions?"),
    ],
    "t3_procedure_avg_patient_age": [
        ("physician", "What's the average age of patients when they undergo a depression screening?"),
        ("population_health_analyst", "What is the mean patient age at the time of depression screening?"),
        ("physician", "On average, how old are patients when they get screened for depression?"),
        ("population_health_analyst", "What is the average patient age at depression screening?"),
    ],
    "t4_observation_first_vs_last": [
        ("physician", "For each patient, how has their platelet count changed between their first and most recent reading?"),
        ("population_health_analyst", "Show the change in platelet count from each patient's earliest to latest recorded value."),
        ("physician", "What's the difference between each patient's first and last platelet count?"),
        ("population_health_analyst", "For every patient, compute the delta between their initial and most recent platelet result."),
    ],
    "t4_most_recent_observation_per_patient": [
        ("physician", "For my hypertensive patients, what is each one's most recent platelet count?"),
        ("nurse", "Show the latest platelet reading for every patient who has hypertension."),
        ("physician", "What's the most recent platelet result on file for each hypertensive patient?"),
        ("nurse", "Give me each hypertensive patient's newest platelet count reading."),
    ],
    "t4_condition_then_procedure_30d": [
        ("physician", "Which patients diagnosed with gingivitis went on to have a colonoscopy within 90 days?"),
        ("population_health_analyst", "List patients whose gingivitis diagnosis was followed by a colonoscopy within the next 90 days."),
        ("physician", "Of the gingivitis patients, who had a colonoscopy performed within 3 months of diagnosis?"),
        ("population_health_analyst", "Show patients where a colonoscopy occurred within 90 days after their gingivitis diagnosis."),
    ],
    "t4_top5_patients_by_medication_count": [
        ("pharmacist", "Who are the top 5 patients with the most Acetaminophen 325 MG prescriptions?"),
        ("physician", "Which 5 patients have been prescribed Acetaminophen 325 mg the most times?"),
        ("pharmacist", "List the 5 patients with the highest number of Acetaminophen 325 MG orders."),
        ("physician", "Top 5 patients by count of Acetaminophen 325 MG prescriptions -- who are they?"),
    ],
    "t4_patients_with_3plus_encounters_12mo": [
        ("ed_manager", "Which patients had 3 or more 'encounter for problem' visits in the same year?"),
        ("hospital_ceo", "Show patients with 3 or more problem-related encounters within a single year -- possible high utilizers."),
        ("icu_manager", "Who are the patients with 3 or more encounter-for-problem visits in one calendar year?"),
        ("ed_manager", "List patients and the year in which they had 3 or more problem encounters."),
    ],
    "t4_top5_patients_by_condition_recurrence": [
        ("physician", "Which 5 patients have had gingivitis diagnosed the most times?"),
        ("population_health_analyst", "Who are the top 5 patients by number of recorded gingivitis diagnoses?"),
        ("physician", "List the 5 patients with the most recurrences of a gingivitis diagnosis."),
        ("population_health_analyst", "Top 5 patients ranked by how many times gingivitis was diagnosed?"),
    ],
    "t4_time_from_condition_to_medication": [
        ("physician", "On average, how long after a gingivitis diagnosis do patients start on lisinopril?"),
        ("pharmacist", "What's the average time between a patient's gingivitis diagnosis and their first lisinopril prescription?"),
        ("physician", "How many days, on average, pass between diagnosing gingivitis and starting lisinopril?"),
        ("pharmacist", "What's the average days-to-treatment from gingivitis diagnosis to first lisinopril order?"),
    ],
    "t4_observation_trend_yearly_delta": [
        ("hospital_ceo", "How has the average platelet count changed year over year?"),
        ("population_health_analyst", "Show the year-over-year change in average platelet count."),
        ("hospital_ceo", "What's the yearly trend and change in mean platelet count?"),
        ("population_health_analyst", "Give me the average platelet count by year along with the change from the prior year."),
    ],
    "t4_first_diagnosis_age_per_patient": [
        ("physician", "What was the age at first gingivitis diagnosis for the 5 oldest patients diagnosed?"),
        ("population_health_analyst", "Show the 5 patients who were oldest at the time of their first gingivitis diagnosis, with their age."),
        ("physician", "Who were the oldest 5 patients when first diagnosed with gingivitis, and how old were they?"),
        ("population_health_analyst", "List the top 5 oldest ages at first gingivitis diagnosis, by patient."),
    ],
}

if __name__ == "__main__":
    total = sum(len(v) for v in PARAPHRASES.values())
    print(f"{len(PARAPHRASES)} archetypes covered, {total} paraphrases total")
