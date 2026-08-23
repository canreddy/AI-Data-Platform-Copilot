"""Deterministic SQL reviewer."""

from __future__ import annotations

import httpx
import streamlit as st

from ai_data_platform_copilot.ui.client import post_json

st.caption("Static SQLGlot analysis only. Submitted SQL is never executed.")
with st.form("sql_review_form"):
    dialect = st.selectbox("SQL dialect", ["bigquery", "duckdb"])
    governed = st.checkbox("Generated from a governed metric")
    explain = st.checkbox("Generate optional AI explanation")
    sql = st.text_area("SQL", value="select * from orders", height=280)
    submitted = st.form_submit_button("Review SQL", type="primary", icon=":material/rule:")
if submitted:
    try:
        st.session_state.sql_review_result = post_json(
            "/api/v1/sql/reviews",
            payload={"sql": sql, "dialect": dialect, "governed_metric_sql": governed, "include_explanation": explain},
        )
    except httpx.HTTPError as error:
        st.error(f"SQL review failed: {error}")
result = st.session_state.get("sql_review_result")
if isinstance(result, dict):
    st.caption(f"Read-only `{result['read_only']}` · valid `{result['valid_sql']}` · {result['duration_ms']} ms")
    for finding in result["findings"]:
        with st.container(border=True):
            st.subheader(f"{finding['severity'].upper()}: {finding['title']}")
            st.write(finding["message"])
            st.markdown(f"**Recommendation:** {finding['recommendation']}")
    if result.get("explanation"):
        with st.expander("AI explanation"):
            st.write(result["explanation"]["text"])
