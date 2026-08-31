"""
Reproduces PAPER.md Section 6's error-analysis table from the execution-failure
logs in results/heldout_eval/failures/*_unseen.jsonl.

Each failure log line is {archetype_id, tier, question, gold_sql, pred_sql,
failure_type, exec_error} (see rl_train.ipynb's evaluate_generation,
failure_log_path). This script compares the ILIKE search term embedded in
gold_sql vs. pred_sql's lookup CTE and buckets the difference into the
categories reported in the paper.

Usage: python analyze_unseen_failures.py
"""
import json
import os
import re
from collections import Counter

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results", "heldout_eval", "failures")

RUNS = {
    "sft_42": "sft_seed42_unseen.jsonl", "sft_43": "sft_seed43_unseen.jsonl", "sft_44": "sft_seed44_unseen.jsonl",
    "rl_42": "rl_seed42_unseen.jsonl", "rl_43": "rl_seed43_unseen.jsonl", "rl_44": "rl_seed44_unseen.jsonl",
}

_ILIKE_RE = re.compile(r"display ILIKE '%(.*?)%'")
_SUFFIX_RE = re.compile(
    r"\s*\((disorder|finding|situation|procedure|regime/therapy|morphologic abnormality|"
    r"qualifier value|body structure|substance|product|navigational concept)\)\s*$",
    re.IGNORECASE,
)


def load(fname):
    path = os.path.join(RESULTS_DIR, fname)
    if os.path.getsize(path) == 0:
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def extract_search_term(sql):
    m = _ILIKE_RE.search(sql or "")
    return m.group(1) if m else None


def categorize(gold_sql, pred_sql):
    gold_term = extract_search_term(gold_sql)
    pred_term = extract_search_term(pred_sql)
    if gold_term is None or pred_term is None:
        return "no_ilike_found"
    if gold_term == pred_term:
        return "same_search_term_other_sql_diff"
    gold_base = _SUFFIX_RE.sub("", gold_term).strip().lower()
    pred_base = _SUFFIX_RE.sub("", pred_term).strip().lower()
    gold_suffix = _SUFFIX_RE.search(gold_term)
    pred_suffix = _SUFFIX_RE.search(pred_term)
    if gold_base == pred_base:
        if gold_suffix and not pred_suffix:
            return "missing_qualifier_suffix"
        if pred_suffix and not gold_suffix:
            return "added_extra_qualifier_suffix"
        if gold_suffix and pred_suffix:
            return "wrong_qualifier_suffix"
        return "same_base_text_other_diff"
    return "substantively_different_phrase"


def main():
    all_rows = {k: load(f) for k, f in RUNS.items()}
    for k, rows in all_rows.items():
        print(f"{k}: {len(rows)} execution failures")

    cat_counts = Counter()
    total = 0
    for rows in all_rows.values():
        for r in rows:
            total += 1
            cat_counts[categorize(r.get("gold_sql"), r.get("pred_sql"))] += 1

    print(f"\ntotal execution failures across 6 runs: {total}\n")
    label = {
        "added_extra_qualifier_suffix": "Added an extra qualifier suffix not present in gold",
        "substantively_different_phrase": "Substantively different search phrase",
        "wrong_qualifier_suffix": "Wrong qualifier suffix",
        "same_search_term_other_sql_diff": "Same search term, other SQL difference",
        "missing_qualifier_suffix": "Missing a qualifier suffix present in gold",
        "same_base_text_other_diff": "Same base phrase, other minor difference",
        "no_ilike_found": "No ILIKE lookup found in gold or pred (different archetype shape)",
    }
    for cat, n in cat_counts.most_common():
        print(f"  {label.get(cat, cat):<55} {n:4d}  ({n / total:.1%})")


if __name__ == "__main__":
    main()
