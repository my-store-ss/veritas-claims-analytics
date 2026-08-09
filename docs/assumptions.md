# Assumptions

## Business assumptions

1. JSON files arrive in a GCS bucket organised by clinic ID and date, as requested by the assignment.
2. A file can contain multiple response records and classifier types.
3. Duplicate detection is based on stable business content rather than filename alone, because the same report may arrive through different systems.
4. Operational users need a simple dashboard rather than a production-grade workflow application for this prototype.

## Technical assumptions

1. SQLite is used for the working prototype because it requires no external service. The production target is BigQuery or PostgreSQL.
2. The local `sample-data/` folder simulates GCS. A production adapter would consume GCS object events or a scheduler.
3. Python is used for ingestion, transformation and validation; Streamlit provides the lightweight UI.
4. Configuration is stored as JSON so a new clinic/test variant can be added without changing transformation code.
5. Record IDs are content/business fingerprints to make reprocessing idempotent.
6. Structured logging/metrics are represented by pipeline run and error tables in the prototype. Production should export them to a monitoring/logging platform.

## Data assumptions

1. The five supplied JSON files are the representative input set and are copied unchanged into `sample-data/`.
2. Some source files contain header-like rows or composite text values. Header rows are skipped; multi-value result strings are retained as text and classified `Invalid` rather than silently selecting one number.
3. Date normalization supports the formats observed in the samples, including `DD-MM-YYYY`, `DD/MM/YYYY`, and `DD/Mon/YYYY`.
4. Age strings such as `33Y11M265D` are supported and converted to decimal years; redacted/unknown ages remain text.
5. Reference ranges supplied inside a report take precedence. The fallback range configuration is based on ranges observed in the supplied sample data.
6. Medicine mappings are demonstration mappings for the prototype. They are not a substitute for a production clinical formulary and must be governed/validated before use in a real healthcare system.
7. The provided ideal schema is row-oriented. Because FR-2.2 also describes a five-column-per-test representation, the prototype stores the provided canonical row schema in SQLite and provides `output/canonical_wide.csv` as a derived five-column-per-test export.

## Scope exclusions

1. No real GCS account or credentials are required.
2. No production authentication/authorization is implemented in Streamlit.
3. No external clinical terminology service, drug database, or LLM is required.
4. No production orchestration, autoscaling infrastructure or managed monitoring deployment is created; the architecture document explains the production path.
5. No clinical decision support is performed. The pipeline only standardizes and flags data against configured/sample ranges.
