"""Optional evidence-backed chat page."""

from __future__ import annotations

import httpx
import streamlit as st

from ai_data_platform_copilot.ui.client import get_json, post_json

st.caption("Natural-language orchestration over deterministic metadata and metric tools.")

capabilities = {"copilot_chat": False}
try:
    capabilities = get_json("/api/v1/capabilities")
except httpx.HTTPError as error:
    st.error(f"Copilot API request failed: {error}")
    st.stop()

if not capabilities["copilot_chat"]:
    st.info("Copilot chat is disabled. Set `OPENAI_API_KEY` and restart the API to enable it.")
    st.write("Metadata, lineage, SQL review, and governed metric pages remain fully available without an API key.")
    st.stop()

if "copilot_messages" not in st.session_state:
    st.session_state.copilot_messages = []

for message in st.session_state.copilot_messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])
        if message.get("rows"):
            st.dataframe(message["rows"], hide_index=True)
        if message.get("evidence"):
            with st.expander("Tool evidence"):
                st.json(message["evidence"])

if question := st.chat_input("Ask about dbt models or governed metrics", submit_mode="disable"):
    st.session_state.copilot_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)
    try:
        response = post_json("/api/v1/chat", payload={"question": question})
    except httpx.HTTPError as error:
        st.error(f"Copilot request failed: {error}")
    else:
        message = {"role": "assistant", "content": response["answer"], "evidence": response["evidence"]}
        st.session_state.copilot_messages.append(message)
        if response.get("confirmation_required") and response.get("execution_query"):
            st.session_state.copilot_pending_execution = {
                "query": response["execution_query"],
                "evidence": response["evidence"],
            }
        with st.chat_message("assistant"):
            st.write(response["answer"])
            st.caption(" · ".join(item["tool"] for item in response["tool_activity"]))
            with st.expander("Tool evidence"):
                st.json(response["evidence"])

pending = st.session_state.get("copilot_pending_execution")
if isinstance(pending, dict):
    with st.container(border=True):
        st.subheader("Execution confirmation required")
        st.write(
            "Run this server-compiled governed metric query only against the included Jaffle Shop DuckDB database "
            "using a read-only connection?"
        )
        st.json(pending["query"], expanded=False)
        confirmed = st.checkbox(
            "I confirm this read-only demo metric execution.",
            key="copilot_execution_confirmed",
        )
        if st.button(
            "Confirm and execute",
            type="primary",
            icon=":material/play_arrow:",
            disabled=not confirmed,
        ):
            try:
                result = post_json(
                    "/api/v1/metric-queries/execute",
                    payload={"query": pending["query"], "confirmed": True},
                )
            except httpx.HTTPError as error:
                st.error(f"Read-only metric execution failed: {error}")
            else:
                query = result["compilation"]["request"]
                rows = result["rows"]
                if len(rows) == 1 and query["metric"] in rows[0]:
                    value_text = f"{query['metric']}: {rows[0][query['metric']]}"
                else:
                    value_text = f"{result['row_count']} row(s) returned"
                period = (
                    f" from {query['start_time']} through {query['end_time']}"
                    if query.get("start_time") and query.get("end_time")
                    else ""
                )
                interpretation = result.get("interpretation")
                content = interpretation or f"Confirmed result{period}: **{value_text}**."
                st.session_state.copilot_messages.append(
                    {
                        "role": "assistant",
                        "content": content,
                        "rows": rows if len(rows) > 1 else None,
                        "evidence": result,
                    }
                )
                del st.session_state.copilot_pending_execution
                st.rerun()
