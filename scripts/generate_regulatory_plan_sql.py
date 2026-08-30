"""
Verifies regulatory_archetypes.py's REGULATORY_ARCHETYPES
against train.duckdb. Concepts here come from a small fixed whitelist
(SOURCE_TO_CONCEPTS), not the general concept-bank pool, but still go
through the same valuesets lookup_ambiguous check.
"""
import json
import duckdb

from regulatory_archetypes import REGULATORY_ARCHETYPES, SOURCE_TO_CONCEPTS, SOURCE_TO_TABLE
from generate_gold_plan_sql import sql_escape, is_lookup_ambiguous, exec_rows_sorted, instantiate_plan

DB_PATH = "C:/dev/fhirsql-phase2/data/train.duckdb"
OUT_VERIFIED = "C:/dev/fhirsql-phase2/data/training/verified_gold_plan_regulatory.jsonl"
OUT_REJECTED = "C:/dev/fhirsql-phase2/data/training/rejected_gold_plan_regulatory.jsonl"

STABILITY_CHECK_RUNS = 5


def main():
    con = duckdb.connect(DB_PATH, read_only=True)
    verified, rejected = [], []

    for archetype in REGULATORY_ARCHETYPES:
        table_name = SOURCE_TO_TABLE[archetype["source"]]
        concepts = SOURCE_TO_CONCEPTS[archetype["source"]]
        n_ok = 0
        for concept in concepts:
            ambiguous = is_lookup_ambiguous(con, table_name, concept["display"])
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
                "archetype_id": archetype["id"], "tier": archetype["tier"], "description": archetype["description"],
                "table": table_name, "display": concept["display"], "plan": plan, "sql": sql, "row_count": len(result),
            })
            n_ok += 1
        print(f"  {archetype['id']}: {n_ok}/{len(concepts)} verified")

    with open(OUT_VERIFIED, "w") as f:
        for v in verified:
            f.write(json.dumps(v) + "\n")
    with open(OUT_REJECTED, "w") as f:
        for r in rejected:
            f.write(json.dumps(r) + "\n")
    print(f"\nVerified: {len(verified)}, rejected: {len(rejected)}")


if __name__ == "__main__":
    main()
