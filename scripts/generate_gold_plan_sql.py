"""
Instantiates `plan`-carrying archetypes (see archetypes.py, plan_schema.py)
against real concepts, execute-verifies the compiled SQL, and proactively
checks repeated-execution stability.

Produces (question-ready) triples: archetype_id/tier/description, the
concept `display` text, the instantiated `plan` dict, and the compiled
`sql` string. Back-translation (a later step) turns `plan` + `sql` into the
actual SFT target: `json.dumps(plan)` followed by `sql`, one completion.

Only ARCHETYPES entries with both `lookup_based=True` and a `plan` template
are processed -- archetypes not yet converted to the new schema are skipped
entirely (reported in the summary) rather than silently omitted.

`plan`'s {display} placeholder is filled with the RAW display text (no SQL
escaping -- it's human-readable JSON content, not a SQL string literal);
`sql`'s {display} is filled with the SQL-escaped version, exactly as the
original lookup-based generator did. Concepts flagged `lookup_ambiguous` in
`valuesets` are skipped entirely, not force-resolved with LIMIT 1.
"""
import csv
import json
import duckdb

from archetypes import ARCHETYPES

DB_PATH = "C:/dev/fhirsql-phase2/data/train.duckdb"
CONCEPTS_PATH = "C:/dev/fhirsql-phase2/data/profile/train/selected_concepts.csv"
OUT_VERIFIED = "C:/dev/fhirsql-phase2/data/training/verified_gold_plan.jsonl"
OUT_REJECTED = "C:/dev/fhirsql-phase2/data/training/rejected_gold_plan.jsonl"

STABILITY_CHECK_RUNS = 5


def sql_escape(s):
    return s.replace("'", "''")


def load_concepts():
    with open(CONCEPTS_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def is_lookup_ambiguous(con, table_name, display):
    row = con.execute(
        "SELECT lookup_ambiguous FROM valuesets WHERE table_name = ? AND display = ?",
        [table_name, display],
    ).fetchone()
    return row[0] if row else None


def exec_rows_sorted(con, sql):
    rows = list(map(tuple, con.execute(sql).fetchall()))
    return sorted(rows, key=lambda row: tuple((v is None, v) for v in row))


def instantiate_plan(node, **kwargs):
    """Recursively .format()s only the string leaves of a plan dict/list, so JSON
    structural braces are never mistaken for format placeholders (the reason this
    isn't just json.dumps(plan).format(**kwargs))."""
    if isinstance(node, dict):
        return {k: instantiate_plan(v, **kwargs) for k, v in node.items()}
    if isinstance(node, list):
        return [instantiate_plan(v, **kwargs) for v in node]
    if isinstance(node, str):
        return node.format(**kwargs)
    return node


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


def main():
    concepts = load_concepts()
    con = duckdb.connect(DB_PATH, read_only=True)

    verified, rejected = [], []
    rejection_reasons = {}

    plan_archetypes = [a for a in ARCHETYPES if a.get("lookup_based") and "plan" in a]
    skipped_archetypes = [a["id"] for a in ARCHETYPES if a.get("lookup_based") and "plan" not in a]
    print(f"plan-carrying archetypes to process: {len(plan_archetypes)}")
    if skipped_archetypes:
        print(f"skipped (lookup_based but no plan template yet): {skipped_archetypes}")

    for archetype in plan_archetypes:
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
        n_verified_this = 0
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
                "archetype_id": archetype["id"],
                "tier": archetype["tier"],
                "description": archetype["description"],
                "table": source_table,
                "display": concept["display"],
                "plan": plan,
                "sql": sql,
                "row_count": len(result),
            })
            n_verified_this += 1

        print(f"  {archetype['id']} (tier {archetype['tier']}): {n_verified_this}/{len(eligible)} verified "
              f"({n_ambiguous_skipped} skipped as lookup_ambiguous)")

    import os
    os.makedirs("C:/dev/fhirsql-phase2/data/training", exist_ok=True)
    with open(OUT_VERIFIED, "w") as f:
        for v in verified:
            f.write(json.dumps(v) + "\n")
    with open(OUT_REJECTED, "w") as f:
        for r in rejected:
            f.write(json.dumps(r) + "\n")

    print(f"\nTotal verified: {len(verified)}")
    print(f"Total rejected: {len(rejected)}")
    print(f"Rejection reasons: {rejection_reasons}")
    print(f"\nWritten: {OUT_VERIFIED}")
    print(f"Written: {OUT_REJECTED}")


if __name__ == "__main__":
    main()
