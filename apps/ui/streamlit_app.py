"""Streamlit entry point with explicit modern navigation."""

import streamlit as st

st.set_page_config(page_title="AI Data Platform Copilot", page_icon=":material/database:", layout="wide")

page = st.navigation(
    [
        st.Page("app_pages/copilot.py", title="Copilot", icon=":material/chat:"),
        st.Page("app_pages/metadata.py", title="Metadata explorer", icon=":material/search:"),
        st.Page("app_pages/lineage.py", title="Lineage explorer", icon=":material/account_tree:"),
        st.Page("app_pages/sql_review.py", title="SQL reviewer", icon=":material/rule:"),
        st.Page("app_pages/metrics.py", title="Metrics explorer", icon=":material/monitoring:"),
    ],
    position="top",
)
st.title(f"{page.icon} {page.title}")
page.run()
