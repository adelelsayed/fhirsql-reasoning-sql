"""
Plan-carrying counterpart to generate_heldout_backtranslations.py:
same TEMPLATES, same auto-reject check, retargeted at each arm's
heldout_verified_gold_plan_{arm}.jsonl, with the target compiled the same
way as the train side (see generate_all_backtranslations_plan.py):
`json.dumps(plan, indent=2)` + fenced ```sql block.

Usage: python generate_heldout_backtranslations_plan.py familiar|unseen
"""
import json
import sys

from question_templates import TEMPLATES, clean_concept, extract_threshold
from assemble_sft_rows import check_paraphrase, COMPANION_DISPLAY
from generate_all_backtranslations_plan import compile_target

ARMS = {
    "familiar": {
        "gold_path": "C:/dev/fhirsql-phase2/data/training/heldout_verified_gold_plan_familiar.jsonl",
        "out_path": "C:/dev/fhirsql-phase2/data/training/heldout_benchmark_plan_familiar.jsonl",
        "flagged_out_path": "C:/dev/fhirsql-phase2/data/training/heldout_benchmark_plan_familiar_flagged.jsonl",
    },
    "unseen": {
        "gold_path": "C:/dev/fhirsql-phase2/data/training/heldout_verified_gold_plan_unseen.jsonl",
        "out_path": "C:/dev/fhirsql-phase2/data/training/heldout_benchmark_plan_unseen.jsonl",
        "flagged_out_path": "C:/dev/fhirsql-phase2/data/training/heldout_benchmark_plan_unseen_flagged.jsonl",
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

        target = compile_target(gold["plan"], gold["sql"])
        for persona, template in templates:
            question = template.format(**fmt_args)
            flags = check_paraphrase(question, gold["display"], companion_display)
            row = {
                "archetype_id": archetype_id, "tier": gold["tier"], "persona": persona,
                "question": question, "schema_ref": "schema/schema.sql",
                "target": target, "gold_sql": gold["sql"], "gold_plan": gold["plan"],
                "concept_display": gold["display"], "flags": flags,
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


if __name__ == "__main__":
    arm = sys.argv[1] if len(sys.argv) > 1 else None
    if arm not in ARMS:
        print("Usage: python generate_heldout_backtranslations_plan.py familiar|unseen")
        sys.exit(1)
    run(arm)
