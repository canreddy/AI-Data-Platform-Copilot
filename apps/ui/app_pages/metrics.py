"""Governed metric discovery and compile-only query explorer."""

from __future__ import annotations

from datetime import date

import httpx
import streamlit as st

from ai_data_platform_copilot.ui.client import get_json, get_list, post_json

st.caption(
    "Discover governed definitions, compile MetricFlow SQL, and optionally run it on the read-only demo database."
)
metric_list: list[dict[str, object]] = []
try:
    metric_list = get_list("/api/v1/metrics")
except httpx.HTTPError as error:
    st.error(f"Metrics API request failed: {error}")
    st.stop()

metric_name = st.selectbox("Metric", [str(item["name"]) for item in metric_list]) if metric_list else None
if metric_name:
    details = get_json(f"/api/v1/metrics/{metric_name}")
    lineage = get_json(f"/api/v1/metrics/{metric_name}/lineage")
    dimensions = get_list(f"/api/v1/metrics/{metric_name}/dimensions")
    with st.container(border=True):
        st.subheader(details["label"])
        st.write(details["description"])
        st.caption(
            f"Type `{details['type']}` · measure `{details['measure']}` · semantic model `{details['semantic_model']}`"
        )
    group_by = st.multiselect(
        "Group by", dimensions, default=["metric_time__month"] if "metric_time__month" in dimensions else []
    )
    limit_to_year = st.checkbox("Limit to calendar year")
    year = st.number_input("Year", min_value=1900, max_value=2200, value=2018, disabled=not limit_to_year)
    query_payload = {
        "metric": metric_name,
        "group_by": group_by,
        "filters": [],
        "start_time": date(int(year), 1, 1).isoformat() if limit_to_year else None,
        "end_time": date(int(year), 12, 31).isoformat() if limit_to_year else None,
    }
    if st.button("Compile SQL", type="primary", icon=":material/code:"):
        try:
            compiled = post_json("/api/v1/metric-queries/compile", payload=query_payload)
        except httpx.HTTPError as error:
            st.error(f"MetricFlow compilation failed: {error}")
        else:
            st.session_state.metric_compilation = compiled
            st.session_state.metric_execution_query = query_payload
            st.session_state.pop("metric_execution_result", None)

    stored_compilation = st.session_state.get("metric_compilation")
    if isinstance(stored_compilation, dict) and stored_compilation["request"]["metric"] == metric_name:
        if stored_compilation["validation"]["valid"]:
            st.code(stored_compilation["sql"], language="sql")
            st.info("Compiled only. Execution requires confirmation below.")
            confirmed = st.checkbox(
                "I confirm execution of this governed query on the included read-only Jaffle Shop DuckDB database.",
                key="metric_execution_confirmed",
            )
            if st.button(
                "Execute on demo DuckDB",
                type="primary",
                icon=":material/play_arrow:",
                disabled=not confirmed,
            ):
                try:
                    st.session_state.metric_execution_result = post_json(
                        "/api/v1/metric-queries/execute",
                        payload={"query": st.session_state.metric_execution_query, "confirmed": True},
                    )
                except httpx.HTTPError as error:
                    st.error(f"Read-only metric execution failed: {error}")
        else:
            st.error("\n".join(stored_compilation["validation"]["errors"]))

    execution = st.session_state.get("metric_execution_result")
    if isinstance(execution, dict) and execution["compilation"]["request"]["metric"] == metric_name:
        st.success(
            f"Executed with `{execution['connection_mode']}` access in {execution['duration_ms']} ms "
            f"({execution['row_count']} row(s))."
        )
        st.dataframe(execution["rows"], width="stretch", hide_index=True)
        with st.expander("Execution evidence"):
            st.json(execution)
    with st.expander("Metric lineage and evidence"):
        st.dataframe(lineage["nodes"], width="stretch", hide_index=True)
        st.json(details["evidence"])
