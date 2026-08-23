"""Confirmed dbt lineage and impact explorer."""

from __future__ import annotations

import graphviz  # type: ignore[import-untyped]
import httpx
import streamlit as st

from ai_data_platform_copilot.ui.client import get_json

st.caption("Edges are confirmed dbt manifest dependencies.")
selector = st.text_input("Model name or dbt unique ID", value="customers")
direction = st.selectbox("Direction", ["both", "upstream", "downstream"])
max_depth = st.slider("Maximum depth", min_value=0, max_value=10, value=5)

if selector:
    try:
        lineage = get_json(f"/api/v1/lineage/{selector}", params={"direction": direction, "max_depth": max_depth})
    except httpx.HTTPError as error:
        st.error(f"Lineage API request failed: {error}")
    else:
        graph = graphviz.Digraph()
        graph.attr(rankdir="LR")
        for node in lineage["nodes"]:
            graph.node(node["unique_id"], label=f"{node['name']}\n{node['resource_type']}", shape="box")
        for edge in lineage["edges"]:
            graph.edge(edge["source"], edge["target"], label=edge["certainty"])
        st.graphviz_chart(graph, width="stretch")
        st.dataframe(lineage["nodes"], width="stretch", hide_index=True)
