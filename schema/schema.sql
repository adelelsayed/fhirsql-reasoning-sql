-- FHIR-SQL fine-tuning study: frozen core clinical schema.
--
-- This is the benchmark-facing schema shown to models in every prompt (benchmark
-- authoring, SFT prompt format, RL reward execution). It is a deliberately curated
-- subset of the full flattened data -- see METHODOLOGY_LOG.md for the two-layer
-- rationale (full fidelity in the database, curated scope in what models see) and
-- the token-cost/scope reasoning.
--
-- Generated from the actual column types DuckDB inferred when loading
-- data/train.duckdb, not hand-assumed -- see scripts/flatten_to_duckdb.py for
-- the extraction logic that produces this shape.
--
-- Version stamp:
--   Date frozen:        2026-08-02
--   Synthea build:      v3.4.0-18-ga07a65555 (git-describe string embedded in
--                        generated Patient resources; downloaded from the
--                        GitHub v4.0.0 release page -- see methodology log)
--   Train population:   18,999 patients (target was ~15,000; see log for
--                        per-batch seed/state/age-bracket design)
--   Held-out population: 6,383 patients (target was ~5,000)
--   Populations verified disjoint: 0 patient_id overlap between train and held-out
--
-- Every number produced downstream (benchmark accuracy, cost tables, etc.) is
-- relative to this artifact. Do not modify this file without a note on what
-- changed and why.
--
-- Provider attribution: Synthea generates exactly one participant per encounter,
-- typed "primary performer" only -- it does not distinguish admitting/attending/
-- consulting roles, so those remain unanswerable regardless of schema design.
-- Procedure.performer is never populated by this Synthea version (0/29,947 in a
-- full batch) -- procedure-level provider attribution is not available at all.
--
-- Naming convention: columns are named to match FHIR element names directly,
-- so a model's clinical-language understanding maps onto the schema with as
-- little translation as possible:
--   - Primary key: `id` (matches every FHIR resource's own `id` element).
--   - Foreign keys: `patient_id`, `encounter_id` (SQL join-key convention;
--     not itself a literal FHIR field name, since FHIR expresses this via
--     subject/patient/encounter *reference* elements, but resolving those
--     references to a flat join key needs a name, and `<type>_id` is the
--     clearest SQL-side compromise).
--   - Primary coding triple on each table: `code`, `system`, `display`
--     (matches FHIR Coding.code/.system/.display exactly).
--   - Where a resource's own field name differs from the generic "code"
--     (Encounter.type, Encounter.class, Immunization.vaccineCode,
--     CarePlan.category), the coding triple is prefixed with that field name
--     instead: `type_code/type_system/type_display`, `class_code`,
--     `vaccineCode/vaccineCode_system/vaccineCode_display`,
--     `category_code/category_system/category_display`.
--   - Status/descriptive fields: exact camelCase FHIR element names
--     (clinicalStatus, verificationStatus, intent, criticality).
--   - Dates: exact FHIR element names (birthDate, deceasedDateTime,
--     onsetDateTime, abatementDateTime, recordedDate, effectiveDateTime,
--     authoredOn, performedDateTime, occurrenceDateTime); Period-typed
--     start/end kept as `period_start`/`period_end` (Period.start/.end).
--   - value[x]: `valueQuantity`, `unit` (Quantity.unit), `valueCodeableConcept`
--     (+ `valueCodeableConcept_system`), `valueString`.
--   - Provider-reference columns match the FHIR field they were extracted
--     from: `requester_npi`/`requester_name` on medication_request (from
--     MedicationRequest.requester), `participant_npi`/`participant_name` on
--     encounter (from Encounter.participant).
--   - `race`/`ethnicity` on patient (US-Core extensions -- see
--     scripts/flatten_to_duckdb.py's us_core_ext_text macro).
--   - `imaging_study` (ImagingStudy resource) makes radiology-volume questions
--     answerable (department-level radiology questions remain unanswerable --
--     no department/service-line concept exists anywhere in Synthea's FHIR
--     output).
--
-- Indexes: secondary (ART) indexes are added directly to train.duckdb and
-- heldout.duckdb (not a change to this file -- no column/table/logical change,
-- only a physical one) on the coding-triple columns (condition.code,
-- observation.code, medication_request.code, encounter.class_code,
-- encounter.type_code, procedure.code, immunization.vaccineCode, allergy.code,
-- careplan.category_code, diagnostic_report.code, imaging_study.procedureCode,
-- imaging_study.modality), to support the RL execution-efficiency reward term.
-- patient_id/encounter_id deliberately NOT indexed -- DuckDB's ART index isn't
-- used by the optimizer to accelerate joins, only point/highly-selective
-- (<0.1% of rows) filters. See METHODOLOGY_LOG.md for the full verification
-- history of this schema and its indexes.

CREATE TABLE patient (
    id                    VARCHAR PRIMARY KEY,
    gender                VARCHAR,
    birthDate             DATE,
    deceasedDateTime      TIMESTAMP,
    maritalStatus         VARCHAR,
    state                 VARCHAR,     -- address[0].state
    city                  VARCHAR,     -- address[0].city
    postalCode            VARCHAR,     -- address[0].postalCode
    race                  VARCHAR,     -- US-Core race extension, ombCategory text
    ethnicity             VARCHAR      -- US-Core ethnicity extension, ombCategory text
);

CREATE TABLE condition (
    id                    VARCHAR PRIMARY KEY,
    patient_id            VARCHAR,     -- join key -> patient.id
    encounter_id          VARCHAR,     -- join key -> encounter.id
    code                  VARCHAR,
    system                VARCHAR,     -- kept alongside code deliberately: code-system confusion (SNOMED vs ICD-10 vs LOINC) is a failure mode to observe
    display               VARCHAR,
    clinicalStatus        VARCHAR,
    verificationStatus    VARCHAR,
    onsetDateTime         TIMESTAMP,
    abatementDateTime     TIMESTAMP,
    recordedDate          TIMESTAMP
);

CREATE TABLE observation (
    id                    VARCHAR PRIMARY KEY,
    patient_id            VARCHAR,     -- join key -> patient.id
    encounter_id          VARCHAR,     -- join key -> encounter.id
    code                  VARCHAR,
    system                VARCHAR,
    display               VARCHAR,
    category              VARCHAR,
    status                VARCHAR,
    effectiveDateTime     TIMESTAMP,
    valueQuantity         DOUBLE,      -- value[x] flattened per plan design rule
    unit                  VARCHAR,
    valueCodeableConcept  VARCHAR,
    valueCodeableConcept_system VARCHAR,  -- code-system pairing for the value itself, when value[x] is coded
    valueString           VARCHAR
);

CREATE TABLE medication_request (
    id                    VARCHAR PRIMARY KEY,
    patient_id            VARCHAR,     -- join key -> patient.id
    encounter_id          VARCHAR,     -- join key -> encounter.id
    code                  VARCHAR,
    system                VARCHAR,
    display               VARCHAR,
    status                VARCHAR,
    intent                VARCHAR,
    authoredOn            TIMESTAMP,
    requester_npi         VARCHAR,     -- prescribing physician's NPI (from MedicationRequest.requester)
    requester_name        VARCHAR
);

CREATE TABLE encounter (
    id                    VARCHAR PRIMARY KEY,
    patient_id            VARCHAR,     -- join key -> patient.id
    class_code            VARCHAR,     -- Encounter.class.code (AMB/EMER/IMP/HH/VR)
    type_code             VARCHAR,     -- Encounter.type[0].coding[0]
    type_system           VARCHAR,
    type_display          VARCHAR,
    status                VARCHAR,
    period_start          TIMESTAMP,
    period_end            TIMESTAMP,
    reasonCode            VARCHAR,
    participant_npi       VARCHAR,     -- primary-performer physician's NPI (Synthea models only one role per encounter, not admitting/attending/etc separately)
    participant_name      VARCHAR
);

CREATE TABLE procedure (
    id                    VARCHAR PRIMARY KEY,
    patient_id            VARCHAR,     -- join key -> patient.id
    encounter_id          VARCHAR,     -- join key -> encounter.id
    code                  VARCHAR,
    system                VARCHAR,
    display               VARCHAR,
    status                VARCHAR,
    performedDateTime     TIMESTAMP
    -- Note: Procedure.performer (physician who performed it) is never populated
    -- by this Synthea version (confirmed 0/29,947) -- not available at all.
);

CREATE TABLE immunization (
    id                    VARCHAR PRIMARY KEY,
    patient_id            VARCHAR,     -- join key -> patient.id
    encounter_id          VARCHAR,     -- join key -> encounter.id
    vaccineCode           VARCHAR,
    vaccineCode_system    VARCHAR,
    vaccineCode_display   VARCHAR,
    status                VARCHAR,
    occurrenceDateTime    TIMESTAMP
);

CREATE TABLE allergy (
    id                    VARCHAR PRIMARY KEY,
    patient_id            VARCHAR,     -- join key -> patient.id
    code                  VARCHAR,
    system                VARCHAR,
    display               VARCHAR,
    clinicalStatus        VARCHAR,
    verificationStatus    VARCHAR,
    category              VARCHAR,
    criticality           VARCHAR,
    recordedDate          TIMESTAMP
);

CREATE TABLE careplan (
    id                    VARCHAR PRIMARY KEY,
    patient_id            VARCHAR,     -- join key -> patient.id
    encounter_id          VARCHAR,     -- join key -> encounter.id
    category_code         VARCHAR,     -- CarePlan.category[0].coding[0]
    category_system       VARCHAR,
    category_display      VARCHAR,
    status                VARCHAR,
    period_start          TIMESTAMP,
    period_end            TIMESTAMP
);

CREATE TABLE diagnostic_report (
    id                    VARCHAR PRIMARY KEY,
    patient_id            VARCHAR,     -- join key -> patient.id
    encounter_id          VARCHAR,     -- join key -> encounter.id
    code                  VARCHAR,
    system                VARCHAR,
    display               VARCHAR,
    category              VARCHAR,
    status                VARCHAR,
    effectiveDateTime     TIMESTAMP
);

CREATE TABLE imaging_study (
    id                    VARCHAR PRIMARY KEY,
    patient_id            VARCHAR,     -- join key -> patient.id
    encounter_id          VARCHAR,     -- join key -> encounter.id
    status                VARCHAR,
    started               TIMESTAMP,
    numberOfSeries        INTEGER,
    numberOfInstances     INTEGER,
    procedureCode         VARCHAR,     -- the imaging procedure performed, e.g. "Plain X-ray of ankle region"
    procedureCode_system  VARCHAR,
    procedureCode_display VARCHAR,
    modality               VARCHAR,    -- DICOM modality code, e.g. "DX" = Digital Radiography (from series[0])
    modality_system        VARCHAR,
    modality_display       VARCHAR,
    bodySite               VARCHAR,    -- from series[0]
    bodySite_display       VARCHAR
);
