"""
Assembles back-translated paraphrases + verified gold SQL into final SFT-format
training rows, using the frozen prompt format: schema DDL + question +
instruction -> gold SQL.

Also runs the auto-reject check: flag (not silently drop) any
paraphrase that appears to have dropped a filter present in the source SQL --
implemented as a soft keyword-presence check against the concept's display
name and, where present, a companion concept's display name (for archetypes
with a fixed second clinical anchor). Flags are for human review, not
automatic deletion, since valid synonyms (e.g. "high blood pressure" for
"essential hypertension") would false-positive under pure keyword matching.

Output rows carry `schema_ref` (a pointer to schema/schema.sql), not the full
DDL text inline -- embedding the ~150-line schema in every one of ~9,000+ rows
would bloat the file ~30x for zero benefit (the schema is identical across
every row). Join it from schema/schema.sql at actual SFT-training time.
"""
import json
import re

SCHEMA_PATH = "C:/dev/fhirsql/schema/schema.sql"

STOPWORDS = {"disorder", "finding", "situation", "procedure", "substance", "unspecified", "class", "cause"}


def key_terms(display):
    words = re.findall(r"[a-zA-Z]+", display.lower())
    return [w for w in words if len(w) > 3 and w not in STOPWORDS]


def _prefix_match(term, q_lower, prefix_len=6):
    """Fuzzy match tolerant of plurals/adjectival forms (platelet/platelets,
    hypertension/hypertensive, anemia/anemic) without a real stemmer: a
    sufficiently long shared prefix counts as the same concept."""
    p = term[:prefix_len] if len(term) >= prefix_len else term
    return p in q_lower


def check_paraphrase(question, display, companion_display=None):
    """Soft check: does the question reference at least one significant term
    from the concept's display name (and the companion's, if any)? Returns a
    list of flags (empty = passed)."""
    q_lower = question.lower()
    flags = []

    terms = key_terms(display)
    if terms and not any(_prefix_match(t, q_lower) for t in terms):
        flags.append(f"no_keyword_match:{display}")

    if companion_display:
        c_terms = key_terms(companion_display)
        if c_terms and not any(_prefix_match(t, q_lower) for t in c_terms):
            flags.append(f"no_companion_keyword_match:{companion_display}")

    return flags


# Fixed companion concepts used by tier-3/4 archetypes with a hardcoded second anchor.
COMPANION_DISPLAY = {
    "t3_medication_and_condition": "Essential hypertension",
    "t3_diagnostic_report_with_condition": "Essential hypertension",
    "t3_observation_and_medication": "lisinopril",
    "t3_allergy_and_condition_count": "Anemia",
    "t4_most_recent_observation_per_patient": "Essential hypertension",
    "t4_condition_then_procedure_30d": "Colonoscopy",
    "t4_time_from_condition_to_medication": "lisinopril",
}


def assemble(gold_path, paraphrases, out_path, flagged_out_path):
    with open(gold_path) as f:
        gold_by_archetype = {}
        for line in f:
            row = json.loads(line)
            gold_by_archetype[row["archetype_id"]] = row

    rows = []
    flagged = []
    for archetype_id, para_list in paraphrases.items():
        gold = gold_by_archetype.get(archetype_id)
        if gold is None:
            print(f"WARNING: no gold artifact found for {archetype_id}, skipping")
            continue
        companion_display = COMPANION_DISPLAY.get(archetype_id)

        for persona, question in para_list:
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

    with open(out_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with open(flagged_out_path, "w") as f:
        for r in flagged:
            f.write(json.dumps(r) + "\n")

    print(f"Assembled {len(rows)} SFT rows -> {out_path}")
    print(f"Flagged for review: {len(flagged)} -> {flagged_out_path}")
    return rows, flagged


if __name__ == "__main__":
    from back_translations_batch1 import PARAPHRASES
    assemble(
        "C:/dev/fhirsql/data/training/batch1_sample.jsonl",
        PARAPHRASES,
        "C:/dev/fhirsql/data/training/sft_batch1.jsonl",
        "C:/dev/fhirsql/data/training/sft_batch1_flagged.jsonl",
    )
