"""
Back-translates every category's verified (plan, sql) gold artifacts into
full SFT rows, where the target is `plan JSON` followed by the compiled SQL
in a markdown-fenced code block -- one continuous completion, not raw SQL
alone (see plan_schema.py, PAPER.md Section 1).

Target format: `json.dumps(plan, indent=2)` then
`"\\n\\n```sql\\n" + sql + "\\n```"`. Chosen over a bare-newline separator
for the RL stage: a fenced code block gives a single, unambiguous regex
extraction point (`` ```sql\\s*\\n(.*?)\\n``` ``) that's robust even if the
model's plan JSON is malformed or contains stray braces, and
Qwen2.5-Coder-14B-Instruct (the base model) is heavily pretrained on exactly
this markdown-fence convention for code. Applied uniformly, including to
abstention rows -- the compiled "SQL" for an abstain=true plan is just the
literal `UNANSWERABLE` token, still inside the fence, so the RL parser needs
exactly one extraction rule for every row shape, not a special case for
abstention.

NL question phrasing reuses question_templates.py/personas.py (main
archetypes) and each category's own CONCEPT_TEMPLATES/STRUCTURAL_TEMPLATES
(operational/quality_kpi/regulatory) -- only the SQL target's shape changes,
not what the question asks.
"""
import json

from question_templates import TEMPLATES, clean_concept, extract_threshold, fix_articles
from assemble_sft_rows import check_paraphrase, COMPANION_DISPLAY

import generate_operational_gold as _op_gold
import generate_quality_kpi_gold as _qk_gold
import generate_regulatory_gold as _reg_gold

OUT_PATH = "C:/dev/fhirsql-phase2/data/training/sft_final_plan.jsonl"
OUT_FLAGGED_PATH = "C:/dev/fhirsql-phase2/data/training/sft_final_plan_flagged.jsonl"

UNANSWERABLE_SFT_PATH = "C:/dev/fhirsql-phase2/data/training/sft_unanswerable.jsonl"
ABSTENTION_TOKEN = "UNANSWERABLE"


def compile_target(plan, sql):
    return json.dumps(plan, indent=2) + "\n\n```sql\n" + sql.strip() + "\n```"


def rows_from_main():
    with open("C:/dev/fhirsql-phase2/data/training/verified_gold_plan.jsonl") as f:
        gold_rows = [json.loads(line) for line in f]

    rows, flagged = [], []
    for gold in gold_rows:
        archetype_id = gold["archetype_id"]
        templates = TEMPLATES.get(archetype_id)
        if not templates:
            continue

        concept = clean_concept(gold["display"])
        companion_display = COMPANION_DISPLAY.get(archetype_id)

        fmt_args = {"concept": concept}
        if any("{threshold}" in t for _, t in templates):
            threshold = extract_threshold(gold["sql"])
            if threshold is None:
                continue
            fmt_args["threshold"] = threshold

        for persona, template in templates:
            question = template.format(**fmt_args)
            flags = check_paraphrase(question, gold["display"], companion_display)
            row = {
                "archetype_id": archetype_id, "tier": gold["tier"], "persona": persona,
                "question": question, "schema_ref": "schema/schema.sql",
                "target": compile_target(gold["plan"], gold["sql"]),
                "gold_sql": gold["sql"], "gold_plan": gold["plan"],
                "concept_display": gold["display"], "flags": flags,
            }
            rows.append(row)
            if flags:
                flagged.append(row)
    return rows, flagged


def rows_from_concept_structural(gold_path, concept_templates, structural_templates):
    with open(gold_path) as f:
        gold_rows = [json.loads(line) for line in f]

    rows = []
    for gold in gold_rows:
        target = compile_target(gold["plan"], gold["sql"])
        if gold["concept_type"] == "concept":
            templates = concept_templates[gold["archetype_id"]]
            concept = clean_concept(gold["display"])
            for persona, template in templates:
                question = fix_articles(template.format(concept=concept))
                rows.append({
                    "archetype_id": gold["archetype_id"], "tier": gold["tier"], "persona": persona,
                    "question": question, "schema_ref": "schema/schema.sql",
                    "target": target, "gold_sql": gold["sql"], "gold_plan": gold["plan"],
                    "concept_display": gold["display"], "flags": [],
                })
        else:
            templates = structural_templates[gold["archetype_id"]]
            for persona, question in templates:
                rows.append({
                    "archetype_id": gold["archetype_id"], "tier": gold["tier"], "persona": persona,
                    "question": question, "schema_ref": "schema/schema.sql",
                    "target": target, "gold_sql": gold["sql"], "gold_plan": gold["plan"],
                    "concept_display": None, "flags": [],
                })
    return rows


def rows_from_regulatory():
    with open("C:/dev/fhirsql-phase2/data/training/verified_gold_plan_regulatory.jsonl") as f:
        gold_rows = [json.loads(line) for line in f]

    rows = []
    for gold in gold_rows:
        templates = _reg_gold.REG_TEMPLATES[gold["archetype_id"]]
        concept = clean_concept(gold["display"])
        target = compile_target(gold["plan"], gold["sql"])
        for persona, template in templates:
            question = fix_articles(template.format(concept=concept))
            rows.append({
                "archetype_id": gold["archetype_id"], "tier": gold["tier"], "persona": persona,
                "question": question, "schema_ref": "schema/schema.sql",
                "target": target, "gold_sql": gold["sql"], "gold_plan": gold["plan"],
                "concept_display": gold["display"], "flags": [],
            })
    return rows


def rows_from_unanswerable():
    """Reuses the existing abstention SFT rows verbatim for `question`/`persona`/etc.,
    only rewriting `sql` -> `target` in the new plan+fence format (plan is always
    {"abstain": true}, sql is always the literal ABSTENTION_TOKEN)."""
    rows = []
    with open(UNANSWERABLE_SFT_PATH) as f:
        for line in f:
            r = json.loads(line)
            r["target"] = compile_target({"abstain": True}, ABSTENTION_TOKEN)
            r["gold_sql"] = ABSTENTION_TOKEN
            r["gold_plan"] = {"abstain": True}
            del r["sql"]
            rows.append(r)
    return rows


def main():
    main_rows, main_flagged = rows_from_main()
    op_rows = rows_from_concept_structural(
        "C:/dev/fhirsql-phase2/data/training/verified_gold_plan_operational.jsonl",
        _op_gold.CONCEPT_TEMPLATES, _op_gold.STRUCTURAL_TEMPLATES,
    )
    qk_rows = rows_from_concept_structural(
        "C:/dev/fhirsql-phase2/data/training/verified_gold_plan_quality_kpi.jsonl",
        _qk_gold.CONCEPT_TEMPLATES, _qk_gold.STRUCTURAL_TEMPLATES,
    )
    reg_rows = rows_from_regulatory()
    unans_rows = rows_from_unanswerable()

    all_rows = main_rows + op_rows + qk_rows + reg_rows + unans_rows

    with open(OUT_PATH, "w") as f:
        for r in all_rows:
            f.write(json.dumps(r) + "\n")
    with open(OUT_FLAGGED_PATH, "w") as f:
        for r in main_flagged:
            f.write(json.dumps(r) + "\n")

    print(f"main: {len(main_rows)}  operational: {len(op_rows)}  quality_kpi: {len(qk_rows)}  "
          f"regulatory: {len(reg_rows)}  unanswerable: {len(unans_rows)}")
    print(f"TOTAL: {len(all_rows)} -> {OUT_PATH}")
    print(f"Flagged (main only, for review): {len(main_flagged)} -> {OUT_FLAGGED_PATH}")


if __name__ == "__main__":
    main()
