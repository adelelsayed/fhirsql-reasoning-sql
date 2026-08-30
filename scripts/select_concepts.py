"""
Selects ~100 concepts from the concept bank (data/profile/train/concept_bank.csv)
for the archetype x concept factory.

Curation rules (beyond the >=50-patient-coverage floor the plan specifies):
  - Manual exclusion list: pure administrative/SDOH-demographic "findings" Synthea
    codes as Condition resources (employment status, education level, criminal
    record, medication-review-due boilerplate) and administrative Procedure
    codes (medication reconciliation, dental referral) that are near-universal
    and carry no differential clinical signal -- a WHERE filter on these barely
    filters anything, which is a weak training signal for schema/value precision.
  - Coverage ceiling (90% of population) applied ONLY to condition/procedure/
    encounter, where the archetype semantics are "which/how many patients have
    X" (a near-universal code doesn't discriminate). NOT applied to observation/
    diagnostic_report, where archetypes are more often "compute stats of X"
    (ubiquitous vitals like heart rate are fine subjects for that).
  - medication_request/allergy/immunization: no additional filtering, the raw
    >=50-patient concepts here are already clinically genuine (real drugs,
    real allergens, real vaccines).

Selects roughly proportional to how a real "hospital analyst" benchmark would
weight tables: conditions and observations get the most concepts (most common
real-world query targets), medication_request/procedure next, then
allergy/immunization/encounter/diagnostic_report for archetype diversity.
"""
import csv

CONCEPT_BANK = "C:/dev/fhirsql/data/profile/train/concept_bank.csv"
OUT_PATH = "C:/dev/fhirsql/data/profile/train/selected_concepts.csv"

POPULATION_SIZE = 18999
COVERAGE_CEILING_PCT = 0.90  # applied to condition/procedure/encounter only

ADMIN_EXCLUDE_CODES = {
    "314529007",  # Medication review due (situation)
    "160903007",  # Full-time employment (finding)
    "160904001",  # Part-time employment (finding)
    "741062008",  # Not in labor force (finding)
    "73438004",   # Unemployed (finding)
    "224299000",  # Received higher education (finding)
    "473461003",  # Educated to high school level (finding)
    "266948004",  # Has a criminal record (finding)
    "430193006",  # Medication reconciliation (procedure)
    "103697008",  # Patient referral for dental care (procedure)
}

# Target concept counts per table (scaled up from an initial ~100 pass, which
# yielded only 674 verified gold artifacts vs. a ~3,200 target -- each
# archetype is scoped to one table, so achievable cross-product is much lower
# than a naive 40x100 arithmetic assumes. Scaling concept
# count is the cheap lever (we have 1,248 eligible candidates total, only used
# 108). Bounded by how many candidates actually exist per table (allergy/
# immunization only have 21 each; encounter/diagnostic_report smaller pools too).
TARGETS = {
    "condition": 90,
    "observation": 70,
    "medication_request": 60,
    "procedure": 45,
    "allergy": 21,
    "immunization": 21,
    "encounter": 45,
    "diagnostic_report": 30,
}

COVERAGE_CEILING_TABLES = {"condition", "procedure", "encounter"}


def load_concepts():
    with open(CONCEPT_BANK) as f:
        return list(csv.DictReader(f))


def select():
    rows = load_concepts()
    selected = []
    for table, target_n in TARGETS.items():
        candidates = [r for r in rows if r["table_name"] == table]
        candidates = [r for r in candidates if r["code"] not in ADMIN_EXCLUDE_CODES]
        candidates = [r for r in candidates if int(r["distinct_patient_count"]) >= 50]
        if table in COVERAGE_CEILING_TABLES:
            ceiling = POPULATION_SIZE * COVERAGE_CEILING_PCT
            candidates = [r for r in candidates if int(r["distinct_patient_count"]) <= ceiling]
        candidates.sort(key=lambda r: -int(r["distinct_patient_count"]))
        # Spread across the coverage range rather than pure top-N: take every
        # Nth candidate so we get a mix of common and rarer concepts, not just
        # the highest-coverage handful.
        if len(candidates) <= target_n:
            picked = candidates
        else:
            step = len(candidates) / target_n
            picked = [candidates[int(i * step)] for i in range(target_n)]
        selected.extend(picked)
        print(f"  {table}: {len(picked)} concepts selected (from {len(candidates)} eligible candidates)")

    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["table_name", "code", "code_system", "display", "row_count", "distinct_patient_count"])
        writer.writeheader()
        for r in selected:
            writer.writerow(r)

    print(f"\nTotal selected: {len(selected)} concepts -> {OUT_PATH}")


if __name__ == "__main__":
    select()
