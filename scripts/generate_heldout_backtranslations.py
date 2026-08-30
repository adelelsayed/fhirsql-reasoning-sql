"""
Heldout benchmark back-translation -- mirrors generate_all_backtranslations.py
exactly (same TEMPLATES, same auto-reject check), just retargeted at each
concept arm's verified gold file produced by generate_heldout_gold.py. Reuses
train's question_templates.py/personas.py as-is -- no new template design
needed for the heldout benchmark.

Usage: python generate_heldout_backtranslations.py familiar|unseen
"""
import json
import sys

from question_templates import TEMPLATES, clean_concept, extract_threshold
from assemble_sft_rows import check_paraphrase, COMPANION_DISPLAY

ARMS = {
    "familiar": {
        "gold_path": "C:/dev/fhirsql/data/training/heldout_verified_gold_familiar.jsonl",
        "out_path": "C:/dev/fhirsql/data/training/heldout_sft_familiar.jsonl",
        "flagged_out_path": "C:/dev/fhirsql/data/training/heldout_sft_familiar_flagged.jsonl",
    },
    "unseen": {
        "gold_path": "C:/dev/fhirsql/data/training/heldout_verified_gold_unseen.jsonl",
        "out_path": "C:/dev/fhirsql/data/training/heldout_sft_unseen.jsonl",
        "flagged_out_path": "C:/dev/fhirsql/data/training/heldout_sft_unseen_flagged.jsonl",
    },
}


def run(arm):
    cfg = ARMS[arm]
    with open(cfg["gold_path"]) as f:
        gold_rows = [json.loads(line) for line in f]

    rows, flagged = [], []
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
        if any("{threshold}" in t for _, t in templates):
            threshold = extract_threshold(gold["sql"])
            if threshold is None:
                skipped_no_template += 1
                continue
            fmt_args["threshold"] = threshold

        for persona, template in templates:
            question = template.format(**fmt_args)
            flags = check_paraphrase(question, gold["display"], companion_display)
            row = {
                "archetype_id": archetype_id, "tier": gold["tier"], "persona": persona,
                "question": question, "schema_ref": "schema/schema.sql", "sql": gold["sql"].strip(),
                "concept_display": gold["display"], "concept_code": gold["code"], "flags": flags,
            }
            rows.append(row)
            if flags:
                flagged.append(row)

    with open(cfg["out_path"], "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with open(cfg["flagged_out_path"], "w") as f:
        for r in flagged:
            f.write(json.dumps(r) + "\n")

    print(f"[{arm}] Gold artifacts: {len(gold_rows)}, skipped (no template/no threshold): {skipped_no_template}")
    print(f"[{arm}] Assembled {len(rows)} rows -> {cfg['out_path']}")
    pct = 100 * len(flagged) / len(rows) if rows else 0
    print(f"[{arm}] Flagged for review: {len(flagged)} ({pct:.1f}%) -> {cfg['flagged_out_path']}")

    from collections import Counter
    print(f"[{arm}] By tier:", dict(Counter(r["tier"] for r in rows)))


if __name__ == "__main__":
    arm = sys.argv[1] if len(sys.argv) > 1 else None
    if arm not in ARMS:
        print("Usage: python generate_heldout_backtranslations.py familiar|unseen")
        sys.exit(1)
    run(arm)
