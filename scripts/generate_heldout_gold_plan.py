"""
Plan-carrying counterpart to generate_heldout_gold.py -- same two
concept arms, same tier/table restriction for the unseen arm, but
instantiates plan + SQL together and stability-checks the SQL, same as
generate_gold_plan_sql.py does for the train side.

Usage: python generate_heldout_gold_plan.py familiar|unseen
"""
import csv
import json
import os
import sys
import duckdb

sys.path.insert(0, os.path.dirname(__file__))
from archetypes import ARCHETYPES
from generate_gold_plan_sql import sql_escape, is_lookup_ambiguous, exec_rows_sorted, instantiate_plan, compute_threshold

DB_PATH = "C:/dev/fhirsql-phase2/data/heldout.duckdb"
OUT_DIR = "C:/dev/fhirsql-phase2/data/training"

STABILITY_CHECK_RUNS = 5

ARM_CONFIG = {
    "familiar": {
        "concepts_path": "C:/dev/fhirsql-phase2/data/profile/heldout/selected_concepts_familiar.csv",
        "archetype_filter": lambda a: True,
    },
    "unseen": {
        "concepts_path": "C:/dev/fhirsql-phase2/data/profile/heldout/selected_concepts_unseen.csv",
        "archetype_filter": lambda a: a["tier"] in (1, 2) and a["source_table"] in
            ("condition", "procedure", "medication_request"),
    },
}


def load_concepts(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def instantiate(archetype, concept, con):
    display_raw = concept["display"]
    display_sql = sql_escape(display_raw)
    fmt_sql = {"display": display_sql}
    fmt_plan = {"display": display_raw}
    if "{threshold}" in archetype["sql"]:
        threshold = compute_threshold(con, concept["code"], concept["code_system"])
        if threshold is None:
            return None, None, "no_numeric_data_for_threshold"
        fmt_sql["threshold"] = threshold
        fmt_plan["threshold"] = threshold
    sql = archetype["sql"].format(**fmt_sql).strip()
    plan = instantiate_plan(archetype["plan"], **fmt_plan)
    return plan, sql, None


def run(arm):
    cfg = ARM_CONFIG[arm]
    concepts = load_concepts(cfg["concepts_path"])
    archetypes = [a for a in ARCHETYPES if a.get("lookup_based") and "plan" in a and cfg["archetype_filter"](a)]
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

        n_ambiguous_skipped = 0
        n_ok = 0
        for concept in eligible:
            ambiguous = is_lookup_ambiguous(con, source_table, concept["display"])
            if ambiguous is None:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": "not_in_valuesets"})
                rejection_reasons["not_in_valuesets"] = rejection_reasons.get("not_in_valuesets", 0) + 1
                continue
            if ambiguous:
                n_ambiguous_skipped += 1
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": "lookup_ambiguous"})
                rejection_reasons["lookup_ambiguous"] = rejection_reasons.get("lookup_ambiguous", 0) + 1
                continue

            plan, sql, skip_reason = instantiate(archetype, concept, con)
            if sql is None:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": skip_reason})
                rejection_reasons[skip_reason] = rejection_reasons.get(skip_reason, 0) + 1
                continue

            try:
                result = exec_rows_sorted(con, sql)
            except Exception as e:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"],
                                  "reason": "execution_error", "error": str(e), "sql": sql})
                rejection_reasons["execution_error"] = rejection_reasons.get("execution_error", 0) + 1
                continue

            if len(result) == 0:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": "empty_result", "sql": sql})
                rejection_reasons["empty_result"] = rejection_reasons.get("empty_result", 0) + 1
                continue

            stable = True
            for _ in range(STABILITY_CHECK_RUNS - 1):
                if exec_rows_sorted(con, sql) != result:
                    stable = False
                    break
            if not stable:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"],
                                  "reason": "unstable_across_repeats", "sql": sql})
                rejection_reasons["unstable_across_repeats"] = rejection_reasons.get("unstable_across_repeats", 0) + 1
                continue

            verified.append({
                "archetype_id": archetype["id"], "tier": archetype["tier"],
                "description": archetype["description"], "table": source_table,
                "display": concept["display"], "plan": plan, "sql": sql, "row_count": len(result),
            })
            n_ok += 1

        print(f"  {archetype['id']} (tier {archetype['tier']}): {n_ok}/{len(eligible)} verified "
              f"({n_ambiguous_skipped} skipped as lookup_ambiguous)")

    os.makedirs(OUT_DIR, exist_ok=True)
    out_verified = f"{OUT_DIR}/heldout_verified_gold_plan_{arm}.jsonl"
    out_rejected = f"{OUT_DIR}/heldout_rejected_gold_plan_{arm}.jsonl"
    with open(out_verified, "w") as f:
        for v in verified:
            f.write(json.dumps(v) + "\n")
    with open(out_rejected, "w") as f:
        for r in rejected:
            f.write(json.dumps(r) + "\n")

    print(f"\n[{arm}] Total verified: {len(verified)}")
    print(f"[{arm}] Total rejected: {len(rejected)}")
    print(f"[{arm}] Rejection reasons: {rejection_reasons}")


if __name__ == "__main__":
    arm = sys.argv[1] if len(sys.argv) > 1 else None
    if arm not in ARM_CONFIG:
        print("Usage: python generate_heldout_gold_plan.py familiar|unseen")
        sys.exit(1)
    run(arm)
