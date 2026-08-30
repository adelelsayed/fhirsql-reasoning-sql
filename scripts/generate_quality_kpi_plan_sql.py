"""
Verifies quality_kpi_archetypes.py's CONCEPT_ARCHETYPES
and STRUCTURAL_ARCHETYPES (two of which -- mortality/fall-risk -- are now
lookup-based on a fixed exact-match concept, not per-instantiation-varied,
so their `sql` needs no formatting) against train.duckdb.
"""
import csv
import json
import duckdb

from quality_kpi_archetypes import CONCEPT_ARCHETYPES, STRUCTURAL_ARCHETYPES
from generate_gold_plan_sql import sql_escape, is_lookup_ambiguous, exec_rows_sorted, instantiate_plan

DB_PATH = "C:/dev/fhirsql-phase2/data/train.duckdb"
CONCEPTS_PATH = "C:/dev/fhirsql-phase2/data/profile/train/selected_concepts.csv"
OUT_VERIFIED = "C:/dev/fhirsql-phase2/data/training/verified_gold_plan_quality_kpi.jsonl"
OUT_REJECTED = "C:/dev/fhirsql-phase2/data/training/rejected_gold_plan_quality_kpi.jsonl"

STABILITY_CHECK_RUNS = 5


def load_concepts():
    with open(CONCEPTS_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    con = duckdb.connect(DB_PATH, read_only=True)
    concepts = load_concepts()

    verified, rejected = [], []

    for archetype in CONCEPT_ARCHETYPES:
        eligible = [c for c in concepts if c["table_name"] == archetype["source_table"]]
        n_ok = 0
        for concept in eligible:
            ambiguous = is_lookup_ambiguous(con, archetype["source_table"], concept["display"])
            if ambiguous is None:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": "not_in_valuesets"})
                continue
            if ambiguous:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": "lookup_ambiguous"})
                continue

            sql = archetype["sql"].format(display=sql_escape(concept["display"])).strip()
            plan = instantiate_plan(archetype["plan"], display=concept["display"])
            try:
                result = exec_rows_sorted(con, sql)
            except Exception as e:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": "execution_error", "error": str(e), "sql": sql})
                continue
            if len(result) == 0:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": "empty_result", "sql": sql})
                continue

            stable = True
            for _ in range(STABILITY_CHECK_RUNS - 1):
                if exec_rows_sorted(con, sql) != result:
                    stable = False
                    break
            if not stable:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": "unstable_across_repeats", "sql": sql})
                continue

            verified.append({
                "archetype_id": archetype["id"], "tier": archetype["tier"], "concept_type": "concept",
                "display": concept["display"], "plan": plan, "sql": sql, "row_count": len(result),
            })
            n_ok += 1
        print(f"  {archetype['id']}: {n_ok}/{len(eligible)} verified")

    for archetype in STRUCTURAL_ARCHETYPES:
        sql = archetype["sql"].strip()
        plan = archetype["plan"]
        try:
            result = exec_rows_sorted(con, sql)
        except Exception as e:
            rejected.append({"archetype_id": archetype["id"], "reason": "execution_error", "error": str(e)})
            print(f"  {archetype['id']}: FAILED ({e})")
            continue
        if len(result) == 0:
            rejected.append({"archetype_id": archetype["id"], "reason": "empty_result"})
            print(f"  {archetype['id']}: 0/1 verified (empty result)")
            continue

        stable = True
        for _ in range(STABILITY_CHECK_RUNS - 1):
            if exec_rows_sorted(con, sql) != result:
                stable = False
                break
        if not stable:
            rejected.append({"archetype_id": archetype["id"], "reason": "unstable_across_repeats", "sql": sql})
            print(f"  {archetype['id']}: UNSTABLE")
            continue

        verified.append({
            "archetype_id": archetype["id"], "tier": archetype["tier"], "concept_type": "structural",
            "display": None, "plan": plan, "sql": sql, "row_count": len(result),
        })
        print(f"  {archetype['id']}: 1/1 verified ({len(result)} rows)")

    with open(OUT_VERIFIED, "w") as f:
        for v in verified:
            f.write(json.dumps(v) + "\n")
    with open(OUT_REJECTED, "w") as f:
        for r in rejected:
            f.write(json.dumps(r) + "\n")
    print(f"\nVerified: {len(verified)}, rejected: {len(rejected)}")


if __name__ == "__main__":
    main()
