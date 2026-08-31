"""
Quantifies how discriminative `gen_exec_match` actually is on the held-out UNSEEN arm.

The unseen arm is restricted to low-prevalence concepts (1-3 patients each) under
tier-1/2 archetypes, so its gold answers are small scalars. That raises a concrete
risk: a prediction that resolves the WRONG clinical concept can still return the
same result set as gold and be scored execution-correct.

This script bounds that risk from the committed data alone, without needing model
predictions. For every pair of distinct concepts instantiated under the SAME
archetype, it executes both gold queries and checks whether they return identical
results. The resulting collision rate is the probability that confusing one unseen
concept for another within an archetype would go undetected by execution match.

Reported in PAPER.md Section 6 / Section 7.

Usage: python analyze_unseen_discriminativeness.py
"""
import json
import os
from collections import Counter, defaultdict

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(ROOT, "data", "training", "heldout_benchmark_plan_unseen.jsonl")
DB = os.path.join(ROOT, "data", "heldout.duckdb")


def is_abstention(row):
    plan = row.get("gold_plan")
    return row.get("gold_sql") == "ABSTENTION" or row.get("gold_sql") == "UNANSWERABLE" or (
        isinstance(plan, dict) and plan.get("abstain"))


def main():
    rows = [json.loads(l) for l in open(BENCH, encoding="utf-8")]
    answerable = [r for r in rows if not is_abstention(r)]

    # one representative row per distinct gold SQL
    unique = {}
    for r in answerable:
        unique.setdefault(r["gold_sql"], r)
    print(f"unseen answerable rows: {len(answerable)}   distinct gold SQL: {len(unique)}")

    con = duckdb.connect(DB, read_only=True)

    def execute(sql):
        try:
            return tuple(sorted(repr(t) for t in con.execute(sql).fetchall()))
        except Exception as exc:
            return ("ERROR", str(exc)[:80])

    by_archetype = defaultdict(list)
    shapes = Counter()
    scalars = Counter()
    for sql, row in unique.items():
        out = execute(sql)
        if out and out[0] == "ERROR":
            shapes["execution error"] += 1
            continue
        shapes[f"{len(out)} row(s)"] += 1
        if len(out) == 1:
            scalars[out[0]] += 1
        by_archetype[row["archetype_id"]].append((row.get("concept_display"), out))

    print("\n-- result-set shape of gold answers --")
    for shape, n in shapes.most_common():
        print(f"   {shape:<18} {n}")

    print("\n-- most common single-row answers --")
    for value, n in scalars.most_common(8):
        print(f"   {value:<24} {n}")

    print("\n-- collision analysis (distinct concepts, same archetype, identical gold answer) --")
    total_pairs = collide_pairs = 0
    per_arch = []
    for archetype, items in sorted(by_archetype.items()):
        groups = defaultdict(list)
        for concept, out in items:
            groups[out].append(concept)
        n = len(items)
        pairs = n * (n - 1) // 2
        coll = sum(len(c) * (len(c) - 1) // 2 for c in groups.values() if len(c) > 1)
        total_pairs += pairs
        collide_pairs += coll
        if pairs:
            per_arch.append((archetype, n, pairs, coll, coll / pairs))

    for archetype, n, pairs, coll, rate in sorted(per_arch, key=lambda x: -x[4]):
        print(f"   {archetype:<38} concepts={n:>3} pairs={pairs:>5} collisions={coll:>5} ({rate:.1%})")

    print(f"\n   TOTAL: {collide_pairs}/{total_pairs} within-archetype concept pairs "
          f"return identical gold answers ({collide_pairs / total_pairs:.1%})")
    print("\n   Interpretation: confusing one unseen concept for another within the same")
    print("   archetype goes undetected by execution match roughly this often, so the")
    print("   unseen arm's gen_exec_match is an upper bound on true concept-resolution")
    print("   accuracy. gen_exact_match / gen_structure_match are not subject to this")
    print("   (they compare query text) and bound the same quantity from below.")

    con.close()


if __name__ == "__main__":
    main()
