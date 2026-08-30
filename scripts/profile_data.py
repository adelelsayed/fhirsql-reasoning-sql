"""
Data profile for the 10 core clinical tables, both populations.

Produces three CSVs per population under data/profile/<population>/:
  - table_summary.csv:    row_count, distinct_patient_count per table
  - column_fill_rates.csv: non-null fill rate per column, per table
  - concept_bank.csv:     per (table, code, code_system) triple -- row_count and
                          distinct_patient_count. This is the concept bank the
                          archetype x concept factory draws ~100 concepts from,
                          filtered to >=50-patient coverage.

Run after scripts/flatten_to_duckdb.py.
"""
import os
import duckdb

DATA_ROOT = "C:/dev/fhirsql/data"

CORE_TABLES = [
    "patient", "condition", "observation", "medication_request", "encounter",
    "procedure", "immunization", "allergy", "careplan", "diagnostic_report",
]

# Tables with a (code, system) pair suitable for the concept bank. Most tables
# use the generic FHIR Coding.code/.system pair (column names "code"/"system"),
# but encounter/immunization/careplan use their own FHIR field's name instead
# (Encounter.type, Immunization.vaccineCode, CarePlan.category) -- this map
# says which columns to read per table, output is still normalized to
# "code"/"code_system" in our own concept_bank.csv (that's our pipeline's
# own artifact, not shown to any LLM).
CODED_TABLES = [
    "condition", "observation", "medication_request", "encounter",
    "procedure", "immunization", "allergy", "careplan", "diagnostic_report",
]
CODE_COLUMNS = {
    "encounter": ("type_code", "type_system", "type_display"),
    "immunization": ("vaccineCode", "vaccineCode_system", "vaccineCode_display"),
    "careplan": ("category_code", "category_system", "category_display"),
}
DEFAULT_CODE_COLUMNS = ("code", "system", "display")


def profile_population(population):
    db_path = f"{DATA_ROOT}/{population}.duckdb"
    con = duckdb.connect(db_path, read_only=True)
    out_dir = f"{DATA_ROOT}/profile/{population}"
    os.makedirs(out_dir, exist_ok=True)

    # -- table_summary --
    summary_rows = []
    for table in CORE_TABLES:
        row_count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if table == "patient":
            distinct_patients = row_count
        else:
            distinct_patients = con.execute(
                f"SELECT COUNT(DISTINCT patient_id) FROM {table}"
            ).fetchone()[0]
        summary_rows.append((table, row_count, distinct_patients))
        print(f"  [{population}] {table}: {row_count} rows, {distinct_patients} distinct patients")

    con.execute("CREATE OR REPLACE TEMP TABLE _table_summary(table_name VARCHAR, row_count BIGINT, distinct_patient_count BIGINT)")
    con.executemany("INSERT INTO _table_summary VALUES (?, ?, ?)", summary_rows)
    con.execute(f"COPY _table_summary TO '{out_dir}/table_summary.csv' (HEADER, DELIMITER ',')")

    # -- column_fill_rates --
    fill_rows = []
    for table in CORE_TABLES:
        total = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        cols = con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ? ORDER BY ordinal_position",
            [table],
        ).fetchall()
        for (col,) in cols:
            non_null = con.execute(f'SELECT COUNT("{col}") FROM {table}').fetchone()[0]
            pct = round(100.0 * non_null / total, 2) if total else 0.0
            fill_rows.append((table, col, total, non_null, pct))

    con.execute("""
        CREATE OR REPLACE TEMP TABLE _fill_rates(
            table_name VARCHAR, column_name VARCHAR, total_rows BIGINT,
            non_null_count BIGINT, fill_rate_pct DOUBLE
        )
    """)
    con.executemany("INSERT INTO _fill_rates VALUES (?, ?, ?, ?, ?)", fill_rows)
    con.execute(f"COPY _fill_rates TO '{out_dir}/column_fill_rates.csv' (HEADER, DELIMITER ',')")

    # -- concept_bank: per (table, code, code_system) -- the concept factory input --
    con.execute("CREATE OR REPLACE TEMP TABLE _concept_bank(table_name VARCHAR, code VARCHAR, code_system VARCHAR, display VARCHAR, row_count BIGINT, distinct_patient_count BIGINT)")
    for table in CODED_TABLES:
        code_col, system_col, display_col = CODE_COLUMNS.get(table, DEFAULT_CODE_COLUMNS)
        con.execute(f"""
            INSERT INTO _concept_bank
            SELECT
                '{table}' AS table_name,
                {code_col} AS code,
                {system_col} AS code_system,
                MIN({display_col}) AS display,
                COUNT(*) AS row_count,
                COUNT(DISTINCT patient_id) AS distinct_patient_count
            FROM {table}
            WHERE {code_col} IS NOT NULL
            GROUP BY {code_col}, {system_col}
        """)
    con.execute(f"""
        COPY (SELECT * FROM _concept_bank ORDER BY distinct_patient_count DESC)
        TO '{out_dir}/concept_bank.csv' (HEADER, DELIMITER ',')
    """)
    n_concepts = con.execute("SELECT COUNT(*) FROM _concept_bank").fetchone()[0]
    n_concepts_50 = con.execute("SELECT COUNT(*) FROM _concept_bank WHERE distinct_patient_count >= 50").fetchone()[0]
    n_code_systems = con.execute("SELECT COUNT(DISTINCT code_system) FROM _concept_bank").fetchone()[0]
    print(f"  [{population}] concept bank: {n_concepts} distinct (table, code, code_system) concepts, "
          f"{n_concepts_50} with >=50-patient coverage, {n_code_systems} distinct code systems")

    con.close()


def main():
    for population in ["train", "heldout"]:
        print(f"\n=== Profiling {population} ===")
        profile_population(population)
    print("\nDone. Profiles written under data/profile/<population>/.")


if __name__ == "__main__":
    main()
