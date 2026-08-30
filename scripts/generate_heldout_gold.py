"""
Heldout benchmark, main-clinical-archetype pass -- two concept arms:

  familiar: data/profile/heldout/selected_concepts_familiar.csv (the 382 concepts
            used to build all training data -- isolates population
            generalization). All ARCHETYPES tiers 1-4 eligible, same as train.
  unseen:   data/profile/heldout/selected_concepts_unseen.csv (the 87 concepts
            that exist in heldout's concept bank but never appear anywhere in
            train's -- isolates concept generalization). All 87 are 1-3-patient
            rarities (verified directly), so only tier-1/2 patient-level
            archetypes (COUNT/DISTINCT/AVG/GROUP BY -- no top-N ranking) on the
            3 tables that actually have unseen candidates (condition, procedure,
            medication_request) are in scope here -- population-aggregate
            archetypes (top-5, rate-of) can't be built from 1-3 patients.

Mirrors generate_gold_sql.py's instantiate/verify logic exactly, just retargeted
at heldout.duckdb and made arm-selectable. Does not touch train.duckdb, train's
concept files, or any train-side output file.

Usage: python generate_heldout_gold.py familiar|unseen
"""
import csv
import json
import os
import sys
import duckdb

sys.path.insert(0, os.path.dirname(__file__))
from archetypes import ARCHETYPES

DB_PATH = "C:/dev/fhirsql/data/heldout.duckdb"
OUT_DIR = "C:/dev/fhirsql/data/training"

ARM_CONFIG = {
    "familiar": {
        "concepts_path": "C:/dev/fhirsql/data/profile/heldout/selected_concepts_familiar.csv",
        "archetype_filter": lambda a: True,
    },
    "unseen": {
        "concepts_path": "C:/dev/fhirsql/data/profile/heldout/selected_concepts_unseen.csv",
        "archetype_filter": lambda a: a["tier"] in (1, 2) and a["source_table"] in
            ("condition", "procedure", "medication_request"),
    },
}


def sql_escape(s):
    return s.replace("'", "''")


def load_concepts(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def compute_threshold(con, code, code_system, percentile=0.75):
    row = con.execute(
        "SELECT quantile_cont(valueQuantity, ?) FROM observation WHERE code = ? AND system = ? AND valueQuantity IS NOT NULL",
        [percentile, code, code_system],
    ).fetchone()
    val = row[0] if row else None
    if val is None:
        return None
    return round(val, 1) if val < 10 else round(val)


def instantiate(archetype, concept, con):
    code = sql_escape(concept["code"])
    code_system = sql_escape(concept["code_system"])
    display = sql_escape(concept["display"])
    fmt_args = {"code": code, "code_system": code_system, "display": display}
    if "{threshold}" in archetype["sql"]:
        threshold = compute_threshold(con, concept["code"], concept["code_system"])
        if threshold is None:
            return None, "no_numeric_data_for_threshold"
        fmt_args["threshold"] = threshold
    sql = archetype["sql"].format(**fmt_args).strip()
    return sql, None


def run(arm):
    cfg = ARM_CONFIG[arm]
    concepts = load_concepts(cfg["concepts_path"])
    archetypes = [a for a in ARCHETYPES if cfg["archetype_filter"](a)]
    con = duckdb.connect(DB_PATH, read_only=True)

    verified, rejected = [], []
    rejection_reasons = {}

    for archetype in archetypes:
        source_table = archetype["source_table"]
        requires_numeric = archetype.get("requires_numeric", False)
        eligible = [c for c in concepts if c["table_name"] == source_table]
        if requires_numeric:
            eligible = [
                c for c in eligible
                if con.execute(
                    "SELECT COUNT(*) FROM observation WHERE code=? AND system=? AND valueQuantity IS NOT NULL",
                    [c["code"], c["code_system"]],
                ).fetchone()[0] > 0
            ]

        for concept in eligible:
            sql, skip_reason = instantiate(archetype, concept, con)
            if sql is None:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": skip_reason})
                rejection_reasons[skip_reason] = rejection_reasons.get(skip_reason, 0) + 1
                continue
            try:
                result = con.execute(sql).fetchall()
                columns = [d[0] for d in con.description]
            except Exception as e:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"],
                                  "reason": "execution_error", "error": str(e), "sql": sql})
                rejection_reasons["execution_error"] = rejection_reasons.get("execution_error", 0) + 1
                continue
            if len(result) == 0:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": "empty_result", "sql": sql})
                rejection_reasons["empty_result"] = rejection_reasons.get("empty_result", 0) + 1
                continue
            verified.append({
                "archetype_id": archetype["id"], "tier": archetype["tier"],
                "description": archetype["description"], "table": source_table,
                "code": concept["code"], "code_system": concept["code_system"], "display": concept["display"],
                "sql": sql, "row_count": len(result), "columns": columns,
            })

        n_this = sum(1 for v in verified if v["archetype_id"] == archetype["id"])
        print(f"  {archetype['id']} (tier {archetype['tier']}): {n_this}/{len(eligible)} verified")

    os.makedirs(OUT_DIR, exist_ok=True)
    out_verified = f"{OUT_DIR}/heldout_verified_gold_{arm}.jsonl"
    out_rejected = f"{OUT_DIR}/heldout_rejected_gold_{arm}.jsonl"
    with open(out_verified, "w") as f:
        for v in verified:
            f.write(json.dumps(v) + "\n")
    with open(out_rejected, "w") as f:
        for r in rejected:
            f.write(json.dumps(r) + "\n")

    print(f"\n[{arm}] Total verified: {len(verified)}")
    print(f"[{arm}] Total rejected: {len(rejected)}")
    print(f"[{arm}] Rejection reasons: {rejection_reasons}")
    print(f"[{arm}] Written: {out_verified}")
    print(f"[{arm}] Written: {out_rejected}")


if __name__ == "__main__":
    arm = sys.argv[1] if len(sys.argv) > 1 else None
    if arm not in ARM_CONFIG:
        print("Usage: python generate_heldout_gold.py familiar|unseen")
        sys.exit(1)
    run(arm)
