"""
Builds a `valuesets` reference table in each duckdb file from that database's
own concept_bank.csv profile (table_name, code, code_system, display) -- the
thing gold SQL's lookup CTEs (`WITH resolved AS (SELECT code, code_system
FROM valuesets WHERE table_name = '...' AND display ILIKE '%{display}%')`)
resolve against at execution time, so the model never needs to memorize a
literal code, only produce a plausible search phrase.

`lookup_ambiguous` (computed via self-join, not assumed): does searching by
THIS row's own full display text (ILIKE containment) match more than one row
in the same table? Concepts flagged True must be excluded from gold-SQL
generation rather than force-resolved with an arbitrary LIMIT 1 -- that would
reintroduce exactly the non-determinism class already found and fixed twice
in this project's history (see METHODOLOGY_LOG.md).
"""
import duckdb

TARGETS = [
    ("C:/dev/fhirsql-phase2/data/train.duckdb", "C:/dev/fhirsql-phase2/data/profile/train/concept_bank.csv"),
    ("C:/dev/fhirsql-phase2/data/heldout.duckdb", "C:/dev/fhirsql-phase2/data/profile/heldout/concept_bank.csv"),
]


def build(db_path, csv_path):
    con = duckdb.connect(db_path)
    con.execute(f"""
        CREATE OR REPLACE TABLE valuesets AS
        SELECT table_name, code, code_system, display, CAST(NULL AS BOOLEAN) AS lookup_ambiguous
        FROM read_csv_auto('{csv_path}')
    """)
    con.execute("""
        UPDATE valuesets AS v
        SET lookup_ambiguous = (
            SELECT COUNT(*) > 1
            FROM valuesets AS v2
            WHERE v2.table_name = v.table_name
              AND v2.display ILIKE '%' || v.display || '%'
        )
    """)
    n_total = con.execute("SELECT COUNT(*) FROM valuesets").fetchone()[0]
    n_ambig = con.execute("SELECT COUNT(*) FROM valuesets WHERE lookup_ambiguous").fetchone()[0]
    print(f"{db_path}: {n_ambig}/{n_total} ambiguous ({100*n_ambig/n_total:.1f}%)")
    con.close()


if __name__ == "__main__":
    for db_path, csv_path in TARGETS:
        build(db_path, csv_path)
