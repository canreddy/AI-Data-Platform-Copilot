"""Metadata search and detail page."""

from __future__ import annotations

import httpx
import streamlit as st

from ai_data_platform_copilot.ui.client import get_json

st.caption("Search models, descriptions, file paths, and columns with artifact evidence.")
query = st.text_input("Search", value="orders")
resource_types = st.multiselect("Resource types", ["model", "seed", "source", "snapshot"])

if query:
    params: dict[str, object] = {"q": query, "limit": 50}
    if resource_types:
        params["resource_type"] = resource_types
    try:
        payload = get_json("/api/v1/metadata/search", params=params)
    except httpx.HTTPError as error:
        st.error(f"Metadata API request failed: {error}")
    else:
        st.caption(f"Snapshot `{payload['snapshot_id']}` · {len(payload['results'])} results")
        for result in payload["results"]:
            resource = result["resource"]
            with st.expander(f"{resource['name']} · {resource['resource_type']} · {result['match_reason']}"):
                st.write(resource["description"] or "No description available.")
                st.code(resource["unique_id"])
                if resource["columns"]:
                    st.dataframe(resource["columns"], width="stretch", hide_index=True)
                st.json(resource["evidence"], expanded=False)
