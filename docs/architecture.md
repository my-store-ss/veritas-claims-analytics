# Solution Architecture

## 1. Overview

The prototype uses a **batch/event-compatible architecture**: JSON files are discovered from a local `sample-data/` folder that simulates a GCS landing bucket. The same processing contract can be attached to object-finalize events or a scheduler in production.

```text
Clinics
   |
   v
GCS landing bucket (clinic_id/date)
   |
   v
Ingestion / validation
   |---- malformed file ----> Error log / DLQ
   v
Standardisation worker pool
   |  test names | numeric parsing | units
   |  demographics | medicines
   v
Validation + analytics
   |---- flagged records ----> Flag queue
   v
SQLite prototype / BigQuery or PostgreSQL in production
   |
   +---- Streamlit operational dashboard
   |
   +---- audit/raw-document store
```

## 2. Processing flow

1. **Ingestion:** discover JSON files, calculate a SHA-256 file hash, parse JSON and validate the expected top-level structure.
2. **Schema-on-read:** accept clinic-specific JSON shapes and locate `responseDetails`, `basic_info`, `report_details`, and `discharge_summary` structures without requiring a new Python schema for every clinic.
3. **Configuration-driven standardisation:** test aliases, fuzzy matching threshold, units, reference ranges and medicine mappings live under `/config`. A new clinic/test variant is therefore a config change rather than a code change.
4. **Validation:** numeric results are compared with source/configured reference ranges. Extreme values are separately classified as `Outlier`; normal boundary violations are `Above Range` or `Below Range`; non-numeric/multi-value values become `Invalid`.
5. **Storage:** the prototype uses SQLite because it is zero-setup and deterministic for a take-home. The provided ideal-schema column list is represented in `standardized_records`. `raw_documents` preserves the source JSON for auditability.
6. **Idempotency/deduplication:** record IDs are content/business fingerprints, so re-running the same files does not insert duplicates. Identical business records submitted from another file/system can also collapse to the same ID.
7. **Operations:** Streamlit exposes run metrics, flagged records, clinic-level quality metrics and a raw-vs-standardized record inspector.
8. **Error handling:** malformed files are recorded in `raw_documents` with `status=failed` and an error message; they do not stop processing of other files.

## 3. Scale and production evolution

At 200k files/day, average volume is ~2.3 files/sec; the design should be sized for the stated 400k/day burst. In production, GCS notifications can feed Pub/Sub, with Cloud Run Jobs/Dataflow workers consuming messages horizontally. BigQuery is a natural analytical target; PostgreSQL is suitable where transactional access is preferred.

The 15-minute p95 SLA is handled by parallel workers, small per-file transactions, idempotent writes and monitoring of queue lag. A dead-letter topic/bucket supports retries after transient failures and manual replay for persistent data errors.

## 4. Trade-offs

- **SQLite vs BigQuery:** SQLite minimizes setup for the assignment; BigQuery provides managed scale and analytics in production.
- **Batch vs streaming:** batch is simpler for the supplied five files; the ingestion contract remains event-compatible.
- **Schema-on-read vs schema-on-write:** schema-on-read absorbs clinic variation; canonical schema-on-write protects downstream analytics.
- **Fuzzy matching:** improves coverage for typos such as `aemoglobin`, but unmatched names remain visible and confidence is stored. Production should add a human-reviewed alias workflow.
- **Reference ranges:** the prototype uses ranges supplied by the sample data plus a small configuration fallback. Production ranges must be clinically governed and versioned by test, unit, population and effective date.

## 5. Security and governance

Patient identifiers are treated as sensitive. The prototype preserves the supplied redacted values only. Production should use IAM, encryption, secret management, tokenisation/masking, retention policies and access-controlled audit logs. Every standardized row carries document/trace/correlation metadata and ingestion time.
