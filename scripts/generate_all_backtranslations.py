"""
Full-scale back-translation: instantiate question_templates.py's
per-archetype templates against all 2,284 verified gold artifacts (not just
the 40-concept proof-of-pipeline batch), then assemble into final SFT rows
with the same auto-reject filter check as batch 1.

Supersedes back_translations_batch1.py / assemble_sft_rows.py's batch-1-only
output -- this covers every verified artifact, including the 40 batch-1 already
did (regenerated from the now-parameterized version of the same phrasing, for
consistency of a single source of truth).
"""
import json

from question_templates import TEMPLATES, clean_concept, extract_threshold
from assemble_sft_rows import check_paraphrase, COMPANION_DISPLAY, SCHEMA_PATH

GOLD_PATH = "C:/dev/fhirsql/data/training/verified_gold.jsonl"
OUT_PATH = "C:/dev/fhirsql/data/training/sft_all.jsonl"
FLAGGED_OUT_PATH = "C:/dev/fhirsql/data/training/sft_all_flagged.jsonl"


def main():
    with open(GOLD_PATH) as f:
        gold_rows = [json.loads(line) for line in f]

    rows = []
    flagged = []
    skipped_no_template = 0

    for gold in gold_rows:
        archetype_id = gold["archetype_id"]
        templates = TEMPLATES.get(archetype_id)
        if not templates:
            skipped_no_template += 1
            continue

        concept = clean_concept(gold["display"])
        companion_display = COMPANION_DISPLAY.get(archetype_id)

        fmt_args = {"concept": concept}
        if "{threshold}" in templates[0][1] or any("{threshold}" in t for _, t in templates):
            threshold = extract_threshold(gold["sql"])
            if threshold is None:
                skipped_no_template += 1
                continue
            fmt_args["threshold"] = threshold

        for persona, template in templates:
            question = template.format(**fmt_args)
            flags = check_paraphrase(question, gold["display"], companion_display)
            row = {
                "archetype_id": archetype_id,
                "tier": gold["tier"],
                "persona": persona,
                "question": question,
                "schema_ref": "schema/schema.sql",
                "sql": gold["sql"].strip(),
                "concept_display": gold["display"],
                "concept_code": gold["code"],
                "flags": flags,
            }
            rows.append(row)
            if flags:
                flagged.append(row)

    with open(OUT_PATH, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with open(FLAGGED_OUT_PATH, "w") as f:
        for r in flagged:
            f.write(json.dumps(r) + "\n")

    print(f"Gold artifacts: {len(gold_rows)}, skipped (no template/no threshold): {skipped_no_template}")
    print(f"Assembled {len(rows)} SFT rows -> {OUT_PATH}")
    print(f"Flagged for review: {len(flagged)} ({100*len(flagged)/len(rows):.1f}%) -> {FLAGGED_OUT_PATH}")

    from collections import Counter
    print("By tier:", dict(Counter(r["tier"] for r in rows)))
    print("By persona:", dict(Counter(r["persona"] for r in rows)))


if __name__ == "__main__":
    main()
