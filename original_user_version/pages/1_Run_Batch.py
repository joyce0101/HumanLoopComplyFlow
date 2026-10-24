"""Batch UI using A's predictions/gate and B's event persistence contracts."""

from dataclasses import asdict, replace
import importlib
import html
import json
import math
import random
import time
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

from loopledger import verification_ui

from loopledger.schemas import GateResult, Prediction


def _validate_batch_size(n: int) -> None:
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 200:
        raise ValueError("Choose between 1 and 200 applications.")


def _new_batch(n: int, batch_id: str, mode: str) -> dict:
    return {
        "batch_id": batch_id,
        "mode": mode,
        "requested": n,
        "rows": [],
        "pending_reviews": [],
        "decisions": [],
    }


def _record_prediction(result: dict, pred: Prediction, gate: GateResult) -> None:
    result["decisions"].append((pred, gate))
    if gate.needs_review:
        routing = "Manual review"
        result["pending_reviews"].append(pred)
    else:
        routing = "Auto approve" if pred.decision == "approve" else "Auto reject"
    result["rows"].append({
        "Case": pred.case_id,
        "Loan amount": pred.features["credit_amount"],
        "Gold Case": "GOLD" if pred.is_gold else "Normal",
        "AI decision": pred.decision,
        "Confidence": f"{pred.confidence:.0%}",
        "Routing": routing,
        "Reasons": "; ".join(gate.reasons) or "No review rule triggered",
        "Error": "",
    })


def run_mock_batch(n: int, batch_id: str) -> dict:
    """Produce scripted demo decisions without touching session state or SQL."""
    _validate_batch_size(n)
    result = _new_batch(n, batch_id, "Mock demo")
    # Fixed patterns make frontend behavior reproducible. These are not model
    # outputs or validated lending rules. Positive factors point toward reject.
    patterns = [
        (2500, 12, 40, "approve", 0.93, -0.30),
        (6000, 36, 48, "reject", 0.87, 0.35),
        (4000, 24, 30, "approve", 0.64, -0.12),
        (18000, 48, 45, "reject", 0.88, 0.40),
    ]
    for index in range(n):
        amount, duration, age, decision, confidence, contribution = patterns[index % 4]
        pred = Prediction(
            case_id=f"{batch_id}-{index + 1:04d}",
            features={"credit_amount": amount, "duration": duration, "age": age},
            decision=decision,
            confidence=confidence,
            top_factors=[
                ("credit_amount", contribution),
                ("duration", contribution / 2),
                ("age", -contribution / 3),
            ],
        )
        reasons = []
        if confidence < 0.70:
            reasons.append("Low confidence (< 0.70)")
        if amount > 15000:
            reasons.append("High amount (> 15000 demo units)")
        _record_prediction(result, pred, GateResult(bool(reasons), reasons))
    return result


def run_model_batch(
    n: int,
    batch_id: str,
    *,
    model_path: str | Path | None = None,
    identity_verified: bool = False,
) -> dict:
    """Use A's shared prediction/gate contracts; do not train, enqueue, or persist."""
    _validate_batch_size(n)
    model = importlib.import_module("loopledger.model")
    gate = importlib.import_module("loopledger.gate")

    artifact = Path(model_path) if model_path is not None else Path(model.MODEL_FILE)
    if not artifact.is_file():
        raise FileNotFoundError(
            "No trained model is available. Run `python -m loopledger.model --train` "
            "before running a batch."
        )
    result = _new_batch(n, batch_id, "Model preview")
    samples = model.sample_cases(n)
    for index, features in enumerate(samples):
        case_id = f"{batch_id}-{index + 1:04d}"
        application = {
            **features,
            "identity_verified": identity_verified,
        }
        try:
            raw_prediction = model.predict(application, case_id=case_id, model_path=artifact)
            if not isinstance(raw_prediction, Prediction):
                raise ValueError("Model must return a shared Prediction object.")
            if raw_prediction.case_id != case_id:
                raise ValueError("Model returned a different application ID.")
            confidence = float(raw_prediction.confidence)
            decision = raw_prediction.decision
            if decision not in ("approve", "reject") or not math.isfinite(confidence):
                raise ValueError("Model returned an invalid recommendation or confidence.")
            if not 0 <= confidence <= 1:
                raise ValueError("Model confidence must be between 0 and 1.")
            factors = [
                (name, float(value))
                for name, value in raw_prediction.top_factors
            ]
            if any(not math.isfinite(value) for _, value in factors):
                raise ValueError("Model returned a nonfinite feature contribution.")
            pred = replace(raw_prediction, confidence=confidence, top_factors=factors)
            raw_gate = gate.check(raw_prediction)
            if not isinstance(raw_gate, GateResult):
                raise ValueError("Risk gate must return a shared GateResult object.")
            needs_review = raw_gate.needs_review
            reasons = raw_gate.reasons
            if (
                not isinstance(needs_review, bool)
                or not isinstance(reasons, list)
                or any(not isinstance(reason, str) for reason in reasons)
            ):
                raise ValueError("Risk gate returned an invalid routing result.")
            _record_prediction(result, pred, GateResult(needs_review, reasons))
        except Exception as error:
            # Keep the failed request visible, but never turn it into an auto
            # decision or a fabricated successful prediction.
            result["rows"].append({
                "Case": case_id,
                "Loan amount": features.get("credit_amount"),
                "AI decision": "—",
                "Confidence": "—",
                "Routing": "Failed",
                "Reasons": "Not routed",
                "Error": f"{type(error).__name__}: {error}",
            })
    return result


def run_mixed_batch(n: int, batch_id: str, *, model_path=None,
                    identity_verified: bool = False, gold_ratio: float = 0.10) -> dict:
    """Keep batch total n and randomly mix 10% Gold Cases into model predictions."""
    _validate_batch_size(n)
    if not 0 <= gold_ratio <= 1:
        raise ValueError("gold_ratio must be between 0 and 1")
    n_gold = int(n * gold_ratio + 0.5)
    n_normal = n - n_gold
    result = (run_model_batch(n_normal, batch_id, model_path=model_path,
                              identity_verified=identity_verified)
              if n_normal else _new_batch(n, batch_id, "Model preview"))
    result["requested"] = n
    if n_gold:
        gold = importlib.import_module("loopledger.gold")
        gate = importlib.import_module("loopledger.gate")
        templates = gold.make_gold_cases(6)
        for i in range(n_gold):
            pred = replace(templates[i % len(templates)],
                           case_id=f"{batch_id}-C-{i + 1:04d}")
            _record_prediction(result, pred, gate.check(pred))
    rng = random.Random(batch_id)
    rng.shuffle(result["rows"])
    rng.shuffle(result["decisions"])
    rng.shuffle(result["pending_reviews"])
    result["gold_count"], result["regular_count"] = n_gold, n_normal
    return result


def persist_model_batch(result: dict) -> dict:
    """Save predictions then routing; a missing gate leaves a pending case.

    The two ledger calls are separate transactions. Never retry a prediction
    automatically after a gate failure or claim that an automatic route saved.
    """
    ledger = importlib.import_module("loopledger.ledger")
    ledger.init_db()
    result["mode"] = "Model + database"
    result["pending_reviews"] = []
    rows = {row["Case"]: row for row in result["rows"]}
    for pred, gate in result["decisions"]:
        row = rows[pred.case_id]
        try:
            ledger.log_event("prediction", asdict(pred))
        except Exception as error:
            row.update({"Routing": "Failed", "Persistence": "Not saved", "Error": str(error)})
            continue
        try:
            ledger.log_event("gate", {"case_id": pred.case_id, **asdict(gate)})
        except Exception as error:
            row.update({
                "Routing": "Manual review", "Persistence": "Prediction saved; gate failed",
                "Reasons": "Routing was not saved. Application remains pending for manual review.",
                "Error": str(error),
            })
            result["pending_reviews"].append(pred)
        else:
            row["Persistence"] = "Saved"
            if gate.needs_review:
                result["pending_reviews"].append(pred)
    return result


def render_batch(result: dict) -> None:
    st.subheader("Last completed batch")
    st.caption(
        f"{result['mode']} · Batch {result['batch_id']} · "
        f"{result['requested']} applications requested. Counts below are for this batch only."
    )
    rows = result["rows"]
    counts = pd.Series([row["Routing"] for row in rows]).value_counts()
    failed = int(counts.get("Failed", 0))
    values = {
        "Processed": len(rows) - failed,
        "Auto-approve": int(counts.get("Auto approve", 0)),
        "Auto-reject": int(counts.get("Auto reject", 0)),
        "Needs review": int(counts.get("Manual review", 0)),
        "Failed": failed,
    }
    for column, (label, value) in zip(st.columns(5), values.items()):
        column.metric(label, value)
    if "gold_count" in result:
        st.caption("Batch mix: {} model cases + {} visible Gold Cases.".format(
            result["regular_count"], result["gold_count"]))
    if failed:
        st.warning(f"{failed} application(s) failed. Check the Error column before retrying.")
    if result["mode"] == "Mock demo":
        st.info(
            f"{values['Needs review']} mock applications were added to Review Queue "
            "in this app session. Existing pending and completed reviews were preserved. "
            "Opening another browser tab starts a separate session."
        )
    elif result["mode"] == "Model + database":
        st.info(
            "Saved applications are available in Review Queue, "
            "including after a browser refresh. Automatic routing records eligibility; "
            "this prototype does not execute loan transactions."
        )
        if any(row.get("Error") and row["Routing"] != "Failed" for row in rows):
            st.warning("Some routing events could not be saved. These applications remain pending; inspect the Error column.")
    else:
        st.info(
            "Preview only: routing shows eligibility, not executed loan decisions. "
            "These results were not added to Review Queue or saved to the database."
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def show_reviewer_verification_status() -> None:
    """Live browser countdown; backend authentication remains authoritative."""
    import streamlit.components.v1 as components

    reviewer = verification_ui.authenticated_reviewer()
    grant = st.session_state.get("vr_workspace_pass", {})
    valid = verification_ui.workspace_unlocked()
    remaining = max(0, int(grant.get("expires_at_epoch", 0) - time.time())) if valid else 0
    # A browser-side clock runs even when Streamlit is idle. performance.now()
    # measures elapsed time, avoiding clock differences between browser/server.
    reviewer_label = html.escape(str(reviewer or "unknown"))
    initial = json.dumps(remaining)
    initial_status = "true" if valid else "false"
    components.html(f"""
      <style>
        html, body {{ margin: 0; background: transparent; font-family: sans-serif; }}
        #status {{ background: #173e2a; color: #b8f4cb; padding: 12px 16px;
                   border-radius: 7px; font-size: 14px; line-height: 22px; }}
        #status.expired {{ background: #491f27; color: #ffd3d8; }}
        #clock {{ font-variant-numeric: tabular-nums; }}
      </style>
      <div id="status" role="status" aria-live="off">
        <span id="message"></span>
      </div>
      <script>
        const initialSeconds = {initial};
        const initiallyValid = {initial_status};
        const startedAt = performance.now();
        const status = document.getElementById('status');
        const message = document.getElementById('message');
        function render() {{
          const elapsed = Math.floor((performance.now() - startedAt) / 1000);
          const remaining = Math.max(0, initialSeconds - elapsed);
          if (!initiallyValid || remaining === 0) {{
            status.classList.add('expired');
            message.textContent = '🔒 Reviewer verification expired. Reverify your face before continuing.';
          }} else {{
            const mm = String(Math.floor(remaining / 60)).padStart(2, '0');
            const ss = String(remaining % 60).padStart(2, '0');
            message.textContent = '✅ Reviewer face verified ({reviewer_label}) · time until next verification: ' + mm + ':' + ss;
          }}
        }}
        render();
        setInterval(render, 250);
      </script>
    """, height=52, scrolling=False)


def main() -> None:
    st.set_page_config(page_title="Run Batch | LoopLedger", page_icon="▶️", layout="wide")
    verification_ui.require_workspace_access()
    state = st.session_state
    st.title("Run Batch")
    st.write("Process a batch of demo loan applications and inspect which decisions need review.")
    st.caption("Applications and routing results are saved to the database.")
    st.caption(
        "Demo-only assumption: sampled applicants are treated as identity-verified "
        "for risk-routing tests. This is not evidence of real identity verification. "
        "Loan amounts use dataset units."
    )
    if state.get("rb_last_batch", {}).get("mode") not in (None, "Model + database"):
        state.pop("rb_last_batch", None)
        state.pop("rb_last_error", None)

    # A timed fragment inside st.form cannot reliably refresh independently.
    # Keep the status outside a form so the timer ticks once per second.
    n = st.slider("Number of applications", 1, 200, 50, key="rb_batch_size")
    show_reviewer_verification_status()
    identity_verified = True  # Demo-only applicant assumption; independent of reviewer face login
    run = st.button("Run batch", type="primary", key="rb_run_batch")

    if run and not verification_ui.workspace_unlocked():
        st.error("Reviewer face verification has expired. Verify again before running a batch.")
        st.stop()

    if run:
        batch_id = f"B-{uuid4().hex[:12]}"
        try:
            with st.spinner("Processing applications…"):
                result = persist_model_batch(
                    run_mixed_batch(n, batch_id, identity_verified=identity_verified)
                )
            state["rb_last_batch"] = result
            state.pop("rb_last_error", None)
        except Exception as error:
            state["rb_last_error"] = f"Batch could not be completed: {error}"

    if error := state.get("rb_last_error"):
        st.error(error)
        if "rb_last_batch" in state:
            st.caption("The results below belong to the previous completed batch.")
    if "rb_last_batch" in state:
        render_batch(state["rb_last_batch"])
    else:
        st.info("Choose a batch size and click Run batch to begin.")


if __name__ == "__main__":
    main()
