"""Persisted review queue using the ledger's read and submission interfaces."""

from dataclasses import asdict
from html import escape
import json
import hashlib
import math
from textwrap import wrap
import time

import plotly.graph_objects as go
import streamlit as st

from loopledger.schemas import Prediction, ReviewAction


FEATURE_LABELS = {
    "credit_amount": "Loan amount",
    "duration": "Term (months)",
    "age": "Age (years)",
}


# Category descriptions follow the bundled German Credit german.doc.
CATEGORY_LABELS = {
    "purpose": {
        "A40": "New car", "A41": "Used car", "A42": "Furniture / equipment",
        "A43": "Radio / television", "A44": "Domestic appliances", "A45": "Repairs",
        "A46": "Education", "A48": "Retraining", "A49": "Business", "A410": "Other purpose",
    },
    "credit_history": {
        "A30": "No prior credits / all credits repaid duly",
        "A31": "All credits at this bank repaid duly",
        "A32": "Existing credits repaid duly so far",
        "A33": "Prior repayment delays",
        "A34": "Critical account / other credits outside this bank",
    },
    "checking_status": {
        "A11": "Balance below 0 DM", "A12": "Balance from 0 to below 200 DM",
        "A13": "Balance at least 200 DM / salary assigned for at least 1 year",
        "A14": "No checking account",
    },
    "savings_status": {
        "A61": "Below 100 DM", "A62": "100 to below 500 DM",
        "A63": "500 to below 1,000 DM", "A64": "At least 1,000 DM",
        "A65": "Unknown / no savings account",
    },
    "employment": {
        "A71": "Unemployed", "A72": "Less than 1 year", "A73": "1 to less than 4 years",
        "A74": "4 to less than 7 years", "A75": "At least 7 years",
    },
    "other_parties": {"A101": "None", "A102": "Co-applicant", "A103": "Guarantor"},
    "housing": {"A151": "Rented housing", "A152": "Owned housing", "A153": "Free housing"},
    "property_magnitude": {
        "A121": "Real estate", "A122": "Building-society savings / life insurance",
        "A123": "Car / other property (excluding savings)", "A124": "Unknown / no property",
    },
    "other_payment_plans": {
        "A141": "Bank installment plan", "A142": "Store installment plan", "A143": "None",
    },
}

APPLICATION_DETAIL_GROUPS = (
    ("Credit & repayment", (
        ("purpose", "Loan purpose"), ("credit_history", "Credit history"),
        ("existing_credits", "Existing credits at this bank"),
        ("other_payment_plans", "Other installment plans"),
        ("other_parties", "Other debtors / guarantors"),
    )),
    ("Finances & employment", (
        ("checking_status", "Checking account"), ("savings_status", "Savings / bonds"),
        ("employment", "Employment tenure"), ("housing", "Housing"),
        ("property_magnitude", "Property"), ("num_dependents", "People financially supported"),
    )),
)

FACTOR_LIMIT = 10
FACTOR_LABELS = {
    **FEATURE_LABELS,
    **{field: label for _, fields in APPLICATION_DETAIL_GROUPS for field, label in fields},
    "installment_commitment": "Installment rate code",
    "residence_since": "Residence duration",
    "personal_status": "Personal status", "job": "Occupation",
    "own_telephone": "Registered telephone", "foreign_worker": "Foreign-worker flag",
}
FACTOR_DESCRIPTIONS = {
    "credit_amount": "Requested loan amount in dataset units.",
    "duration": "Requested repayment period in months.",
    "age": "Applicant age in years.",
    "purpose": "The stated use of the requested loan.",
    "credit_history": "The dataset's record of previous credit and repayment behavior.",
    "checking_status": "Existing checking-account status; balance bands use the original DM units.",
    "savings_status": "Savings-account or bond holdings; the unknown/no-account category does not distinguish the two.",
    "employment": "Length of time in the applicant's current employment.",
    "installment_commitment": "Dataset code for installment burden relative to disposable income; the code is not a measured percentage.",
    "other_parties": "Whether the application has another debtor, a co-applicant, or a guarantor.",
    "housing": "Recorded housing arrangement: rented, owned, or provided free of charge.",
    "property_magnitude": "Recorded property category; unknown/no-property does not establish which of these applies.",
    "other_payment_plans": "Other installment arrangements through a bank or store.",
    "existing_credits": "Number of existing credits at this bank.",
    "num_dependents": "Number of people for whom the applicant provides financial maintenance.",
    "residence_since": "Recorded time at the current residence, retained in the dataset's units.",
    "personal_status": "The original dataset's combined sex and marital-status category.",
    "job": "Occupation category recorded in the original dataset.",
    "own_telephone": "Whether a telephone is registered under the applicant's name.",
    "foreign_worker": "The original dataset's foreign-worker category.",
}
FACTOR_CATEGORY_LABELS = {
    **CATEGORY_LABELS,
    "personal_status": {
        "A91": "Male: divorced / separated", "A92": "Female: divorced / separated / married",
        "A93": "Male: single", "A94": "Male: married / widowed", "A95": "Female: single",
    },
    "job": {
        "A171": "Unemployed / unskilled, non-resident", "A172": "Unskilled, resident",
        "A173": "Skilled employee / official",
        "A174": "Management / self-employed / highly qualified employee / officer",
    },
    "own_telephone": {"A191": "None", "A192": "Registered under applicant's name"},
    "foreign_worker": {"A201": "Yes", "A202": "No"},
}


def contributing_factors_for_display(pred: Prediction) -> tuple[list, str | None]:
    """Extend reproducible legacy explanations without changing stored evidence."""
    stored = list(pred.top_factors[:FACTOR_LIMIT])
    if not stored or pred.is_gold or len(stored) >= FACTOR_LIMIT:
        return stored, None
    unavailable = (
        f"Stored factors only: {len(stored)} available. Additional contributions "
        "could not be reproduced from the current local model."
    )
    try:
        from loopledger import model
        current = model.predict(pred.features, case_id=pred.case_id)
        matches = (
            isinstance(current, Prediction)
            and current.decision == pred.decision
            and math.isclose(current.confidence, pred.confidence, rel_tol=0, abs_tol=1e-6)
            and [tuple(item) for item in current.top_factors[:len(stored)]] == [tuple(item) for item in stored]
            and len(current.top_factors) >= FACTOR_LIMIT
        )
        if matches:
            return list(current.top_factors[:FACTOR_LIMIT]), (
                "Additional factors recomputed from the local model after matching the stored "
                "recommendation, confidence and contributions. Original audit records are unchanged."
            )
    except Exception:
        # Missing files, incomplete legacy inputs, or incompatible artifacts must
        # never make the saved application or the review form unavailable.
        pass
    return stored, unavailable


def factor_display_details(name: str, value: float, features: dict) -> tuple[str, str]:
    """Explain only the named public model input, including its encoded category."""
    encoded_category = None
    field = name
    numeric = name.startswith("num__")
    if numeric:
        field = name.removeprefix("num__")
    elif name.startswith("cat__"):
        encoded = name.removeprefix("cat__")
        field, _, encoded_category = encoded.rpartition("_")

    label = FACTOR_LABELS.get(field, name)
    description = FACTOR_DESCRIPTIONS.get(field, "No field description available for this recorded factor.")
    if field in FACTOR_LABELS:
        raw = features.get(field)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            raw_text = "Not provided"
        elif field in FACTOR_CATEGORY_LABELS:
            raw_text = FACTOR_CATEGORY_LABELS[field].get(str(raw), f"Unknown category: {raw}")
        else:
            raw_text = str(raw)
        description += f" Recorded application value: {raw_text}."
    if encoded_category:
        category = FACTOR_CATEGORY_LABELS.get(field, {}).get(
            encoded_category, f"Unknown category: {encoded_category}",
        )
        label += f" · {category}"
        description += f" Encoded category: {category}. This term uses a 0/1 indicator for that category."
    elif numeric:
        description += " This numerical input is standardized before its model contribution is calculated."
    direction = "toward rejection" if value > 0 else ("toward approval" if value < 0 else "no contribution")
    description += f" The contribution shown is {value:+.4f} log-odds ({direction}), not a probability or a causal effect."
    # Plotly uses HTML in labels/tooltips. Escape all source values before adding
    # our own line breaks, so a stored value cannot inject tooltip markup.
    label_html = "<br>".join(escape(line) for line in wrap(label, width=34))
    description_html = "<br>".join(escape(line) for line in wrap(description, width=68))
    return label_html, description_html


def application_detail_value(field: str, value) -> str:
    """Keep absent data distinct from explicit zero, none, and unknown categories."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return "Not provided"
    if field in CATEGORY_LABELS:
        return CATEGORY_LABELS[field].get(str(value), f"Unknown category: {value}")
    return str(value)


def render_application_details(features: dict) -> None:
    """Show the public financial fields needed to assess the recommendation."""
    for column, (heading, fields) in zip(st.columns(2), APPLICATION_DETAIL_GROUPS):
        with column:
            with st.container(border=True):
                st.markdown(f"#### {heading}")
                for field, label in fields:
                    st.caption(label)
                    st.text(application_detail_value(field, features.get(field)))
    st.caption("Account and savings bands use the dataset's original DM units.")


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


def public_case_id(case_id: str) -> str:
    """Use the same opaque display identifier for every persisted application."""
    return "APP-" + hashlib.sha256(case_id.encode()).hexdigest()[:12]


def render_prediction(pred: Prediction, *, database: bool = False) -> None:
    """Render only public fields; never pass a whole Prediction to the UI."""
    st.subheader(f"Application {public_case_id(pred.case_id) if database else pred.case_id}")
    if pred.is_gold:
        st.warning("GOLD CASE — visible demo test. Expected answer remains backend-only.")
    columns = st.columns(3)
    for column, feature in zip(columns, FEATURE_LABELS):
        value = pred.features.get(feature)
        display = "Not provided" if value is None else (f"{value:,}" if isinstance(value, (int, float)) else str(value))
        column.metric(FEATURE_LABELS[feature], display)
    st.caption("Loan amounts use dataset/demo units; no currency has been assigned.")
    render_application_details(pred.features)
    if database:
        details = {
            key: pred.features[key] for key in (
                "identity_verified", "extra_proof", "authorized_exception", "document_amount",
                "fraud_confirmed", "policy_checks_passed", "scenario",
            ) if key in pred.features
        }
        if details:
            st.markdown("#### Application evidence")
            for key, value in details.items():
                st.text(f"{key.replace('_', ' ').capitalize()}: {value}")

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
        factors, note = contributing_factors_for_display(pred)
        if not factors:
            st.info("No feature contributions were provided for this application.")
            return
        names, values = zip(*factors)
        details = [factor_display_details(name, value, pred.features) for name, value in factors]
        figure = go.Figure(
            go.Bar(
                x=list(values),
                y=[label for label, _ in details],
                orientation="h",
                marker_color=["#dc2626" if value > 0 else ("#16a34a" if value < 0 else "#94a3b8") for value in values],
                customdata=[[description, escape(name)] for name, (_, description) in zip(names, details)],
                hovertemplate="<b>%{y}</b><br>%{customdata[0]}<br><br>Contribution: %{x:+.4f} log-odds<br>Model field: %{customdata[1]}<extra></extra>",
            )
        )
        figure.add_vline(x=0, line_color="#94a3b8", line_width=1)
        figure.update_layout(
            height=max(300, 52 * len(factors)),
            margin=dict(l=0, r=20, t=10, b=10),
            xaxis_title="Contribution toward rejection",
            yaxis=dict(autorange="reversed"),
            showlegend=False,
            hoverlabel=dict(align="left"),
        )
        st.plotly_chart(figure, width="stretch", key="rq_factors")
        if note:
            st.caption(note)
        st.caption(
            ("Stored contributions; the local logistic model uses log-odds contributions, not SHAP. "
             if database else "Illustrative values, not measured SHAP output. ")
            + "Positive → reject; negative → approve. Hover a bar for its meaning and application value. "
            "These contributions are not individual confidence scores."
        )


def render_review_form(pred: Prediction, *, database: bool = False) -> None:
    """Validate then call the selected sink; failed writes preserve the draft."""
    state = st.session_state
    display_id = public_case_id(pred.case_id) if database else pred.case_id
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
            key=f"rq_reason_{display_id}",
            placeholder="Explain your decision after reviewing the application.",
        )
        approve_column, reject_column = st.columns(2)
        approve = approve_column.form_submit_button(
            "Approve application", key=f"rq_approve_{display_id}", type="primary"
        )
        reject = reject_column.form_submit_button(
            "Reject application", key=f"rq_reject_{display_id}"
        )

    if not (approve or reject):
        return
    if not reviewer.strip():
        st.error("Enter the reviewer's name before submitting.")
        return
    if not reason.strip():
        st.error("Enter a reason before submitting.")
        return
    if not database and any(review.case_id == pred.case_id for review in state["rq_submitted_reviews"]):
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
        if database:
            from loopledger import ledger
            ledger.submit_review(action)
        else:
            submit_mock_review(action)
    except Exception:
        # A failed sink must not discard input or advance the selected case.
        st.error("Submission failed. Your input is preserved; please try again.")
        return

    if not database:
        state.setdefault("rq_reviewed_predictions", {})[pred.case_id] = pred
        state["rq_submitted_reviews"].append(action)
        state["rq_pending_reviews"] = [
            case for case in state["rq_pending_reviews"] if case.case_id != pred.case_id
        ]
    state["rq_success_message"] = (
        f"{'Database' if database else 'Mock'} review saved for {display_id}: "
        f"{action.action} "
        f"by {action.reviewer} ({action.seconds_spent:.1f}s)."
    )
    st.rerun()


def main() -> None:
    st.set_page_config(page_title="Review Queue | LoopLedger", page_icon="📋", layout="wide")
    state = st.session_state
    st.title("Review Queue")
    st.write("Review the application and AI recommendation, then record your own decision.")
    source = "Database records"
    st.button("Refresh queue", key="rq_refresh")
    try:
        from loopledger import ledger
        ledger.init_db()
        pending = ledger.get_pending_reviews()
    except Exception:
        st.error("Could not load the database review queue. Check the database connection and refresh.")
        return
    if message := state.pop("rq_success_message", None):
        st.success(message)

    st.metric("Pending applications", len(pending))
    if not pending:
        state.pop("rq_active_case_id", None)
        state.pop("rq_started_at", None)
        st.info("No pending applications. Run a batch or refresh after new applications are saved.")
        return

    queue_column, detail_column = st.columns([1, 3])
    cases = {public_case_id(case.case_id): case for case in pending}
    case_ids = list(cases)

    def case_label(display_id: str) -> str:
        return f"🟨 GOLD · {display_id}" if cases[display_id].is_gold else display_id

    # Repair stale selection before constructing its widget, never after it.
    if state.get("rq_case_selector") not in case_ids:
        state["rq_case_selector"] = case_ids[0]
    with queue_column:
        st.subheader("Pending queue")
        selected_id = st.selectbox("Choose an application", case_ids, format_func=case_label, key="rq_case_selector")
        st.caption("Approve or reject the application itself, regardless of the AI's suggestion.")

    if state.get("rq_active_case_id") != selected_id or state.get("rq_active_source") != source:
        state["rq_active_case_id"] = selected_id
        state["rq_active_source"] = source
        state["rq_started_at"] = time.perf_counter()
    selected_case = cases[selected_id]
    with detail_column:
        render_prediction(selected_case, database=True)
        render_review_form(selected_case, database=True)


if __name__ == "__main__":
    main()
