"""
Verify the regulatory-reportable archetypes (regulatory_archetypes.py) against
train.duckdb, same methodology as generate_gold_sql.py (execution-verify,
exclude empty results), then back-translate with regulatory/compliance-flavored
questions and assemble into SFT rows, merged into the main training set.
"""
import json
import duckdb

from regulatory_archetypes import REGULATORY_ARCHETYPES, SOURCE_TO_CONCEPTS
from question_templates import clean_concept, fix_articles
from assemble_sft_rows import SCHEMA_PATH

DB_PATH = "C:/dev/fhirsql/data/train.duckdb"
OUT_VERIFIED = "C:/dev/fhirsql/data/training/verified_gold_regulatory.jsonl"
OUT_REJECTED = "C:/dev/fhirsql/data/training/rejected_gold_regulatory.jsonl"
OUT_SFT = "C:/dev/fhirsql/data/training/sft_regulatory.jsonl"


def sql_escape(s):
    return s.replace("'", "''")


# Persona-appropriate templates for each regulatory archetype.
REG_TEMPLATES = {
    "reg_notifiable_condition_monthly": [
        ("infection_control_officer", "For our monthly notifiable-disease report, how many new {concept} diagnoses did we have each month?"),
        ("infection_control_officer", "Break down new {concept} case counts by month for the notifiable disease submission."),
        ("population_health_analyst", "How many new {concept} diagnoses were recorded each month?"),
        ("infection_control_officer", "What's the monthly count of newly diagnosed {concept} cases we need to report?"),
    ],
    "reg_notifiable_lab_monthly": [
        ("infection_control_officer", "For public-health surveillance reporting, how many {concept} tests were performed each month?"),
        ("infection_control_officer", "Break down monthly {concept} testing volume for our notifiable-disease submission."),
        ("population_health_analyst", "What's the monthly count of {concept} tests conducted?"),
        ("infection_control_officer", "How many patients had a {concept} test each month?"),
    ],
    "reg_notifiable_active_case_list": [
        ("infection_control_officer", "Which patients have an active {concept} diagnosis, for case management follow-up?"),
        ("infection_control_officer", "List every patient with a currently active {concept} diagnosis for contact tracing purposes."),
        ("physician", "Who are the patients with active {concept} right now?"),
        ("infection_control_officer", "Give me the active case list for {concept} that we need to track."),
    ],
    "reg_narcotic_quarterly_consumption": [
        ("pharmacist", "For our quarterly narcotic consumption report, how many units of {concept} were dispensed each quarter?"),
        ("pharmacist", "Break down {concept} dispensing volume by quarter for the narcotics report."),
        ("finance_reviewer", "What's the quarterly dispensing count for {concept}?"),
        ("pharmacist", "How many {concept} prescriptions were filled each quarter?"),
    ],
    "reg_controlled_monthly_consumption": [
        ("pharmacist", "For our monthly controlled-substance consumption report, how many units of {concept} were dispensed each month?"),
        ("pharmacist", "Break down {concept} dispensing volume by month for the controlled-drug report."),
        ("finance_reviewer", "What's the monthly dispensing count for {concept}?"),
        ("pharmacist", "How many {concept} prescriptions were filled each month?"),
    ],
    "reg_recent_narcotic_patients": [
        ("pharmacist", "Which patients have been dispensed {concept} in the last 30 days?"),
        ("pharmacist", "List patients with a {concept} prescription filled within the past month, for utilization review."),
        ("finance_reviewer", "Who received {concept} in the last 30 days?"),
        ("pharmacist", "Give me every patient dispensed {concept} in the past 30 days."),
    ],
}


def instantiate_and_verify(con):
    verified, rejected = [], []
    for archetype in REGULATORY_ARCHETYPES:
        concepts = SOURCE_TO_CONCEPTS[archetype["source"]]
        n_ok = 0
        for concept in concepts:
            code = sql_escape(concept["code"])
            code_system = sql_escape(concept["code_system"])
            sql = archetype["sql"].format(code=code, code_system=code_system).strip()
            try:
                result = con.execute(sql).fetchall()
                columns = [d[0] for d in con.description]
            except Exception as e:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": "execution_error", "error": str(e), "sql": sql})
                continue
            if len(result) == 0:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": "empty_result", "sql": sql})
                continue
            verified.append({
                "archetype_id": archetype["id"], "tier": archetype["tier"], "description": archetype["description"],
                "table": concept["table_name"], "code": concept["code"], "code_system": concept["code_system"],
                "display": concept["display"], "sql": sql, "row_count": len(result), "columns": columns,
            })
            n_ok += 1
        print(f"  {archetype['id']}: {n_ok}/{len(concepts)} verified")
    return verified, rejected


def back_translate_and_assemble(verified):
    rows = []
    for gold in verified:
        templates = REG_TEMPLATES[gold["archetype_id"]]
        concept = clean_concept(gold["display"])
        for persona, template in templates:
            question = fix_articles(template.format(concept=concept))
            rows.append({
                "archetype_id": gold["archetype_id"], "tier": gold["tier"], "persona": persona,
                "question": question, "schema_ref": "schema/schema.sql", "sql": gold["sql"].strip(),
                "concept_display": gold["display"], "concept_code": gold["code"], "flags": [],
            })
    return rows


def main():
    con = duckdb.connect(DB_PATH, read_only=True)
    verified, rejected = instantiate_and_verify(con)

    with open(OUT_VERIFIED, "w") as f:
        for v in verified:
            f.write(json.dumps(v) + "\n")
    with open(OUT_REJECTED, "w") as f:
        for r in rejected:
            f.write(json.dumps(r) + "\n")
    print(f"\nVerified: {len(verified)}, rejected: {len(rejected)}")

    rows = back_translate_and_assemble(verified)
    with open(OUT_SFT, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"Back-translated: {len(rows)} SFT rows -> {OUT_SFT}")


if __name__ == "__main__":
    main()
