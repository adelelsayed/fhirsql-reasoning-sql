"""
Flattens Synthea FHIR NDJSON output into DuckDB.

Two-layer design (see METHODOLOGY_LOG.md, "Scope revision" entry):
  - CORE_TABLES: 10 target clinical tables, hand-flattened per a fixed set of
    design rules (value[x] -> typed columns, patient_id join key everywhere, keep both
    code + code_system, keep clinical_status/verification_status, keep date columns).
    This is what gets shown to models in prompts -- kept lean deliberately.
  - EXTRA_TABLES: every other FHIR resource type Synthea exported, auto-flattened via
    DuckDB's read_json_auto. Full fidelity, nothing discarded, but not part of the
    benchmark-facing schema.

Produces one DuckDB file per population: data/train.duckdb, data/heldout.duckdb, plus a
Parquet export of every table under data/parquet/<population>/<table>.parquet for the
Colab/Drive workflow.

Must be run AFTER scripts/fix_ndjson_encoding.py (raw Synthea output on this machine had
134 files with invalid UTF-8 from a JVM default-charset bug -- see methodology log).
"""
import glob
import os
import duckdb

SYNTHEA_ROOT = "C:/dev/fhirsql/synthea/output"
DATA_ROOT = "C:/dev/fhirsql/data"

POPULATIONS = {
    "train": [
        "general_ma", "general_ca", "general_tx",
        "pediatric_oh", "pediatric_fl",
        "geriatric_pa", "geriatric_il",
        "oncology_ny",
    ],
    "heldout": [
        "general_wa", "general_ga",
        "pediatric_nc",
        "geriatric_az",
        "oncology_co",
    ],
}

REF_ID_MACRO = "CREATE OR REPLACE MACRO ref_id(ref) AS regexp_extract(ref, '[^/]+$');"
# Practitioner references from Encounter.participant/MedicationRequest.requester are FHIR
# *conditional* references by NPI identifier (e.g.
# "Practitioner?identifier=http://hl7.org/fhir/sid/us-npi|9999983197"), NOT a direct
# "Practitioner/<id>" reference -- ref_id() (splits on last "/") would mis-extract this,
# so a separate macro splits on "|" instead to get the NPI number.
PRACTITIONER_NPI_MACRO = "CREATE OR REPLACE MACRO practitioner_npi(ref) AS split_part(ref, '|', 2);"
# US-Core race/ethnicity extensions are nested extension arrays (extension[url=...].extension[url=text].valueString),
# not a flat field -- filters the outer array by URL pattern, then the inner array for the "text" sub-extension.
# Tested standalone against real Patient JSON before use (see METHODOLOGY_LOG.md) -- list_filter + lambda on a
# JSON array cast via from_json, not DuckDB's more limited built-in JSONPath filter syntax.
US_CORE_EXT_TEXT_MACRO = """
CREATE OR REPLACE MACRO us_core_ext_text(json, ext_url_pattern) AS (
    json_extract_string(
        list_extract(
            list_filter(
                from_json(
                    json_extract(
                        list_extract(
                            list_filter(
                                from_json(json_extract(json, '$.extension'), '["JSON"]'),
                                x -> json_extract_string(x, '$.url') LIKE ext_url_pattern
                            ), 1
                        ),
                    '$.extension'),
                '["JSON"]'),
                y -> json_extract_string(y, '$.url') = 'text'
            ), 1
        ),
    '$.valueString')
);
"""

# ---------------------------------------------------------------------------
# CORE_TABLES: (resource_type_filename, select_sql_using "json" column)
# ---------------------------------------------------------------------------
CORE_TABLES = {
    "patient": (
        "Patient",
        """
        json_extract_string(json, '$.id')                                   AS id,
        json_extract_string(json, '$.gender')                                AS gender,
        TRY_CAST(json_extract_string(json, '$.birthDate') AS DATE)           AS birthDate,
        TRY_CAST(json_extract_string(json, '$.deceasedDateTime') AS TIMESTAMP) AS deceasedDateTime,
        json_extract_string(json, '$.maritalStatus.coding[0].code')         AS maritalStatus,
        json_extract_string(json, '$.address[0].state')                     AS state,
        json_extract_string(json, '$.address[0].city')                      AS city,
        json_extract_string(json, '$.address[0].postalCode')                AS postalCode,
        us_core_ext_text(json, '%us-core-race%')                            AS race,
        us_core_ext_text(json, '%us-core-ethnicity%')                       AS ethnicity
        """,
    ),
    "condition": (
        "Condition",
        """
        json_extract_string(json, '$.id')                                    AS id,
        ref_id(json_extract_string(json, '$.subject.reference'))             AS patient_id,
        ref_id(json_extract_string(json, '$.encounter.reference'))           AS encounter_id,
        json_extract_string(json, '$.code.coding[0].code')                   AS code,
        json_extract_string(json, '$.code.coding[0].system')                 AS system,
        json_extract_string(json, '$.code.coding[0].display')                AS display,
        json_extract_string(json, '$.clinicalStatus.coding[0].code')         AS clinicalStatus,
        json_extract_string(json, '$.verificationStatus.coding[0].code')     AS verificationStatus,
        TRY_CAST(json_extract_string(json, '$.onsetDateTime') AS TIMESTAMP)      AS onsetDateTime,
        TRY_CAST(json_extract_string(json, '$.abatementDateTime') AS TIMESTAMP)  AS abatementDateTime,
        TRY_CAST(json_extract_string(json, '$.recordedDate') AS TIMESTAMP)       AS recordedDate
        """,
    ),
    "observation": (
        "Observation",
        """
        json_extract_string(json, '$.id')                                    AS id,
        ref_id(json_extract_string(json, '$.subject.reference'))             AS patient_id,
        ref_id(json_extract_string(json, '$.encounter.reference'))           AS encounter_id,
        json_extract_string(json, '$.code.coding[0].code')                   AS code,
        json_extract_string(json, '$.code.coding[0].system')                 AS system,
        json_extract_string(json, '$.code.coding[0].display')                AS display,
        json_extract_string(json, '$.category[0].coding[0].code')            AS category,
        json_extract_string(json, '$.status')                                AS status,
        TRY_CAST(json_extract_string(json, '$.effectiveDateTime') AS TIMESTAMP)  AS effectiveDateTime,
        TRY_CAST(json_extract_string(json, '$.valueQuantity.value') AS DOUBLE)   AS valueQuantity,
        json_extract_string(json, '$.valueQuantity.unit')                    AS unit,
        COALESCE(
            json_extract_string(json, '$.valueCodeableConcept.coding[0].code'),
            json_extract_string(json, '$.valueCode')
        )                                                                     AS valueCodeableConcept,
        json_extract_string(json, '$.valueCodeableConcept.coding[0].system') AS valueCodeableConcept_system,
        json_extract_string(json, '$.valueString')                           AS valueString
        """,
    ),
    "medication_request": (
        "MedicationRequest",
        """
        json_extract_string(json, '$.id')                                    AS id,
        ref_id(json_extract_string(json, '$.subject.reference'))             AS patient_id,
        ref_id(json_extract_string(json, '$.encounter.reference'))           AS encounter_id,
        json_extract_string(json, '$.medicationCodeableConcept.coding[0].code')   AS code,
        json_extract_string(json, '$.medicationCodeableConcept.coding[0].system') AS system,
        json_extract_string(json, '$.medicationCodeableConcept.coding[0].display')AS display,
        json_extract_string(json, '$.status')                                AS status,
        json_extract_string(json, '$.intent')                                AS intent,
        TRY_CAST(json_extract_string(json, '$.authoredOn') AS TIMESTAMP)     AS authoredOn,
        practitioner_npi(json_extract_string(json, '$.requester.reference')) AS requester_npi,
        json_extract_string(json, '$.requester.display')                    AS requester_name
        """,
    ),
    "encounter": (
        "Encounter",
        """
        json_extract_string(json, '$.id')                                    AS id,
        ref_id(json_extract_string(json, '$.subject.reference'))             AS patient_id,
        json_extract_string(json, '$.class.code')                            AS class_code,
        json_extract_string(json, '$.type[0].coding[0].code')                AS type_code,
        json_extract_string(json, '$.type[0].coding[0].system')              AS type_system,
        json_extract_string(json, '$.type[0].coding[0].display')             AS type_display,
        json_extract_string(json, '$.status')                                AS status,
        TRY_CAST(json_extract_string(json, '$.period.start') AS TIMESTAMP)   AS period_start,
        TRY_CAST(json_extract_string(json, '$.period.end') AS TIMESTAMP)     AS period_end,
        json_extract_string(json, '$.reasonCode[0].coding[0].code')          AS reasonCode,
        practitioner_npi(json_extract_string(json, '$.participant[0].individual.reference')) AS participant_npi,
        json_extract_string(json, '$.participant[0].individual.display')     AS participant_name
        """,
    ),
    "procedure": (
        "Procedure",
        """
        json_extract_string(json, '$.id')                                    AS id,
        ref_id(json_extract_string(json, '$.subject.reference'))             AS patient_id,
        ref_id(json_extract_string(json, '$.encounter.reference'))           AS encounter_id,
        json_extract_string(json, '$.code.coding[0].code')                   AS code,
        json_extract_string(json, '$.code.coding[0].system')                 AS system,
        json_extract_string(json, '$.code.coding[0].display')                AS display,
        json_extract_string(json, '$.status')                                AS status,
        TRY_CAST(
            COALESCE(
                json_extract_string(json, '$.performedDateTime'),
                json_extract_string(json, '$.performedPeriod.start')
            ) AS TIMESTAMP
        )                                                                    AS performedDateTime
        """,
    ),
    "immunization": (
        "Immunization",
        """
        json_extract_string(json, '$.id')                                    AS id,
        ref_id(json_extract_string(json, '$.patient.reference'))             AS patient_id,
        ref_id(json_extract_string(json, '$.encounter.reference'))           AS encounter_id,
        json_extract_string(json, '$.vaccineCode.coding[0].code')            AS vaccineCode,
        json_extract_string(json, '$.vaccineCode.coding[0].system')          AS vaccineCode_system,
        json_extract_string(json, '$.vaccineCode.coding[0].display')         AS vaccineCode_display,
        json_extract_string(json, '$.status')                                AS status,
        TRY_CAST(json_extract_string(json, '$.occurrenceDateTime') AS TIMESTAMP) AS occurrenceDateTime
        """,
    ),
    "allergy": (
        "AllergyIntolerance",
        """
        json_extract_string(json, '$.id')                                    AS id,
        ref_id(json_extract_string(json, '$.patient.reference'))             AS patient_id,
        json_extract_string(json, '$.code.coding[0].code')                   AS code,
        json_extract_string(json, '$.code.coding[0].system')                 AS system,
        json_extract_string(json, '$.code.coding[0].display')                AS display,
        json_extract_string(json, '$.clinicalStatus.coding[0].code')         AS clinicalStatus,
        json_extract_string(json, '$.verificationStatus.coding[0].code')     AS verificationStatus,
        json_extract_string(json, '$.category[0]')                           AS category,
        json_extract_string(json, '$.criticality')                          AS criticality,
        TRY_CAST(json_extract_string(json, '$.recordedDate') AS TIMESTAMP)   AS recordedDate
        """,
    ),
    "careplan": (
        "CarePlan",
        """
        json_extract_string(json, '$.id')                                    AS id,
        ref_id(json_extract_string(json, '$.subject.reference'))             AS patient_id,
        ref_id(json_extract_string(json, '$.encounter.reference'))           AS encounter_id,
        json_extract_string(json, '$.category[0].coding[0].code')            AS category_code,
        json_extract_string(json, '$.category[0].coding[0].system')          AS category_system,
        json_extract_string(json, '$.category[0].coding[0].display')         AS category_display,
        json_extract_string(json, '$.status')                                AS status,
        TRY_CAST(json_extract_string(json, '$.period.start') AS TIMESTAMP)   AS period_start,
        TRY_CAST(json_extract_string(json, '$.period.end') AS TIMESTAMP)     AS period_end
        """,
    ),
    "diagnostic_report": (
        "DiagnosticReport",
        """
        json_extract_string(json, '$.id')                                    AS id,
        ref_id(json_extract_string(json, '$.subject.reference'))             AS patient_id,
        ref_id(json_extract_string(json, '$.encounter.reference'))           AS encounter_id,
        json_extract_string(json, '$.code.coding[0].code')                   AS code,
        json_extract_string(json, '$.code.coding[0].system')                 AS system,
        json_extract_string(json, '$.code.coding[0].display')                AS display,
        json_extract_string(json, '$.category[0].coding[0].code')            AS category,
        json_extract_string(json, '$.status')                                AS status,
        TRY_CAST(json_extract_string(json, '$.effectiveDateTime') AS TIMESTAMP)  AS effectiveDateTime
        """,
    ),
    "imaging_study": (
        "ImagingStudy",
        """
        json_extract_string(json, '$.id')                                    AS id,
        ref_id(json_extract_string(json, '$.subject.reference'))             AS patient_id,
        ref_id(json_extract_string(json, '$.encounter.reference'))           AS encounter_id,
        json_extract_string(json, '$.status')                                AS status,
        TRY_CAST(json_extract_string(json, '$.started') AS TIMESTAMP)        AS started,
        TRY_CAST(json_extract_string(json, '$.numberOfSeries') AS INTEGER)   AS numberOfSeries,
        TRY_CAST(json_extract_string(json, '$.numberOfInstances') AS INTEGER) AS numberOfInstances,
        json_extract_string(json, '$.procedureCode[0].coding[0].code')       AS procedureCode,
        json_extract_string(json, '$.procedureCode[0].coding[0].system')     AS procedureCode_system,
        json_extract_string(json, '$.procedureCode[0].coding[0].display')    AS procedureCode_display,
        json_extract_string(json, '$.series[0].modality.code')               AS modality,
        json_extract_string(json, '$.series[0].modality.system')             AS modality_system,
        json_extract_string(json, '$.series[0].modality.display')            AS modality_display,
        json_extract_string(json, '$.series[0].bodySite.code')               AS bodySite,
        json_extract_string(json, '$.series[0].bodySite.display')            AS bodySite_display
        """,
    ),
}

# Extra resource types: full fidelity via auto-inference, not part of the benchmark-facing schema.
# Name collisions (e.g. Practitioner vs PractitionerRole) require exact-name glob patterns, not prefix globs.
EXTRA_RESOURCE_TYPES = [
    "CareTeam", "Claim", "Device", "DocumentReference", "ExplanationOfBenefit",
    "ImagingStudy", "Location", "Medication", "MedicationAdministration",
    "Organization", "Practitioner", "PractitionerRole", "Provenance", "SupplyDelivery",
]


def batch_dirs(population):
    return [f"{SYNTHEA_ROOT}/{population}/{b}/fhir" for b in POPULATIONS[population]]


def globs_for_resource(population, resource):
    """Exact-name glob patterns for a resource, handling both plain (Condition.ndjson)
    and run-id-suffixed (Practitioner.1785675408003.ndjson) filenames without
    accidentally matching a differently-named resource that shares a prefix."""
    patterns = []
    for d in batch_dirs(population):
        plain = f"{d}/{resource}.ndjson"
        if os.path.exists(plain):
            patterns.append(plain)
        patterns.extend(glob.glob(f"{d}/{resource}.[0-9]*.ndjson"))
    return patterns


def table_exists(con, table):
    row = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchone()
    return row[0] > 0


def load_core_table(con, population, table, resource, select_sql):
    if table_exists(con, table):
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  [resume] {table}: already loaded ({n} rows), skipping")
        return
    files = globs_for_resource(population, resource)
    if not files:
        print(f"  [skip] {table}: no files found for resource {resource}")
        return
    file_list_sql = "[" + ", ".join(f"'{f}'" for f in files) + "]"
    con.execute(f"""
        CREATE OR REPLACE TABLE {table} AS
        SELECT {select_sql}
        FROM read_json_objects({file_list_sql}) AS t(json)
    """)
    n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  [core]  {table}: {n} rows")


def load_extra_table(con, population, resource):
    table = f"extra_{resource.lower()}"
    if table_exists(con, table):
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  [resume] {table}: already loaded ({n} rows), skipping")
        return
    files = globs_for_resource(population, resource)
    if not files:
        print(f"  [skip] {table}: no files found")
        return
    file_list_sql = "[" + ", ".join(f"'{f}'" for f in files) + "]"
    con.execute(f"""
        CREATE OR REPLACE TABLE {table} AS
        SELECT * FROM read_json_auto({file_list_sql}, union_by_name=true, ignore_errors=true)
    """)
    n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  [extra] {table}: {n} rows")


def export_parquet(con, population, table):
    out_dir = f"{DATA_ROOT}/parquet/{population}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/{table}.parquet"
    if os.path.exists(out_path):
        print(f"  [resume] {table}.parquet already exists, skipping")
        return
    con.execute(f"COPY {table} TO '{out_path}' (FORMAT PARQUET)")
    print(f"  [parquet] {table}.parquet written")


def main():
    os.makedirs(DATA_ROOT, exist_ok=True)
    for population in POPULATIONS:
        print(f"\n=== Population: {population} ===")
        db_path = f"{DATA_ROOT}/{population}.duckdb"
        con = duckdb.connect(db_path)
        con.execute(REF_ID_MACRO)
        con.execute(PRACTITIONER_NPI_MACRO)
        con.execute(US_CORE_EXT_TEXT_MACRO)
        # Large tables (Observation, Claim, ExplanationOfBenefit reach millions of rows) hit
        # a temp-directory OOM during Parquet export with default settings on this machine
        # (15.4GB RAM). preserve_insertion_order=false lets DuckDB stream results directly to
        # Parquet instead of buffering for row-order preservation under parallelism -- row
        # order is irrelevant for this data. max_temp_directory_size pinned explicitly rather
        # than left to auto-derive from momentary free disk space, for reproducibility.
        con.execute("SET preserve_insertion_order=false;")
        con.execute("PRAGMA max_temp_directory_size='100GiB';")
        # imaging_study (562MB of raw JSON across 8 files, parsed as untyped JSON
        # columns via read_json_objects) OOM'd at default settings with only ~8.7GB
        # RAM free at the time -- explicit threads=2 + memory_limit=6GB fixed it
        # (verified standalone before applying here). DuckDB's auto-derived
        # memory_limit (~80% of system RAM) doesn't account for what's actually
        # free at runtime, only total installed RAM.
        con.execute("SET threads=2;")
        con.execute("SET memory_limit='6GB';")

        print("-- core tables --")
        for table, (resource, select_sql) in CORE_TABLES.items():
            load_core_table(con, population, table, resource, select_sql)

        print("-- extra tables (full fidelity, not benchmark-facing) --")
        for resource in EXTRA_RESOURCE_TYPES:
            load_extra_table(con, population, resource)

        print("-- exporting parquet --")
        all_tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        for table in all_tables:
            export_parquet(con, population, table)

        con.close()
        print(f"=== {population} done: {db_path} ===")


if __name__ == "__main__":
    main()
