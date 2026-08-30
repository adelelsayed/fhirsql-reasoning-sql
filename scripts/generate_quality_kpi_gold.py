"""
Verify quality_kpi_archetypes.py (quality KPIs, demographics, imaging
volume) against train.duckdb, same execution-verify-everything discipline
used elsewhere, then back-translate and assemble into SFT rows.
"""
import csv
import json
import duckdb

from quality_kpi_archetypes import CONCEPT_ARCHETYPES, STRUCTURAL_ARCHETYPES
from question_templates import clean_concept, fix_articles

DB_PATH = "C:/dev/fhirsql/data/train.duckdb"
CONCEPTS_PATH = "C:/dev/fhirsql/data/profile/train/selected_concepts.csv"
OUT_VERIFIED = "C:/dev/fhirsql/data/training/verified_gold_quality_kpi.jsonl"
OUT_REJECTED = "C:/dev/fhirsql/data/training/rejected_gold_quality_kpi.jsonl"
OUT_SFT = "C:/dev/fhirsql/data/training/sft_quality_kpi.jsonl"


def sql_escape(s):
    return s.replace("'", "''")


CONCEPT_TEMPLATES = {
    "condition_by_race": [
        ("population_health_analyst", "How does the {concept} patient count break down by race?"),
        ("infection_control_officer", "Show {concept} diagnosis counts split out by patient race, for our demographic reporting."),
        ("hospital_ceo", "What's the racial breakdown of patients diagnosed with {concept}?"),
        ("population_health_analyst", "Break down {concept} cases by race."),
    ],
    "condition_by_ethnicity": [
        ("population_health_analyst", "How does the {concept} patient count break down by ethnicity?"),
        ("infection_control_officer", "Show {concept} diagnosis counts split out by patient ethnicity."),
        ("hospital_ceo", "What's the ethnicity breakdown of patients diagnosed with {concept}?"),
        ("population_health_analyst", "Break down {concept} cases by ethnicity."),
    ],
}

STRUCTURAL_TEMPLATES = {
    "physician_monthly_case_volume": [
        ("hospital_ceo", "How many distinct patients did each physician see per month?"),
        ("finance_reviewer", "Show monthly patient case volume broken down by physician."),
        ("hospital_ceo", "For each doctor, how many cases did they handle each month?"),
        ("finance_reviewer", "Break down monthly case counts by treating physician."),
    ],
    "readmission_rate_30day": [
        ("hospital_ceo", "How many patients were readmitted as inpatients within 30 days of a prior discharge?"),
        ("icu_manager", "What's our 30-day inpatient readmission count?"),
        ("population_health_analyst", "How many patients had an inpatient readmission within 30 days of discharge?"),
        ("hospital_ceo", "Give me the count of patients readmitted within 30 days -- a key quality indicator."),
    ],
    "mortality_review_monthly": [
        ("hospital_ceo", "How many patient deaths were recorded each month, for mortality review?"),
        ("icu_manager", "Break down death-certification counts by month for our mortality review."),
        ("population_health_analyst", "What's the monthly count of death certifications on file?"),
        ("hospital_ceo", "Show me our monthly mortality figures."),
    ],
    "fall_risk_screening_monthly": [
        ("icu_manager", "How many Morse Fall Scale screenings were performed each month?"),
        ("nurse", "Break down fall-risk screening volume by month, a patient-safety KPI."),
        ("hospital_ceo", "What's our monthly count of fall-risk assessments?"),
        ("icu_manager", "Show monthly Morse Fall Scale screening counts."),
    ],
    "patients_by_race": [
        ("population_health_analyst", "How many patients do we have in each race category?"),
        ("hospital_ceo", "Break down our patient population by race."),
        ("infection_control_officer", "What's the racial composition of our patient population?"),
        ("population_health_analyst", "Show patient counts by race across our population."),
    ],
    "patients_by_ethnicity": [
        ("population_health_analyst", "How many patients do we have in each ethnicity category?"),
        ("hospital_ceo", "Break down our patient population by ethnicity."),
        ("infection_control_officer", "What's the ethnic composition of our patient population?"),
        ("population_health_analyst", "Show patient counts by ethnicity across our population."),
    ],
    "patients_by_state": [
        ("hospital_ceo", "How many patients come from each state?"),
        ("population_health_analyst", "Break down our patient population by state of residence."),
        ("admission_clerk", "What's the geographic distribution of our patients by state?"),
        ("hospital_ceo", "Show patient counts by state."),
    ],
    "imaging_volume_by_month": [
        ("hospital_ceo", "How many imaging studies (radiology orders) were performed each month?"),
        ("finance_reviewer", "Break down radiology order volume by month."),
        ("ed_manager", "What's our monthly imaging study volume?"),
        ("hospital_ceo", "Show me our monthly radiology throughput."),
    ],
    "imaging_volume_by_modality": [
        ("finance_reviewer", "Break down imaging studies by modality -- X-ray, CT, MRI, ultrasound, etc."),
        ("hospital_ceo", "What's the volume of imaging studies by modality type?"),
        ("ed_manager", "How many imaging studies of each modality have we performed?"),
        ("finance_reviewer", "Show radiology order counts grouped by modality."),
    ],
}


def load_concepts():
    with open(CONCEPTS_PATH) as f:
        return list(csv.DictReader(f))


def main():
    con = duckdb.connect(DB_PATH, read_only=True)
    concepts = load_concepts()

    verified, rejected = [], []

    for archetype in CONCEPT_ARCHETYPES:
        eligible = [c for c in concepts if c["table_name"] == archetype["source_table"]]
        n_ok = 0
        for concept in eligible:
            sql = archetype["sql"].format(code=sql_escape(concept["code"]), code_system=sql_escape(concept["code_system"])).strip()
            try:
                result = con.execute(sql).fetchall()
            except Exception as e:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": "execution_error", "error": str(e)})
                continue
            if len(result) == 0:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": "empty_result"})
                continue
            verified.append({
                "archetype_id": archetype["id"], "tier": archetype["tier"], "concept_type": "concept",
                "display": concept["display"], "sql": sql, "row_count": len(result),
            })
            n_ok += 1
        print(f"  {archetype['id']}: {n_ok}/{len(eligible)} verified")

    for archetype in STRUCTURAL_ARCHETYPES:
        sql = archetype["sql"].strip()
        try:
            result = con.execute(sql).fetchall()
        except Exception as e:
            rejected.append({"archetype_id": archetype["id"], "reason": "execution_error", "error": str(e)})
            print(f"  {archetype['id']}: FAILED ({e})")
            continue
        if len(result) == 0:
            rejected.append({"archetype_id": archetype["id"], "reason": "empty_result"})
            print(f"  {archetype['id']}: 0/1 verified (empty result)")
            continue
        verified.append({
            "archetype_id": archetype["id"], "tier": archetype["tier"], "concept_type": "structural",
            "display": None, "sql": sql, "row_count": len(result),
        })
        print(f"  {archetype['id']}: 1/1 verified ({len(result)} rows)")

    with open(OUT_VERIFIED, "w") as f:
        for v in verified:
            f.write(json.dumps(v) + "\n")
    with open(OUT_REJECTED, "w") as f:
        for r in rejected:
            f.write(json.dumps(r) + "\n")
    print(f"\nVerified: {len(verified)}, rejected: {len(rejected)}")

    rows = []
    for gold in verified:
        if gold["concept_type"] == "concept":
            templates = CONCEPT_TEMPLATES[gold["archetype_id"]]
            concept = clean_concept(gold["display"])
            for persona, template in templates:
                question = fix_articles(template.format(concept=concept))
                rows.append({
                    "archetype_id": gold["archetype_id"], "tier": gold["tier"], "persona": persona,
                    "question": question, "schema_ref": "schema/schema.sql", "sql": gold["sql"],
                    "concept_display": gold["display"], "flags": [],
                })
        else:
            templates = STRUCTURAL_TEMPLATES[gold["archetype_id"]]
            for persona, question in templates:
                rows.append({
                    "archetype_id": gold["archetype_id"], "tier": gold["tier"], "persona": persona,
                    "question": question, "schema_ref": "schema/schema.sql", "sql": gold["sql"],
                    "concept_display": None, "flags": [],
                })

    with open(OUT_SFT, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"Back-translated: {len(rows)} SFT rows -> {OUT_SFT}")


if __name__ == "__main__":
    main()
