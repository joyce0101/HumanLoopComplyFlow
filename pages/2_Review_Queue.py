"""Mock review queue; run from the repository root with Streamlit.

The queue and completed reviews live only in this browser session. Replace
the mock data source and submission sink with ledger interfaces at integration.
"""

from dataclasses import asdict
import json
import time

import plotly.graph_objects as go
import streamlit as st

from loopledger.schemas import Prediction, ReviewAction


FEATURE_LABELS = {
    "credit_amount": "Loan amount",
    "duration": "Term (months)",
    "age": "Age (years)",
}


def make_mock_pending_reviews() -> list[Prediction]:
    """Return fresh fixtures; contributions are illustrative, not model output."""
    return [
        Prediction(
            case_id="C-001",
            features={"credit_amount": 3000, "duration": 24, "age": 38},
            decision="reject",
            confidence=0.62,
            top_factors=[("duration", 0.30), ("credit_amount", 0.15), ("age", -0.08)],
        ),
        Prediction(
            case_id="C-002",
            features={"credit_amount": 5000, "duration": 12, "age": 31},
            decision="approve",
            confidence=0.66,
            top_factors=[("duration", -0.25), ("age", -0.12), ("credit_amount", 0.10)],
        ),
        Prediction(
            case_id="C-003",
            features={"credit_amount": 18000, "duration": 36, "age": 45},
            decision="approve",
            confidence=0.92,
            top_factors=[("age", -0.45), ("credit_amount", 0.25), ("duration", -0.20)],
        ),
        Prediction(
            case_id="C-004",
            features={"credit_amount": 7000, "duration": 48, "age": 22},
            decision="reject",
            confidence=0.69,
            top_factors=[("duration", 0.35), ("age", 0.20), ("credit_amount", -0.10)],
        ),
        Prediction(
            case_id="C-005",
            features={"credit_amount": 9000, "duration": 24, "age": 40},
            decision="approve",
            confidence=0.94,
            top_factors=[("age", -0.40), ("duration", -0.18), ("credit_amount", 0.15)],
            is_gold=True,
            gold_correct_decision="reject",
        ),
    ]


def submit_mock_review(action: ReviewAction) -> None:
    """Emit the agreed review contract without writing to the real ledger."""
    print("MOCK REVIEW:", json.dumps(asdict(action), ensure_ascii=False), flush=True)


def render_prediction(pred: Prediction) -> None:
    """Render only public fields; never pass a whole Prediction to the UI."""
    st.subheader(f"Application {pred.case_id}")
    columns = st.columns(3)
    for column, feature in zip(columns, FEATURE_LABELS):
        column.metric(FEATURE_LABELS[feature], f"{pred.features[feature]:,}")
    st.caption("Loan amounts use demo units; no currency has been assigned.")

    recommendation, explanation = st.columns([1, 2])
    with recommendation:
        st.markdown("#### AI recommendation")
        if pred.decision == "approve":
            st.success("Approve application")
        else:
            st.warning("Reject application")
        st.metric("Confidence", f"{pred.confidence:.0%}")
        st.progress(pred.confidence)

    with explanation:
        st.markdown("#### Top contributing factors")
        names, values = zip(*pred.top_factors)
        figure = go.Figure(
            go.Bar(
                x=list(values),
                y=[FEATURE_LABELS.get(name, name) for name in names],
                orientation="h",
                marker_color=["#dc2626" if value > 0 else "#16a34a" for value in values],
                hovertemplate="%{y}: %{x:+.2f}<extra></extra>",
            )
        )
        figure.add_vline(x=0, line_color="#94a3b8", line_width=1)
        figure.update_layout(
            height=240,
            margin=dict(l=0, r=20, t=10, b=10),
            xaxis_title="Contribution toward rejection",
            yaxis=dict(autorange="reversed"),
            showlegend=False,
        )
        st.plotly_chart(figure, width="stretch", key="rq_factors")
        st.caption(
            "Illustrative values, not measured SHAP output. "
            "Positive → reject; negative → approve."
        )


def render_review_form(pred: Prediction) -> None:
    """Validate first, then submit and transition the mock queue once."""
    state = st.session_state
    st.markdown("#### Your decision")
    elapsed = max(0.0, time.perf_counter() - state["rq_started_at"])
    st.caption(
        f"Time on this visit: {elapsed:.1f}s. Final elapsed time is recorded "
        "on submission and includes time spent away from the page."
    )
    with st.form("rq_review_form", clear_on_submit=False):
        reviewer = st.text_input("Reviewer", key="rq_reviewer", placeholder="e.g. alice")
        reason = st.text_area(
            "Reason (required)",
            key=f"rq_reason_{pred.case_id}",
            placeholder="Explain your decision after reviewing the application.",
        )
        approve_column, reject_column, modify_column = st.columns(3)
        approve = approve_column.form_submit_button(
            "Approve application", key=f"rq_approve_{pred.case_id}", type="primary"
        )
        reject = reject_column.form_submit_button(
            "Reject application", key=f"rq_reject_{pred.case_id}"
        )
        modify_column.form_submit_button("Modify terms", disabled=True)
        st.caption("Modify terms is unavailable in this demo.")

    if not (approve or reject):
        return
    if not reviewer.strip():
        st.error("Enter the reviewer's name before submitting.")
        return
    if not reason.strip():
        st.error("Enter a reason before submitting.")
        return
    if any(review.case_id == pred.case_id for review in state["rq_submitted_reviews"]):
        st.error("This application has already been reviewed.")
        return

    action = ReviewAction(
        case_id=pred.case_id,
        reviewer=reviewer.strip(),
        action="approve" if approve else "reject",
        reason=reason.strip(),
        seconds_spent=max(0.0, time.perf_counter() - state["rq_started_at"]),
    )
    try:
        submit_mock_review(action)
    except Exception:
        # A failed sink must not discard input or advance the selected case.
        st.error("Submission failed. Your input is preserved; please try again.")
        return

    state.setdefault("rq_reviewed_predictions", {})[pred.case_id] = pred
    state["rq_submitted_reviews"].append(action)
    state["rq_pending_reviews"] = [
        case for case in state["rq_pending_reviews"] if case.case_id != pred.case_id
    ]
    state["rq_success_message"] = (
        f"Mock review saved for {pred.case_id}: "
        f"{'approved' if action.action == 'approve' else 'rejected'} "
        f"by {action.reviewer} ({action.seconds_spent:.1f}s)."
    )
    st.rerun()


def main() -> None:
    st.set_page_config(page_title="Review Queue | LoopLedger", page_icon="📋", layout="wide")
    state = st.session_state
    if "rq_pending_reviews" not in state:
        state["rq_pending_reviews"] = make_mock_pending_reviews()
    if "rq_submitted_reviews" not in state:
        state["rq_submitted_reviews"] = []

    st.title("Review Queue")
    st.write("Review the application and AI recommendation, then record your own decision.")
    st.warning(
        "Mock data mode / 模拟数据模式 — reviews are kept only in this browser "
        "session and printed to the terminal. No database records are written. "
        "A browser reload may reset this demo."
    )
    if message := state.pop("rq_success_message", None):
        st.success(message)

    pending = state["rq_pending_reviews"]
    pending_column, completed_column = st.columns(2)
    pending_column.metric("Pending applications", len(pending))
    completed_column.metric("Reviewed this session", len(state["rq_submitted_reviews"]))
    if not pending:
        state.pop("rq_active_case_id", None)
        state.pop("rq_started_at", None)
        st.info("No pending applications. All mock cases have been reviewed.")
        return

    queue_column, detail_column = st.columns([1, 3])
    case_ids = [case.case_id for case in pending]
    # Repair stale selection before constructing its widget, never after it.
    if state.get("rq_case_selector") not in case_ids:
        state["rq_case_selector"] = case_ids[0]
    with queue_column:
        st.subheader("Pending queue")
        selected_id = st.selectbox("Choose an application", case_ids, key="rq_case_selector")
        st.caption("Approve or reject the application itself, regardless of the AI's suggestion.")

    if state.get("rq_active_case_id") != selected_id:
        state["rq_active_case_id"] = selected_id
        state["rq_started_at"] = time.perf_counter()
    selected_case = next(case for case in pending if case.case_id == selected_id)
    with detail_column:
        render_prediction(selected_case)
        render_review_form(selected_case)


if __name__ == "__main__":
    main()
