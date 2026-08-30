"""
Persona roster and archetype->persona mapping.

A broader roster than a minimal clinician/analyst/administrator/pharmacist
set, to make back-translated questions read like they came from a specific
hospital role, not a generic NL2SQL corpus.
Each archetype maps to 2-3 personas who would realistically ask that shape of
question -- a CEO doesn't ask a tier-1 single-patient lookup, a nurse doesn't
ask a year-over-year trend question.
"""

PERSONAS = {
    "physician": "an attending physician reviewing their patient panel, phrasing clinically (diagnoses, treatment, labs)",
    "nurse": "a floor nurse checking patient status day-to-day (vitals, immunizations, allergies, care needs)",
    "pharmacist": "a hospital pharmacist focused on medications (prescriptions, dosing, drug utilization)",
    "admission_clerk": "a registration/admissions clerk focused on encounter/visit logistics, not clinical detail",
    "outpatient_clerk": "an outpatient clinic scheduler tracking visit types and follow-ups",
    "ed_manager": "an emergency department manager tracking ED visit volume and throughput",
    "icu_manager": "an ICU charge nurse/manager tracking admissions, acuity, and critical care caseload",
    "finance_reviewer": "a revenue-cycle/finance analyst tracking procedure and service volumes for billing purposes",
    "hospital_ceo": "a hospital CEO or COO asking high-level strategic/trend questions, not patient-level detail",
    "population_health_analyst": "a population health / quality analyst looking at cohort-level demographic and prevalence patterns",
    "infection_control_officer": "an infection control / public health reporting officer preparing notifiable-disease submissions to the relevant public health authority",
}

# archetype_id -> ordered list of the personas most likely to ask that question shape.
# Back-translation draws its 4-5 paraphrases from this list (cycling/sampling), not
# uniformly at random across all 10 personas.
ARCHETYPE_PERSONAS = {
    # Tier 1
    "t1_count_patients_with_condition": ["physician", "population_health_analyst", "hospital_ceo"],
    "t1_list_patients_on_medication": ["pharmacist", "physician", "nurse"],
    "t1_count_patients_allergic": ["nurse", "pharmacist", "physician"],
    "t1_count_immunizations_given": ["nurse", "population_health_analyst", "hospital_ceo"],
    "t1_list_patients_with_procedure": ["physician", "finance_reviewer", "outpatient_clerk"],
    "t1_avg_observation_value": ["physician", "nurse", "population_health_analyst"],
    "t1_count_diagnostic_reports": ["physician", "finance_reviewer", "population_health_analyst"],
    "t1_count_encounters_of_type": ["admission_clerk", "ed_manager", "hospital_ceo"],

    # Tier 2
    "t2_active_condition_count": ["physician", "population_health_analyst", "nurse"],
    "t2_resolved_condition_count": ["physician", "population_health_analyst"],
    "t2_condition_diagnoses_by_year": ["population_health_analyst", "hospital_ceo"],
    "t2_medication_status_breakdown": ["pharmacist", "finance_reviewer"],
    "t2_medication_by_year": ["pharmacist", "finance_reviewer", "hospital_ceo"],
    "t2_observation_high_values": ["physician", "nurse"],
    "t2_observation_by_year": ["physician", "population_health_analyst"],
    "t2_procedure_by_year": ["finance_reviewer", "hospital_ceo", "outpatient_clerk"],
    "t2_allergy_criticality_breakdown": ["nurse", "pharmacist", "physician"],
    "t2_careplan_active_duration": ["admission_clerk", "ed_manager", "icu_manager"],

    # Tier 3
    "t3_condition_by_gender": ["population_health_analyst", "hospital_ceo"],
    "t3_condition_over_age": ["population_health_analyst", "physician"],
    "t3_condition_avg_observation": ["physician", "population_health_analyst"],
    "t3_medication_and_condition": ["pharmacist", "physician"],
    "t3_procedure_with_encounter_type": ["finance_reviewer", "ed_manager", "outpatient_clerk"],
    "t3_immunization_by_gender": ["population_health_analyst", "nurse"],
    "t3_avg_procedures_per_patient_with_condition": ["finance_reviewer", "physician", "hospital_ceo"],
    "t3_diagnostic_report_with_condition": ["physician", "population_health_analyst"],
    "t3_observation_and_medication": ["physician", "pharmacist"],
    "t3_allergy_and_condition_count": ["nurse", "physician"],
    "t3_condition_encounter_count": ["physician", "hospital_ceo", "finance_reviewer"],
    "t3_medication_by_encounter_class": ["pharmacist", "ed_manager", "finance_reviewer"],
    "t3_procedure_avg_patient_age": ["physician", "population_health_analyst"],

    # Tier 4
    "t4_observation_first_vs_last": ["physician", "population_health_analyst"],
    "t4_most_recent_observation_per_patient": ["physician", "nurse"],
    "t4_condition_then_procedure_30d": ["physician", "population_health_analyst"],
    "t4_top5_patients_by_medication_count": ["pharmacist", "physician"],
    "t4_patients_with_3plus_encounters_12mo": ["ed_manager", "hospital_ceo", "icu_manager"],
    "t4_top5_patients_by_condition_recurrence": ["physician", "population_health_analyst"],
    "t4_time_from_condition_to_medication": ["physician", "pharmacist"],
    "t4_observation_trend_yearly_delta": ["hospital_ceo", "population_health_analyst"],
    "t4_first_diagnosis_age_per_patient": ["physician", "population_health_analyst"],
}


def personas_for(archetype_id):
    return ARCHETYPE_PERSONAS.get(archetype_id, ["physician", "population_health_analyst"])
