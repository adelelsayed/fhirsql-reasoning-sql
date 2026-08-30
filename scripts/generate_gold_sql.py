"""
Instantiates every archetype x eligible concept, then execution-verifies each one.

For each archetype x eligible concept, build literal gold SQL (values embedded
as SQL text, not parameterized placeholders -- that's what a model actually has
to produce), run it against train.duckdb, and keep only rows that execute
without error AND return at least one row -- a query returning zero rows would
be trivially "matched" by a broken query also returning zero rows, and RL would
learn to exploit that, so empty-result gold is excluded entirely.

Output: data/training/verified_gold.jsonl -- one JSON object per verified
artifact: {archetype_id, tier, table, code, code_system, display, sql,
row_count, columns}.
Also: data/training/rejected_gold.jsonl -- rejected instantiations with reason,
for the rejection histogram.
"""
import csv
import json
import duckdb

from archetypes import ARCHETYPES

DB_PATH = "C:/dev/fhirsql/data/train.duckdb"
CONCEPTS_PATH = "C:/dev/fhirsql/data/profile/train/selected_concepts.csv"
OUT_VERIFIED = "C:/dev/fhirsql/data/training/verified_gold.jsonl"
OUT_REJECTED = "C:/dev/fhirsql/data/training/rejected_gold.jsonl"


def sql_escape(s):
    """Escape a value for embedding as a SQL string literal (standard SQL: double up single quotes)."""
    return s.replace("'", "''")


def load_concepts():
    with open(CONCEPTS_PATH) as f:
        return list(csv.DictReader(f))


def compute_threshold(con, code, code_system, percentile=0.75):
    row = con.execute(
        "SELECT quantile_cont(valueQuantity, ?) FROM observation WHERE code = ? AND system = ? AND valueQuantity IS NOT NULL",
        [percentile, code, code_system],
    ).fetchone()
    val = row[0] if row else None
    if val is None:
        return None
    # Round to something a human would plausibly phrase as a threshold.
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


def main():
    concepts = load_concepts()
    con = duckdb.connect(DB_PATH, read_only=True)

    verified = []
    rejected = []
    rejection_reasons = {}

    for archetype in ARCHETYPES:
        source_table = archetype["source_table"]
        requires_numeric = archetype.get("requires_numeric", False)

        eligible = [c for c in concepts if c["table_name"] == source_table]
        if requires_numeric:
            # Only concepts where value_quantity is actually the primary value type
            # (checked live, not assumed) -- skip concepts that are predominantly coded/string values.
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
                rejected.append({
                    "archetype_id": archetype["id"], "concept": concept["display"],
                    "reason": "execution_error", "error": str(e), "sql": sql,
                })
                rejection_reasons["execution_error"] = rejection_reasons.get("execution_error", 0) + 1
                continue

            if len(result) == 0:
                rejected.append({"archetype_id": archetype["id"], "concept": concept["display"], "reason": "empty_result", "sql": sql})
                rejection_reasons["empty_result"] = rejection_reasons.get("empty_result", 0) + 1
                continue

            verified.append({
                "archetype_id": archetype["id"],
                "tier": archetype["tier"],
                "description": archetype["description"],
                "table": source_table,
                "code": concept["code"],
                "code_system": concept["code_system"],
                "display": concept["display"],
                "sql": sql,
                "row_count": len(result),
                "columns": columns,
            })

        n_this_archetype = sum(1 for v in verified if v["archetype_id"] == archetype["id"])
        print(f"  {archetype['id']} (tier {archetype['tier']}): {n_this_archetype}/{len(eligible)} verified")

    import os
    os.makedirs("C:/dev/fhirsql/data/training", exist_ok=True)
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
