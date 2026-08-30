"""
Assembles the unanswerable/abstention training rows.

No DB execution here (there's no SQL to run) -- "verification" for this
category means confirming, by inspection of schema/schema.sql, that the
referenced data genuinely has no column/table to answer it. That reasoning
is recorded per-category in unanswerable_archetypes.py's `excluded_concept`
field rather than re-derived here.
"""
import csv
import json

from unanswerable_archetypes import (
    ABSTENTION_TOKEN, FIXED, PARAMETERIZED_TEMPLATES,
    DEVICE_TYPES, INSURANCE_PAYERS, DEPARTMENT_NAMES, SUPPLY_ITEMS,
)
from question_templates import clean_concept, fix_articles

CONCEPTS_PATH = "C:/dev/fhirsql/data/profile/train/selected_concepts.csv"
OUT_SFT = "C:/dev/fhirsql/data/training/sft_unanswerable.jsonl"

N_CONCEPTS_PER_PARAM_CATEGORY = {
    "unans_claim_amount": ("condition", 40),
    "unans_claim_status": ("procedure", 40),
    "unans_document_content": ("condition", 40),
    "unans_medication_administration_actual": ("medication_request", 40),
    "unans_pharmacy_stock": ("medication_request", 30),
}

CURATED_INSTANCE_LISTS = {
    "unans_device_implanted": DEVICE_TYPES,
    "unans_insurance_payer": INSURANCE_PAYERS,
    "unans_department_by_name": DEPARTMENT_NAMES,
    "unans_supply_inventory": SUPPLY_ITEMS,
}


def load_concepts_by_table():
    """Skip concepts whose display name reads awkwardly mid-sentence: multi-
    ingredient pack notations with literal braces (e.g. "{28 (norethindrone
    0.35 MG...)} Pack [Errin 28 Day]") or overly long descriptive phrases.
    The abstention answer is correct regardless of which concept is named
    (the category is absent no matter what), so this is a naturalness filter
    only, not a correctness one."""
    with open(CONCEPTS_PATH) as f:
        rows = list(csv.DictReader(f))
    by_table = {}
    for r in rows:
        display = r["display"]
        if "{" in display or len(display) > 55:
            continue
        by_table.setdefault(r["table_name"], []).append(display)
    return by_table


def main():
    concepts_by_table = load_concepts_by_table()
    rows = []

    # Fixed, non-parameterized categories
    for entry in FIXED:
        for persona, question in entry["questions"]:
            rows.append({
                "archetype_id": entry["id"], "tier": 5, "persona": persona,
                "question": question, "schema_ref": "schema/schema.sql",
                "sql": ABSTENTION_TOKEN, "excluded_concept": entry["excluded_concept"],
                "concept_display": None, "flags": [],
            })

    # Concept-parameterized categories (reuse selected_concepts.csv)
    for archetype_id, (table, n) in N_CONCEPTS_PER_PARAM_CATEGORY.items():
        templates = PARAMETERIZED_TEMPLATES[archetype_id]
        instances = concepts_by_table.get(table, [])[:n]
        for display in instances:
            concept = clean_concept(display)
            for persona, template in templates:
                question = fix_articles(template.format(concept=concept))
                rows.append({
                    "archetype_id": archetype_id, "tier": 5, "persona": persona,
                    "question": question, "schema_ref": "schema/schema.sql",
                    "sql": ABSTENTION_TOKEN,
                    "excluded_concept": f"billing/document/administration/inventory data not in schema (instance: {display})",
                    "concept_display": display, "flags": [],
                })

    # Curated-instance-list parameterized categories
    for archetype_id, instances in CURATED_INSTANCE_LISTS.items():
        templates = PARAMETERIZED_TEMPLATES[archetype_id]
        for instance in instances:
            for persona, template in templates:
                question = fix_articles(template.format(concept=instance))
                rows.append({
                    "archetype_id": archetype_id, "tier": 5, "persona": persona,
                    "question": question, "schema_ref": "schema/schema.sql",
                    "sql": ABSTENTION_TOKEN,
                    "excluded_concept": f"device/insurance/department/supply data not in schema (instance: {instance})",
                    "concept_display": instance, "flags": [],
                })

    with open(OUT_SFT, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    print(f"Total unanswerable rows: {len(rows)} -> {OUT_SFT}")
    from collections import Counter
    print("By archetype:", dict(Counter(r["archetype_id"] for r in rows)))
    print("By persona:", dict(Counter(r["persona"] for r in rows)))


if __name__ == "__main__":
    main()
