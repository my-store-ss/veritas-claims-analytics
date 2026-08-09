
import json
import sqlite3
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "claims.db"
INPUT = ROOT / "sample-data"

st.set_page_config(page_title="Veritas Claims Analytics", layout="wide")
st.title("Veritas Claims Analytics")
st.caption("Medical data standardisation prototype — local files simulate GCS.")

@st.cache_data(ttl=5)
def load_table(query):
    if not DB.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def run_pipeline():
    from src.pipeline import process_folder
    result = process_folder(str(INPUT), str(DB), reset=False)
    st.cache_data.clear()
    return result

if st.button("Run pipeline on sample-data"):
    with st.spinner("Processing..."):
        result = run_pipeline()
    st.success(f"Run {result['run_id']} completed.")
    st.json(result)

records = load_table("SELECT * FROM standardized_records")
runs = load_table("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 10")
raw = load_table("SELECT * FROM raw_documents")

if records.empty:
    st.warning("No database found. Run the pipeline first.")
    st.stop()

c1,c2,c3,c4 = st.columns(4)
c1.metric("Files received (latest)", int(runs.iloc[0]["files_received"]) if not runs.empty else 0)
c2.metric("Records", len(records))
c3.metric("Flagged", int(records["test_analytics"].isin(["Outlier","Above Range","Below Range","Invalid"]).sum()))
c4.metric("Failed files", int(runs.iloc[0]["files_failed"]) if not runs.empty else 0)

tabs = st.tabs(["Pipeline Runs", "Flagged Records", "Clinic Quality", "Record Inspector"])

with tabs[0]:
    st.subheader("Pipeline run summary")
    st.dataframe(runs, use_container_width=True)

with tabs[1]:
    st.subheader("Validation flag queue")
    flagged = records[records["test_analytics"].isin(["Outlier","Above Range","Below Range","Invalid"])].copy()
    st.dataframe(flagged[[
        "document_id","record_type","hospital_name","test_name_original",
        "test_name_canonical","result_value","result_text","range_text","unit_canonical","test_analytics"
    ]].head(500), use_container_width=True)

with tabs[2]:
    st.subheader("Clinic-level quality")
    lab = records[records["record_type"]=="lab_result"].copy()
    if lab.empty:
        st.info("No lab records.")
    else:
        stats = lab.groupby("hospital_name", dropna=False).agg(
            total_records=("id","count"),
            flagged_records=("test_analytics", lambda s: s.isin(["Outlier","Above Range","Below Range","Invalid"]).sum()),
            missing_result=("result_value", lambda s: s.isna().sum()),
            unique_tests=("test_name_canonical","nunique"),
        ).reset_index()
        stats["flag_rate"] = (stats["flagged_records"] / stats["total_records"]).round(4)
        st.dataframe(stats, use_container_width=True)

with tabs[3]:
    st.subheader("Record inspector")
    ids = records["id"].tolist()
    selected = st.selectbox("Select record", ids)
    row = records[records["id"]==selected].iloc[0]
    left,right = st.columns(2)
    with left:
        st.json({k: (None if pd.isna(v) else v) for k,v in row.to_dict().items() if k not in {"raw_json"}})
    with right:
        doc_id = row["document_id"]
        candidates = raw[raw["document_id"]==doc_id]
        if not candidates.empty:
            try:
                st.json(json.loads(candidates.iloc[0]["raw_json"]))
            except Exception:
                st.text(candidates.iloc[0]["raw_json"])
        else:
            st.info("Raw document not available for this record.")
