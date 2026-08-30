"""
Verify operational_archetypes.py (physician attribution + bed occupancy/LOS)
against train.duckdb, same execution-verify-everything discipline used
elsewhere, then back-translate and assemble into SFT rows.
"""
import csv
import json
import duckdb

from operational_archetypes import CONCEPT_ARCHETYPES, STRUCTURAL_ARCHETYPES
from question_templates import clean_concept, fix_articles

DB_PATH = "C:/dev/fhirsql/data/train.duckdb"
CONCEPTS_PATH = "C:/dev/fhirsql/data/profile/train/selected_concepts.csv"
OUT_VERIFIED = "C:/dev/fhirsql/data/training/verified_gold_operational.jsonl"
OUT_REJECTED = "C:/dev/fhirsql/data/training/rejected_gold_operational.jsonl"
OUT_SFT = "C:/dev/fhirsql/data/training/sft_operational.jsonl"


def sql_escape(s):
    return s.replace("'", "''")


CONCEPT_TEMPLATES = {
    "doctor_top5_by_encounter_type": [
        ("hospital_ceo", "Who are the top 5 physicians by number of {concept} encounters?"),
        ("ed_manager", "Which 5 doctors have handled the most {concept} visits?"),
        ("finance_reviewer", "List the top 5 physicians by {concept} encounter volume."),
        ("hospital_ceo", "Top 5 doctors ranked by count of {concept} encounters -- who are they?"),
    ],
    "doctor_top5_prescribers": [
        ("pharmacist", "Who are the top 5 physicians prescribing the most {concept}?"),
        ("finance_reviewer", "Which 5 doctors have the highest number of {concept} prescriptions?"),
        ("pharmacist", "List the top 5 prescribers of {concept} by prescription count."),
        ("hospital_ceo", "Top 5 physicians by {concept} prescription volume -- who are they?"),
    ],
    "doctor_top5_by_condition_diagnosed": [
        ("hospital_ceo", "Which 5 physicians have diagnosed the most patients with {concept}?"),
        ("population_health_analyst", "Top 5 doctors by number of distinct patients diagnosed with {concept} -- who are they?"),
        ("finance_reviewer", "List the 5 physicians with the most {concept} diagnoses attributed to them."),
        ("hospital_ceo", "Which doctors are diagnosing the most {concept} cases? Show the top 5."),
    ],
}

STRUCTURAL_TEMPLATES = {
    "bed_occupancy_at_date": [
        ("icu_manager", "How many inpatient beds were occupied on January 15, 2025?"),
        ("hospital_ceo", "What was our inpatient bed occupancy as of January 15, 2025?"),
        ("admission_clerk", "How many patients were admitted as inpatients on January 15, 2025?"),
        ("icu_manager", "As of January 15, 2025, how many beds did we have occupied?"),
    ],
    "bed_occupancy_by_month": [
        ("hospital_ceo", "How many inpatient admissions did we have each month?"),
        ("icu_manager", "Break down inpatient admission counts by month."),
        ("admission_clerk", "Show me the monthly trend of inpatient admissions."),
        ("hospital_ceo", "Month by month, how many patients were admitted as inpatients?"),
    ],
    "avg_length_of_stay": [
        ("icu_manager", "What's our average inpatient length of stay, in days?"),
        ("hospital_ceo", "On average, how many days do inpatients stay with us?"),
        ("finance_reviewer", "What is the average length of stay for inpatient admissions?"),
        ("icu_manager", "How many days, on average, does an inpatient stay stay last?"),
    ],
    "current_inpatient_census_by_month": [
        ("icu_manager", "What was our inpatient census -- beds occupied -- at the start of each month?"),
        ("hospital_ceo", "Show monthly inpatient census trends over time."),
        ("admission_clerk", "How many inpatient beds were occupied at the beginning of each month?"),
        ("icu_manager", "Break down our inpatient bed census by month."),
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
