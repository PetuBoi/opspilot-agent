"""Run with Streamlit; all investigation controls call the authenticated API."""

import os

import httpx
import pandas as pd
import streamlit as st

st.set_page_config(page_title="OpsPilot", page_icon="🧭", layout="wide")
st.title("OpsPilot · Incident workspace")
st.caption("Northstar Workshop · SYNTHETIC environment · Offline summaries are non-LLM templates")
base_url = os.getenv("OPSPILOT_API_URL", "http://127.0.0.1:8000")
token = st.sidebar.text_input(
    "Local API token", value=os.getenv("OPSPILOT_API_TOKEN", ""), type="password"
)


def api(method: str, path: str, body=None):
    try:
        response = httpx.request(
            method,
            base_url + path,
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=90,
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        st.error(
            "API request failed. Check the running API, token, setup commands and server logs."
        )
        return None


if not token:
    st.info("Start the API and enter its local token to load tickets and approve actions.")
    st.stop()

workspace, history_tab, metrics_tab = st.tabs(
    ["Investigate", "Investigation history", "Evaluation"]
)
with workspace:
    tickets = api("GET", "/api/v1/tickets") or []
    options = {f"{t['id']} · {t['title']}": t for t in tickets}
    selected = st.selectbox("Ticket", ["Custom ticket", *options])
    chosen = options.get(selected, {})
    with st.form("analyze"):
        title = st.text_input("Title", value=chosen.get("title", "VPN certificate expired"))
        description = st.text_area(
            "Description", value=chosen.get("description", "VPN stopped working today")
        )
        severity = st.selectbox(
            "User-reported severity", ["unknown", "low", "medium", "high", "critical"]
        )
        propose = st.checkbox("Prepare a note for human approval", value=True)
        submitted = st.form_submit_button("Investigate", type="primary")
    if submitted:
        result = api(
            "POST",
            "/api/v1/tickets/analyze",
            {
                "title": title,
                "description": description,
                "severity": severity,
                "propose_action": propose,
                "ticket_id": chosen.get("id"),
            },
        )
        if result:
            st.session_state["investigation"] = result
    result = st.session_state.get("investigation")
    if result:
        a, b, c = st.columns(3)
        a.metric("Category", result["classification"]["label"])
        b.metric("Severity (user reported)", result["ticket"]["severity"])
        c.metric("Status", result["status"])
        st.caption(
            f"Classifier: {result['classification']['model']} · "
            f"Dataset: {result['classification']['dataset']}"
        )
        st.info(result["generation"])
        st.write(result["summary"])
        for warning in result["warnings"]:
            st.warning(warning)
        st.graphviz_chart(
            "digraph { rankdir=LR; "
            + ";".join(
                f'"{left}" -> "{right}"'
                for left, right in zip(
                    result["workflow_nodes"], result["workflow_nodes"][1:], strict=False
                )
            )
            + " }"
        )
        st.subheader("Evidence")
        for evidence in result["evidence"]:
            with st.expander(
                f"{evidence['source']} · {evidence['document_id']} · {evidence['chunk_id']}"
            ):
                st.text(evidence["text"])
                st.download_button(
                    "Download source excerpt",
                    evidence["text"],
                    file_name=evidence["source"] + ".txt",
                    key=evidence["chunk_id"],
                )
        st.subheader("Troubleshooting")
        for step in result["steps"]:
            st.write(f"• {step}")
        st.json(result["service_health"])
        with st.expander("Historical incidents (synthetic)"):
            st.json(result["history"])
        if result["action"]:
            st.subheader("Proposed local action")
            st.json(result["action"])
        if result["status"] == "pending":
            note = st.text_input("Review note")
            approve, reject = st.columns(2)
            decision = (
                "approve"
                if approve.button("Approve note attachment")
                else ("reject" if reject.button("Reject action") else None)
            )
            if decision:
                updated = api(
                    "POST", f"/api/v1/investigations/{result['id']}/{decision}", {"note": note}
                )
                if updated:
                    st.session_state["investigation"] = updated
                    st.rerun()
        st.subheader("Audit trail")
        st.json(api("GET", f"/api/v1/investigations/{result['id']}/audit"))
with history_tab:
    history = api("GET", "/api/v1/investigations") or []
    for item in history:
        if st.button(
            f"{item['ticket']['title']} · {item['status']} · {item['id']}", key=item["id"]
        ):
            st.session_state["investigation"] = item
            st.info("Loaded. Open Investigate to review this investigation.")
with metrics_tab:
    metrics = api("GET", "/api/v1/evaluation/summary") or {}
    for name, values in metrics.items():
        with st.expander(name.replace("_", " ").title(), expanded=True):
            if "comparison" in values:
                st.dataframe(pd.DataFrame(values["comparison"]), hide_index=True)
            st.json(values)
    for filename in (
        "reports/real/linear_svc_confusion_matrix.png",
        "reports/real/category_distribution.png",
    ):
        if os.path.isfile(filename):
            st.image(filename)
