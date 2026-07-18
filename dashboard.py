"""LeadPipe Doctor — live Streamlit dashboard.

Run: streamlit run dashboard.py
"""
from __future__ import annotations

import time

import duckdb
import pandas as pd
import streamlit as st

st.set_page_config(page_title="LeadPipe Doctor", page_icon="🩺", layout="wide")

DB_PATH = "data/leadpipe.duckdb"


@st.cache_resource
def get_con():
    return duckdb.connect(DB_PATH, read_only=True)


def q(sql: str) -> pd.DataFrame:
    try:
        return get_con().execute(sql).df()
    except duckdb.Error:
        get_con.clear()
        return get_con().execute(sql).df()


st.title("🩺 LeadPipe Doctor")
st.caption("The self-healing lead ingestion agent — every source, one clean table.")

auto = st.sidebar.toggle("Auto-refresh (2s)", value=True)
st.sidebar.markdown("---")

totals = q("""
    SELECT count(*) AS total,
           sum(CASE WHEN status = 'clean' THEN 1 ELSE 0 END) AS clean,
           sum(CASE WHEN status = 'flagged' THEN 1 ELSE 0 END) AS flagged,
           sum(CASE WHEN status = 'duplicate' THEN 1 ELSE 0 END) AS dupes,
           round(avg(quality_score), 1) AS avg_score
    FROM leads
""")
row = totals.iloc[0] if len(totals) else None

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total leads", f"{int(row['total'] or 0):,}" if row is not None else "0")
c2.metric("Clean", f"{int(row['clean'] or 0):,}" if row is not None else "0")
c3.metric("Flagged", f"{int(row['flagged'] or 0):,}" if row is not None else "0")
c4.metric("Duplicates", f"{int(row['dupes'] or 0):,}" if row is not None else "0")
c5.metric("Avg quality", row["avg_score"] if row is not None else "—")

left, right = st.columns(2)

with left:
    st.subheader("Leads per source")
    by_source = q("""
        SELECT source,
               sum(CASE WHEN status='clean' THEN 1 ELSE 0 END) AS clean,
               sum(CASE WHEN status='flagged' THEN 1 ELSE 0 END) AS flagged,
               sum(CASE WHEN status='duplicate' THEN 1 ELSE 0 END) AS duplicate
        FROM leads GROUP BY source ORDER BY source
    """)
    if len(by_source):
        st.bar_chart(by_source.set_index("source"), horizontal=True)
    else:
        st.info("No leads yet — run the pipeline.")

with right:
    st.subheader("Quality score distribution")
    dist = q("""
        SELECT (quality_score / 10) * 10 AS bucket, count(*) AS leads
        FROM leads WHERE status != 'duplicate' GROUP BY bucket ORDER BY bucket
    """)
    if len(dist):
        st.bar_chart(dist.set_index("bucket"))

st.subheader("🚑 Drift & heal events")
events = q("SELECT ts, source, event, attempt, detail FROM heal_events ORDER BY ts DESC LIMIT 20")
if len(events):
    for _, e in events.iterrows():
        icon = {"drift_detected": "🔴", "retry": "🟡", "healed": "🟢",
                "human_review": "🟠", "mapping_learned": "🧠"}.get(e["event"], "⚪")
        st.markdown(f"{icon} `{e['ts']}` **{e['source']}** — {e['event']}"
                    + (f" (attempt {int(e['attempt'])})" if e["attempt"] else ""))
        if e["event"] in ("drift_detected", "human_review") and e["detail"]:
            with st.expander("details"):
                st.code(e["detail"])
else:
    st.caption("No drift events. The doctor is on call.")

tab1, tab2 = st.tabs(["Latest leads", "Human-review queue"])
with tab1:
    st.dataframe(
        q("""
            SELECT first_name, last_name, email, phone_e164, source, campaign_id,
                   consent, created_at, quality_score, status, flags
            FROM leads ORDER BY ingested_at DESC LIMIT 200
        """),
        use_container_width=True, height=350,
    )
with tab2:
    review = q("SELECT ts, source, reason, raw_payload FROM review_queue ORDER BY ts DESC LIMIT 100")
    if len(review):
        st.dataframe(review, use_container_width=True, height=300)
    else:
        st.caption("Queue is empty.")

if auto:
    time.sleep(2)
    st.rerun()
