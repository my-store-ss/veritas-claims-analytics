# Veritas Claims Analytics — Medical Data Standardisation

Take-home prototype for the Veritas Claims Analytics engineering assignment.

## What is implemented

The solution processes the five supplied JSON files and provides:

- Local-folder ingestion that simulates a GCS landing bucket
- Malformed JSON handling without stopping other files
- Config-driven test-name normalization with exact and conservative fuzzy matching
- Numeric extraction from mixed text
- Multi-value/contradictory result protection
- Unit normalization and configurable conversion factors
- Age, gender and date normalization
- Configurable medicine brand-to-generic mapping
- Range validation and separate outlier detection
- `Within Range`, `Above Range`, `Below Range`, `Outlier`, `Invalid`
- Content/business-key idempotency and duplicate suppression
- SQLite canonical database based on the supplied ideal schema
- Raw JSON retention for audit/record inspection
- Pipeline run/error metrics
- Streamlit operational UI
- Unit tests
- Five supplied sample JSON files
- Derived five-column-per-test CSV export for the FR-2.2 interpretation

The architecture and assumptions are documented in `/docs`.

## Repository structure

```text
.
├── app.py
├── run.py
├── requirements.txt
├── README.md
├── src/
│   ├── config.py
│   ├── ingestion.py
│   ├── pipeline.py
│   └── standardization.py
├── config/
│   ├── test_name_mapping.json
│   ├── unit_mapping.json
│   ├── medicine_mapping.json
│   └── reference_ranges.json
├── sample-data/
│   └── Sample_JSON_file1.json ... Sample_JSON_file5.json
├── tests/
│   └── test_standardization.py
├── docs/
│   ├── architecture.md
│   ├── architecture.svg
│   └── assumptions.md
├── data/
│   └── claims.db                 # generated locally
└── output/
    └── canonical_wide.csv        # generated example
```

## Setup

Python 3.10+ is recommended.

```bash
python -m venv .venv
```

### Windows

```bash
.venv\Scripts\activate
pip install -r requirements.txt
```

### macOS/Linux

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the pipeline

```bash
python run.py run --input sample-data --db data/claims.db --reset
```

Expected prototype result with the supplied files is approximately:

- 5 files received
- 5 files processed
- 0 malformed files
- 408 unique standardized rows written
- 207 validation-flagged rows

These numbers are a run result for the supplied sample set, not a production capacity claim.

## Run tests

```bash
python -m pytest -q
```

The included test suite covers test-name normalization, numeric parsing, multi-value handling, range parsing, demographics, validation classes and medicine mapping.

## Run the UI

```bash
streamlit run app.py
```

The UI contains:

1. Pipeline run summary
2. Flagged-record queue
3. Clinic-level quality metrics
4. Record inspector with raw JSON and standardized fields

## Produce the FR-2.2 wide export

The assignment describes five columns per test:

`Test_Name`, `Test_Name_Result`, `Test_Name_Range`, `Test_Name_Unit`, `Test_Name_Analytics`.

The supplied ideal schema is row-oriented, so the database follows that schema. A derived wide file is produced with:

```bash
python run.py export-wide --db data/claims.db --out output/canonical_wide.csv
```

## Design decisions

### Configuration over code

Clinic/test variants, units, reference ranges and medicine mappings live in `/config`. Adding a supported alias or unit should not require editing the transformation logic.

### Idempotency

Each standardized record receives a deterministic SHA-256 business fingerprint. Re-running the same input does not create another row. This also supports duplicate suppression when the same business record arrives through another file.

### Validation

The source range is used when available. A small fallback range configuration is provided for sample coverage. Multi-value strings are retained as text and marked `Invalid` instead of silently choosing one component.

### Prototype vs production

The assignment explicitly permits local SQLite and local files for the take-home. In production, the landing layer would use GCS, events could use Pub/Sub, workers could scale on Cloud Run/Dataflow, and the database could be BigQuery/PostgreSQL. Monitoring would be exported to a managed observability platform.

## Requirement coverage

| Requirement | Implementation |
|---|---|
| FR-1.1 | `src/ingestion.py`, local folder simulates GCS |
| FR-1.2 | deterministic business fingerprint + UNIQUE id |
| FR-1.3 | schema-on-read response/classifier handling |
| FR-2.1 | `config/test_name_mapping.json` + fuzzy matching |
| FR-2.2 | canonical DB + `output/canonical_wide.csv` |
| FR-2.3 | `parse_numeric()` and mixed-text handling |
| FR-2.4 | `config/unit_mapping.json` |
| FR-2.5 | age/gender/date normalization |
| FR-2.6 | `config/medicine_mapping.json` |
| FR-3.1 | range parser + validation |
| FR-3.2 | configurable extreme-value factors |
| FR-3.3 | analytics classification |
| FR-3.4 | multi-value/non-numeric invalid flag |
| FR-4.1 | SQLite canonical schema |
| FR-4.2 | `raw_documents` failed status/error message |
| FR-4.3 | raw JSON retention |
| FR-5.1 | Streamlit dashboard |
| FR-5.2 | record inspector |
| FR-5.3 | flagged records queue |
| FR-5.4 | clinic-level metrics |
| NFR-1 | horizontal worker design described in architecture |
| NFR-2 | config-driven onboarding |
| NFR-3 | isolation, DLQ concept and idempotency |
| NFR-4 | lineage fields + raw JSON |
| NFR-5 | run/error metrics and structured record metadata |

## Important prototype assumptions

See [`docs/assumptions.md`](docs/assumptions.md). In particular, the sample-provided reference ranges are used for prototype validation; production clinical ranges require clinical governance and versioning.

## Submission

The assignment requests **one GitHub repository** containing `/src`, `/config`, `/sample-data`, `/docs`, and `README.md`.

Recommended final submission sequence:

1. Create a GitHub repository.
2. Copy this project into the repository.
3. Do **not** commit `.venv/`, secrets or unnecessary generated files.
4. Commit and push the project.
5. Make the repository private or public according to the employer's preference.
6. If private, add the review panel's GitHub account(s) as collaborators.
7. Open the repository in a clean environment and run the setup + test + UI commands above.
8. Send the repository URL using the employer's submission channel.

The assignment states that the deadline is **48 hours from receipt of the document** and asks for a single GitHub repository. See the original assignment pages 6–9 for the deliverables, rubric and submission rules.
