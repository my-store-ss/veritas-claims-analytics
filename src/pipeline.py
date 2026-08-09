
import hashlib
import json
import sqlite3
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List
from .config import load_configs
from .ingestion import ingest_folder
from .standardization import (
    normalize_test_name, normalize_unit, normalize_date, normalize_age,
    normalize_gender, normalize_medicine, parse_numeric, parse_range, classify_result
)

SCHEMA = [
("id","TEXT"),("document_id","TEXT"),("record_type","TEXT"),("file_gcs_path","TEXT"),
("trace_id","TEXT"),("correlation_id","TEXT"),("source_system","TEXT"),("claim_no","TEXT"),
("nt_code","TEXT"),("consumer_client_id","TEXT"),("destination_identifier","TEXT"),
("patient_name","TEXT"),("age","TEXT"),("gender","TEXT"),("uhid","TEXT"),("hospital_name","TEXT"),
("doctor_name","TEXT"),("bill_date","TEXT"),("reports_date","TEXT"),("test_name_canonical","TEXT"),
("test_name_original","TEXT"),("result_value","REAL"),("result_text","TEXT"),("unit_canonical","TEXT"),
("unit_original","TEXT"),("range_low","REAL"),("range_high","REAL"),("range_text","TEXT"),
("test_analytics","TEXT"),("normalization_method","TEXT"),("normalization_confidence","REAL"),
("admission_date","TEXT"),("discharge_date","TEXT"),("diagnosis","TEXT"),("brief_history","TEXT"),
("general_examinations","TEXT"),("recommendations","TEXT"),("hospital_address","TEXT"),("ward","TEXT"),
("post_discharge_advice","TEXT"),("medicine","TEXT"),("dose","TEXT"),("frequency","TEXT"),
("medicine_type","TEXT"),("processed_at","TEXT"),("ingested_at","TEXT"),("basic_info_age","TEXT"),
("basic_info_bill_date","TEXT"),("medicine_injections_investigation","TEXT"),
("discharge_medications_dose","TEXT"),("metadetails","TEXT"),("discharge_medications_frequency","TEXT"),
("discharge_medications_medicine","TEXT"),("lab_or_hospital_name","TEXT"),("report_details_page_no","TEXT"),
("report_details_range","TEXT"),("report_details_result","TEXT"),("report_details_test_analytics","TEXT"),
("report_details_test_name","TEXT"),("report_details_unit","TEXT"),("age_text","TEXT"),
("other_med_inj_investigations","TEXT"),("report_date","TEXT"),("course_during_hospitalisation","TEXT"),
("page_number","TEXT"),("range_text_original","TEXT"),("medication_dose","TEXT"),
("result_text_original","TEXT"),("medication_frequency","TEXT"),("course_during_hospitalization","TEXT"),
("medication_name","TEXT"),("page_no","TEXT"),("test_name","TEXT"),("medication_medicine","TEXT"),
("result","TEXT"),("unit","TEXT"),("age_years","TEXT"),("range","TEXT")
]

def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    cols = ", ".join(f"{name} {typ}" for name, typ in SCHEMA)
    conn.execute(f"CREATE TABLE IF NOT EXISTS standardized_records ({cols}, UNIQUE(id))")
    conn.execute("""CREATE TABLE IF NOT EXISTS raw_documents (
        file_hash TEXT PRIMARY KEY, file_name TEXT, document_id TEXT, trace_id TEXT,
        source_system TEXT, ingested_at TEXT, status TEXT, error_message TEXT, raw_json TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS pipeline_runs (
        run_id TEXT PRIMARY KEY, started_at TEXT, completed_at TEXT,
        files_received INTEGER, files_processed INTEGER, files_failed INTEGER, records_written INTEGER,
        records_flagged INTEGER)""")
    conn.commit()
    return conn

def meta_dict(meta):
    return {x.get("key"): x.get("value") for x in (meta or [])}

def base_record(payload, response, file_path, file_hash, ingested_at):
    data = payload.get("data", {})
    meta = meta_dict(data.get("metaDetails"))
    return {
        "document_id": data.get("documentId") or hashlib.sha256((file_hash + response["classifier"]).encode()).hexdigest()[:24],
        "trace_id": payload.get("traceId"),
        "correlation_id": data.get("correlationId"),
        "source_system": meta.get("source_system"),
        "claim_no": meta.get("claim_no"),
        "nt_code": meta.get("nt_code"),
        "consumer_client_id": meta.get("ConsumerClientId"),
        "destination_identifier": meta.get("DestinationIdentifier"),
        "file_gcs_path": str(file_path),
        "ingested_at": ingested_at,
        "record_type": response.get("classifier"),
        "metadetails": json.dumps(meta, sort_keys=True),
    }

def make_id(base, payload):
    # Content-addressed ID makes reprocessing idempotent.
    canonical = json.dumps([base, payload], sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()

def transform_response(payload, response, file_path, file_hash, configs, ingested_at):
    base = base_record(payload, response, file_path, file_hash, ingested_at)
    data = response.get("data", {})
    rows = []
    if response.get("classifier") == "lab_report":
        info = data.get("basic_info", {})
        age_years, age_text = normalize_age(info.get("age"))
        gender = normalize_gender(info.get("gender"))
        for item in data.get("report_details", []):
            # Skip obvious header rows embedded in sample JSON.
            if str(item.get("test_name","")).strip().lower() == "test_name":
                continue
            canonical, method, confidence = normalize_test_name(item.get("test_name",""), configs["test_mapping"])
            raw_value = item.get("result")
            result_value, result_text, parse_status = parse_numeric(raw_value)
            low, high, range_text = parse_range(item.get("range"))
            unit_canonical, result_value, unit_original = normalize_unit(item.get("unit"), result_value, configs["units"])
            ref = configs["ranges"]["reference_ranges"].get(canonical)
            if ref:
                if low is None and high is None:
                    low, high = ref.get("low"), ref.get("high")
                    if not range_text:
                        range_text = ""
                if not unit_canonical and ref.get("unit"):
                    unit_canonical = ref["unit"]
            # If the source range is usable, prefer it over generic fallback.
            analytics = classify_result(
                result_value,
                low, high,
                expected_numeric=(parse_status != "empty" or bool(range_text)),
                outlier_low=configs["ranges"]["outlier_rules"]["low_factor"],
                outlier_high=configs["ranges"]["outlier_rules"]["high_factor"],
            )
            if parse_status == "multi_value":
                analytics = "Invalid"
            row = dict(base)
            row.update({
                "record_type":"lab_result",
                "patient_name":info.get("patient_name"), "age":info.get("age"), "gender":gender,
                "uhid":info.get("uhid"), "hospital_name":info.get("lab_or_hospital_name"),
                "bill_date":normalize_date(info.get("bill_date")), "reports_date":normalize_date(info.get("reports_date")),
                "test_name_canonical":canonical, "test_name_original":item.get("test_name"),
                "result_value":result_value, "result_text":result_text, "unit_canonical":unit_canonical,
                "unit_original":unit_original, "range_low":low, "range_high":high, "range_text":range_text,
                "test_analytics":analytics, "normalization_method":method,
                "normalization_confidence":confidence, "basic_info_age":info.get("age"),
                "basic_info_bill_date":info.get("bill_date"), "lab_or_hospital_name":info.get("lab_or_hospital_name"),
                "report_details_page_no":str(item.get("page_no","")), "report_details_range":item.get("range"),
                "report_details_result":item.get("result"), "report_details_test_analytics":item.get("test_analytics"),
                "report_details_test_name":item.get("test_name"), "report_details_unit":item.get("unit"),
                "age_text":age_text, "age_years":str(age_years) if age_years is not None else None,
                "report_date":normalize_date(info.get("reports_date")), "page_number":str(item.get("page_no","")),
                "range_text_original":item.get("range"), "result_text_original":item.get("result"),
                "test_name":item.get("test_name"), "result":str(item.get("result","")),
                "unit":item.get("unit"), "range":item.get("range")
            })
            row["id"] = make_id({}, {"kind":"lab", "business": {
                "patient": row.get("patient_name"), "date": row.get("reports_date"),
                "test": row.get("test_name_canonical"), "result": row.get("result_value"),
                "result_text": row.get("result_text"), "unit": row.get("unit_canonical"),
                "range": row.get("range_text"), "page": row.get("page_number")
            }})
            rows.append(row)
    elif response.get("classifier") == "discharge_summary":
        age_years, age_text = normalize_age(data.get("age"))
        gender = normalize_gender(data.get("gender"))
        # One summary row gives the record inspector useful context.
        summary = dict(base)
        summary.update({
            "record_type":"discharge_summary", "patient_name":data.get("patientName"),
            "age":data.get("age"), "gender":gender, "doctor_name":data.get("doctorName"),
            "hospital_name":data.get("hospitalName"), "hospital_address":data.get("hospitalAddress"),
            "admission_date":normalize_date(data.get("admissionDate")), "discharge_date":normalize_date(data.get("dischargeDate")),
            "diagnosis":data.get("diagnosis"), "brief_history":data.get("briefHistory"),
            "general_examinations":data.get("generalExaminations"), "recommendations":data.get("recommendations"),
            "ward":data.get("ward"), "post_discharge_advice":data.get("postDischargeAdvice"),
            "medicine_injections_investigation":json.dumps(data.get("medicineInjectionsInvestigation", [])),
            "course_during_hospitalisation":json.dumps(data.get("courseDuringHospitalisation", [])),
            "course_during_hospitalization":json.dumps(data.get("courseDuringHospitalisation", [])),
            "age_text":age_text, "age_years":str(age_years) if age_years is not None else None,
        })
        summary["id"] = make_id({}, {"kind":"summary", "business": {
            "patient": summary.get("patient_name"), "admission": summary.get("admission_date"),
            "discharge": summary.get("discharge_date"), "diagnosis": summary.get("diagnosis"),
            "hospital": summary.get("hospital_name")
        }})
        rows.append(summary)
        for med in data.get("dischargeMedications", []):
            original, generic = normalize_medicine(med.get("medicine"), configs["medicines"])
            row = dict(base)
            row.update({
                "record_type":"discharge_medication", "patient_name":data.get("patientName"),
                "age":data.get("age"), "gender":gender, "doctor_name":data.get("doctorName"),
                "hospital_name":data.get("hospitalName"), "hospital_address":data.get("hospitalAddress"),
                "admission_date":normalize_date(data.get("admissionDate")), "discharge_date":normalize_date(data.get("dischargeDate")),
                "diagnosis":data.get("diagnosis"), "medicine":generic or original,
                "dose":med.get("dose"), "frequency":med.get("frequency"), "medicine_type":med.get("type"),
                "discharge_medications_dose":med.get("dose"), "discharge_medications_frequency":med.get("frequency"),
                "discharge_medications_medicine":original, "medication_dose":med.get("dose"),
                "medication_frequency":med.get("frequency"), "medication_name":generic or original,
                "medication_medicine":original, "age_text":age_text,
                "age_years":str(age_years) if age_years is not None else None,
            })
            row["id"] = make_id({}, {"kind":"med", "business": {
                "patient": row.get("patient_name"), "admission": row.get("admission_date"),
                "discharge": row.get("discharge_date"), "medicine": row.get("medicine"),
                "dose": row.get("dose"), "frequency": row.get("frequency")
            }})
            rows.append(row)
    return rows

def process_folder(input_dir, db_path, reset=False):
    if reset and Path(db_path).exists():
        Path(db_path).unlink()
    conn = init_db(db_path)
    configs = load_configs()
    started = datetime.now(timezone.utc).isoformat()
    run_id = hashlib.sha256(started.encode()).hexdigest()[:16]
    ingested = ingest_folder(input_dir)
    files_processed = files_failed = records_written = records_flagged = 0
    for item in ingested:
        p, payload, file_hash, error = item["path"], item["payload"], item["file_hash"], item["error"]
        ingested_at = datetime.now(timezone.utc).isoformat()
        if error:
            files_failed += 1
            conn.execute("INSERT OR REPLACE INTO raw_documents VALUES (?,?,?,?,?,?,?,?,?)",
                         (file_hash,p.name,None,None,None,ingested_at,"failed",error,None))
            continue
        data = payload.get("data", {})
        meta = meta_dict(data.get("metaDetails"))
        conn.execute("INSERT OR IGNORE INTO raw_documents VALUES (?,?,?,?,?,?,?,?,?)",
                     (file_hash,p.name,data.get("documentId"),payload.get("traceId"),meta.get("source_system"),
                      ingested_at,"processed",None,json.dumps(payload, sort_keys=True)))
        files_processed += 1
        for response in data.get("responseDetails", []):
            for row in transform_response(payload,response,p,file_hash,configs,ingested_at):
                values = [row.get(name) for name,_ in SCHEMA]
                cur = conn.execute(
                    f"INSERT OR IGNORE INTO standardized_records ({','.join(n for n,_ in SCHEMA)}) VALUES ({','.join('?' for _ in SCHEMA)})",
                    values
                )
                if cur.rowcount:
                    records_written += 1
                    if row.get("test_analytics") in {"Outlier","Above Range","Below Range","Invalid"}:
                        records_flagged += 1
    completed = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT INTO pipeline_runs VALUES (?,?,?,?,?,?,?,?)",
                 (run_id,started,completed,len(ingested),files_processed,files_failed,records_written,records_flagged))
    conn.commit()
    conn.close()
    return {
        "run_id":run_id, "files_received":len(ingested), "files_processed":files_processed,
        "files_failed":files_failed, "records_written":records_written, "records_flagged":records_flagged,
        "db_path":db_path
    }

def export_wide(db_path, out_csv):
    import pandas as pd
    conn = connect(db_path)
    df = pd.read_sql_query("""SELECT * FROM standardized_records
                              WHERE record_type='lab_result'
                              ORDER BY document_id, id""", conn)
    conn.close()
    if df.empty:
        pd.DataFrame().to_csv(out_csv,index=False)
        return
    # Assignment FR-2.2 asks for five columns per defined test. This wide export
    # is derived from the row-oriented canonical DB schema supplied with the task.
    fixed = [c for c in ["id","document_id","patient_name","age","gender","hospital_name"] if c in df.columns]
    out = df[fixed].drop_duplicates().set_index("id") if "id" in fixed else df[fixed]
    used_names = set(out.columns)
    for test in sorted(df["test_name_canonical"].dropna().unique()):
        safe = re.sub(r"[^A-Za-z0-9]+","_",test).strip("_") or "TEST"
        base_safe = safe
        i = 2
        while f"{safe}_Name" in used_names:
            safe = f"{base_safe}_{i}"
            i += 1
        rows = df[df["test_name_canonical"] == test]
        for field, suffix in [("test_name_canonical","Name"),("result_value","Result"),("range_text","Range"),("unit_canonical","Unit"),("test_analytics","Analytics")]:
            s = rows.set_index("id")[field].rename(f"{safe}_{suffix}")
            out = out.join(s, how="outer")
            used_names.add(f"{safe}_{suffix}")
    out.reset_index().to_csv(out_csv,index=False)
