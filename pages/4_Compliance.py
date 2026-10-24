"""Compliance UI with explicit demo fixtures and deferred B/D interface calls.

No database writes, report generation, or verification occur on ordinary page
loads. Exports are kept as a complete bundle and invalidated before retries.
"""

from datetime import datetime, timezone
import importlib
import json
import re
from uuid import uuid4

import streamlit as st


class StaleIntegrityError(ValueError):
    """The report no longer describes the chain result the user checked."""


def unchecked_chain() -> dict:
    return {"status": "unchecked", "intact": None, "broken_id": None}


def validate_chain_result(result) -> tuple[bool, int | None]:
    if not isinstance(result, tuple) or len(result) != 2:
        raise ValueError("verify_chain() must return (bool, event_id_or_none).")
    intact, broken_id = result
    if not isinstance(intact, bool):
        raise ValueError("Chain integrity must be a boolean.")
    if intact and broken_id is not None:
        raise ValueError("An intact chain cannot have a broken event ID.")
    if not intact and (type(broken_id) is not int or broken_id <= 0):
        raise ValueError("An inconsistent chain must identify its first failed event.")
    return intact, broken_id


def verify_chain_for_source(source: str, scenario: str | None) -> tuple[bool, int | None]:
    if source == "UI demo":
        if scenario == "Execution error":
            raise RuntimeError("Simulated chain verification failure. Choose another demo response to retry.")
        result = (False, 17) if scenario == "Inconsistency at #17" else (True, None)
    else:
        ledger = importlib.import_module("loopledger.ledger")
        if not callable(getattr(ledger, "verify_chain", None)):
            raise RuntimeError("B's verify_chain() interface is not available yet.")
        result = ledger.verify_chain()
    return validate_chain_result(result)


def build_export_bundle(source: str, chain: dict, simulate_error: bool = False) -> dict:
    """Prepare and validate both artifacts before exposing either download."""
    if chain["status"] not in ("passed", "inconsistent"):
        raise ValueError("Verify the chain before generating a report.")
    if source == "UI demo":
        if simulate_error:
            raise RuntimeError("Simulated report-generation failure. Turn off the failure option and retry.")
        data = {
            "project": "LoopLedger",
            "report_id": f"ui-demo-{uuid4().hex[:12]}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_origin": "UI demo fixture; not database evidence or session-review statistics",
            "integrity": {
                "chain_intact": chain["intact"],
                "first_broken_event_id": chain["broken_id"],
            },
        }
        outcome = "PASS" if chain["intact"] else "FAIL"
        broken = "None" if chain["broken_id"] is None else f"#{chain['broken_id']}"
        markdown = (
            "# LoopLedger — UI Demo Evidence Report\n\n"
            f"**Report ID:** `{data['report_id']}`\n\n"
            f"**Generated at (UTC):** {data['generated_at']}\n\n"
            f"**Data origin:** {data['data_origin']}\n\n"
            "## Chain-check response\n\n"
            f"- Result: **{outcome} (synthetic demo response)**\n"
            f"- First inconsistent event: {broken}\n\n"
            "## Scope\n\n"
            "This fixture demonstrates preview and download behavior. It does not "
            "verify the real SQLite database, include actual session approvals, "
            "or establish regulatory compliance.\n"
        )
    else:
        evidence = importlib.import_module("loopledger.evidence")
        if not all(callable(getattr(evidence, name, None)) for name in ("build_report_json", "build_report")):
            raise RuntimeError("D's build_report_json() and build_report() interfaces are required.")
        data = evidence.build_report_json()
        markdown = evidence.build_report()

    if not isinstance(data, dict) or not data:
        raise ValueError("The JSON report must be a nonempty object.")
    json_text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("The Markdown report is empty or invalid.")
    integrity = data.get("integrity")
    if not isinstance(integrity, dict):
        raise ValueError("The JSON report must contain an integrity result.")
    report_result = validate_chain_result((
        integrity.get("chain_intact"), integrity.get("first_broken_event_id"),
    ))
    if report_result != (chain["intact"], chain["broken_id"]):
        raise StaleIntegrityError("The report's chain result changed. Run Verify chain again before exporting.")
    report_id = data.get("report_id")
    markdown_id = re.search(r"^\*\*Report ID:\*\*\s*`([^`]+)`", markdown, re.MULTILINE)
    if not isinstance(report_id, str) or not report_id.strip() or not markdown_id:
        raise ValueError("Both report formats must expose the same Report ID.")
    if markdown_id.group(1) != report_id:
        raise ValueError("Markdown and JSON Report IDs differ. Records may have changed; generate again.")
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", report_id)[:64]
    origin = "ui-demo" if source == "UI demo" else "backend"
    return {
        "markdown": markdown,
        "json_text": json_text,
        "filename": f"loopledger_{origin}_{safe_id}",
        "source": source,
    }


def render_chain_status(chain: dict, source: str) -> None:
    prefix = "DEMO — " if source == "UI demo" else ""
    if chain["status"] == "unchecked":
        st.info("Not checked / 未校验 — click Verify chain to request a result.")
    elif chain["status"] == "passed":
        st.success(f"{prefix}Check passed / 校验通过 — chain intact for the checked records.")
    elif chain["status"] == "inconsistent":
        st.error(f"{prefix}Inconsistency detected / 发现异常 — first failed event #{chain['broken_id']}.")
    else:
        st.error(f"{prefix}Execution failed / 执行失败 — {chain['error']}")


def main() -> None:
    st.set_page_config(page_title="Compliance & Evidence | LoopLedger", page_icon="📄", layout="wide")
    st.title("Compliance & Evidence")
    st.write("Check audit-chain consistency, preview a report, and download its evidence artifacts.")
    source = st.radio("Data source", ["UI demo", "Backend interfaces"], key="cp_source", horizontal=True)
    if source == "UI demo":
        st.warning(
            "UI demo / 界面演示 — verification responses and report content are synthetic. "
            "No real database is checked or modified, and session approvals are not included."
        )
    else:
        st.info("Backend mode calls B's chain verification and D's report interfaces. No fallback to demo results.")

    st.subheader("1. Chain verification")
    scenario = None
    if source == "UI demo":
        scenario = st.selectbox(
            "Demo chain response", ["Pass", "Inconsistency at #17", "Execution error"], key="cp_demo_chain"
        )
    state = st.session_state
    context = (source, scenario)
    if state.get("cp_context") != context:
        state["cp_context"] = context
        state["cp_chain"] = unchecked_chain()
        state["cp_export"] = None
        state["cp_report_error"] = None

    if st.button("Verify chain", key="cp_verify", type="primary"):
        # Rechecking invalidates old artifacts even if the new request fails.
        state["cp_export"] = None
        state["cp_report_error"] = None
        try:
            with st.spinner("Checking chain consistency…"):
                intact, broken_id = verify_chain_for_source(source, scenario)
            state["cp_chain"] = {
                "status": "passed" if intact else "inconsistent",
                "intact": intact,
                "broken_id": broken_id,
            }
        except Exception as error:
            state["cp_chain"] = {**unchecked_chain(), "status": "error", "error": str(error)}
    render_chain_status(state["cp_chain"], source)

    st.subheader("2. Markdown report preview")
    simulate_error = False
    if source == "UI demo":
        simulate_error = st.checkbox("Simulate report-generation failure", key="cp_demo_report_error")
    can_generate = state["cp_chain"]["status"] in ("passed", "inconsistent")
    if st.button("Generate report", key="cp_generate", disabled=not can_generate) and can_generate:
        state["cp_export"] = None
        state["cp_report_error"] = None
        try:
            with st.spinner("Generating Markdown and JSON evidence…"):
                state["cp_export"] = build_export_bundle(source, state["cp_chain"], simulate_error)
        except StaleIntegrityError as error:
            state["cp_chain"] = unchecked_chain()
            state["cp_report_error"] = str(error)
            # Refresh controls already drawn above so no stale PASS badge or
            # enabled Generate button survives a changed integrity result.
            st.rerun()
        except Exception as error:
            state["cp_report_error"] = str(error)
    if state.get("cp_report_error"):
        st.error(f"Could not generate report: {state['cp_report_error']}")
    bundle = state.get("cp_export")
    if bundle:
        with st.container(height=420, border=True):
            st.markdown(bundle["markdown"])
        st.caption(f"Prepared from {bundle['source']}. The preview is the exact Markdown offered for download.")
    else:
        st.info("No report is ready. Complete a chain check, then generate the report.")

    st.subheader("3. Downloads")
    markdown_column, json_column = st.columns(2)
    markdown_column.download_button(
        "Download Markdown",
        data=bundle["markdown"].encode("utf-8") if bundle else b"",
        file_name=f"{bundle['filename']}.md" if bundle else "loopledger_report.md",
        mime="text/markdown; charset=utf-8", key="cp_download_markdown",
        disabled=bundle is None, on_click="ignore",
    )
    json_column.download_button(
        "Download JSON",
        data=bundle["json_text"].encode("utf-8") if bundle else b"",
        file_name=f"{bundle['filename']}.json" if bundle else "loopledger_report.json",
        mime="application/json", key="cp_download_json",
        disabled=bundle is None, on_click="ignore",
    )


if __name__ == "__main__":
    main()
