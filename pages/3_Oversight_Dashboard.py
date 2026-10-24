"""Oversight indicators for recorded mock-session reviews or B's metrics API.

Session aggregation is a frontend demo adapter, not the production metrics
implementation. This page neither writes SQL nor generates review outcomes.
"""

from collections import defaultdict
import importlib
import json
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


REVIEWER_COLUMNS = [
    "reviewer", "n_reviews", "avg_seconds", "override_rate", "gold_catch_rate",
    "short_reason_rate", "flag", "comparison_samples", "gold_samples",
]
STATUS_LABELS = {
    "no_alert": "🟢 No heuristic alert",
    "watch": "🟡 Watch",
    "review_signals": "🔴 Review signals",
    "insufficient_data": "⚪ Insufficient data",
}
FLAG_REASONS_HELP = """
These are review signals, not proof that a decision is wrong.

- **Short reasons:** `short_reason_rate_at_least_0.8` means at least 80% of
  reasons are short (red); `short_reason_rate_at_least_0.4` means at least 40%
  (yellow). Short means fewer than 12 characters after trimming outer whitespace.
- **No overrides:** `zero_overrides_across_5_or_more_reviews` means at least
  5 reviews can be compared with the AI and every decision followed it (yellow).
  It does not mean every application was approved.
- **Fast reviews:** `avg_seconds_below_5` means mean review time below 5 seconds
  (red); `avg_seconds_below_15` means below 15 seconds (yellow).
- **Gold checks:** `gold_catch_rate_below_0.5` means fewer than 50% of AI-error
  controls were correctly handled (red); `gold_catch_rate_below_0.8` means fewer
  than 80% (yellow). Both require at least 3 completed AI-error controls.
- **Insufficient data:** `fewer_than_5_reviews` means fewer than 5 reviews;
  `missing_or_invalid_timings` means timing is missing or invalid;
  `missing_ai_predictions` means an original AI decision is unavailable.
  These checks take priority over red/yellow signals. Otherwise red takes
  priority over yellow.
"""


def _valid_seconds(value) -> float | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def _demo_flag(row: dict, timed_reviews: int) -> str:
    if (
        row["n_reviews"] < 5
        or timed_reviews != row["n_reviews"]
        or row["comparison_samples"] != row["n_reviews"]
    ):
        return "insufficient_data"
    if (
        row["avg_seconds"] < 5
        or row["short_reason_rate"] >= 0.8
        or (row["gold_samples"] >= 3 and row["gold_catch_rate"] < 0.5)
    ):
        return "review_signals"
    if (
        row["avg_seconds"] < 15
        or row["short_reason_rate"] >= 0.4
        or (row["comparison_samples"] >= 5 and row["override_rate"] == 0)
        or (row["gold_samples"] >= 3 and row["gold_catch_rate"] < 0.8)
    ):
        return "watch"
    return "no_alert"


def build_session_snapshot(state) -> dict:
    """Use known originals and unique case IDs; do not mutate the session."""
    batches = list(state.get("rb_mock_batches", []))
    last_batch = state.get("rb_last_batch")
    if last_batch and last_batch.get("mode") == "Mock demo":
        batches.append(last_batch)
    originals = {}
    batch_rows = {}
    for batch in batches:
        if batch.get("mode") != "Mock demo":
            continue
        for pred in batch.get("pending_reviews", []):
            originals[pred.case_id] = pred
        for row in batch.get("rows", []):
            if row["Routing"] != "Failed":
                batch_rows[row["Case"]] = row
    pending = list(state.get("rq_pending_reviews", []))
    reviews = list(state.get("rq_submitted_reviews", []))
    originals.update({pred.case_id: pred for pred in pending})
    originals.update(state.get("rq_reviewed_predictions", {}))
    pending_ids = {pred.case_id for pred in pending}
    reviewed_ids = {review.case_id for review in reviews}
    routed_ids = {
        case_id for case_id, row in batch_rows.items() if row["Routing"] == "Manual review"
    } | pending_ids | reviewed_ids
    stats = {
        "total": len(set(batch_rows) | pending_ids | reviewed_ids),
        "auto_approved": sum(row["Routing"] == "Auto approve" for row in batch_rows.values()),
        "auto_rejected": sum(row["Routing"] == "Auto reject" for row in batch_rows.values()),
        "sent_to_review": len(routed_ids),
        "reviewed": len(reviewed_ids),
        "pending": len(pending_ids),
    }

    groups = defaultdict(list)
    for review in reviews:
        groups[review.reviewer].append(review)
    reviewer_rows, durations = [], []
    unmatched, invalid_timings = 0, 0
    for reviewer, actions in sorted(groups.items()):
        seconds, comparisons, gold_checks = [], [], []
        for action in actions:
            duration = _valid_seconds(action.seconds_spent)
            if duration is None:
                invalid_timings += 1
            else:
                seconds.append(duration)
                durations.append({"reviewer": reviewer, "seconds_spent": duration})
            pred = originals.get(action.case_id)
            if pred is None:
                unmatched += 1
                continue
            comparisons.append(action.action == "modify" or action.action != pred.decision)
            if (
                pred.is_gold
                and pred.gold_correct_decision in ("approve", "reject")
                and pred.decision != pred.gold_correct_decision
            ):
                gold_checks.append(action.action == pred.gold_correct_decision)
        row = {
            "reviewer": reviewer,
            "n_reviews": len(actions),
            "avg_seconds": sum(seconds) / len(seconds) if seconds else None,
            "override_rate": sum(comparisons) / len(comparisons) if comparisons else None,
            "gold_catch_rate": sum(gold_checks) / len(gold_checks) if gold_checks else None,
            "short_reason_rate": sum(len(action.reason.strip()) < 12 for action in actions) / len(actions),
            "comparison_samples": len(comparisons),
            "gold_samples": len(gold_checks),
        }
        row["flag"] = _demo_flag(row, len(seconds))
        reviewer_rows.append(row)
    warnings = []
    if unmatched:
        warnings.append(
            f"{unmatched} review(s) have no original AI prediction. "
            "Comparison rates use matched records only; unavailable rates remain blank."
        )
    if invalid_timings:
        warnings.append(
            f"{invalid_timings} review(s) have missing or invalid timing. "
            "Those measurements are excluded from averages and charts."
        )
    return {
        "system_stats": stats,
        "reviewer_stats": pd.DataFrame(reviewer_rows, columns=REVIEWER_COLUMNS),
        "durations": pd.DataFrame(durations, columns=["reviewer", "seconds_spent"]),
        "warnings": warnings,
    }


def load_backend_snapshot() -> dict:
    """Read B's functions; missing functions must not silently mean zero data."""
    metrics = importlib.import_module("loopledger.metrics")
    if not all(callable(getattr(metrics, name, None)) for name in ("system_stats", "reviewer_stats")):
        raise RuntimeError("Backend metrics are not available yet: system_stats() and reviewer_stats() are required.")
    stats = dict(metrics.system_stats())
    for key in ("total", "auto_approved", "sent_to_review", "reviewed", "pending"):
        value = float(stats[key])
        if not math.isfinite(value) or value < 0 or not value.is_integer():
            raise ValueError(f"Backend returned an invalid count for {key}.")
        stats[key] = int(value)
    stats.setdefault("auto_rejected", None)
    frame = metrics.reviewer_stats().copy()
    if not isinstance(frame, pd.DataFrame) or not set(REVIEWER_COLUMNS[:7]).issubset(frame.columns):
        raise ValueError("Backend reviewer metrics do not match the agreed table columns.")
    for column in ("n_reviews", "avg_seconds", "override_rate", "gold_catch_rate", "short_reason_rate"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        present = frame[column].dropna()
        if any(not math.isfinite(float(value)) or value < 0 for value in present):
            raise ValueError(f"Backend returned invalid values for {column}.")
        if column.endswith("_rate") and (present > 1).any():
            raise ValueError(f"Backend returned a rate outside 0–1 for {column}.")

    durations, warnings = [], []
    ledger = importlib.import_module("loopledger.ledger")
    if not callable(getattr(ledger, "get_all_events", None)):
        warnings.append("Review-level timing is not available from the backend; no duration distribution can be shown.")
    else:
        try:
            events = ledger.get_all_events()
            invalid = 0
            for event in events:
                if event.get("event_type") != "review":
                    continue
                try:
                    payload = event["payload"]
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    duration = _valid_seconds(payload.get("seconds_spent"))
                    reviewer = payload.get("reviewer")
                    if duration is None or not isinstance(reviewer, str) or not reviewer.strip():
                        invalid += 1
                        continue
                    durations.append({"reviewer": reviewer, "seconds_spent": duration})
                except (KeyError, TypeError, ValueError, AttributeError):
                    invalid += 1
            if invalid:
                warnings.append(f"{invalid} review event(s) lack usable reviewer/timing data and were excluded from the distribution.")
        except Exception as error:
            warnings.append(f"Could not load review-level timings: {error}")
    return {
        "system_stats": stats,
        "reviewer_stats": frame,
        "durations": pd.DataFrame(durations, columns=["reviewer", "seconds_spent"]),
        "warnings": warnings,
    }


def render_reviewers(frame: pd.DataFrame, durations: pd.DataFrame) -> None:
    for flag, message in (("review_signals", "Review signals"), ("watch", "Watch signals")):
        names = frame.loc[frame["flag"] == flag, "reviewer"].astype(str).tolist()
        if names:
            st.warning(f"{message}: {', '.join(names)}. Inspect the indicators and sample counts below.")
    display = frame.copy()
    for column in ("override_rate", "gold_catch_rate", "short_reason_rate"):
        display[column] = display[column].map(lambda value: "—" if pd.isna(value) else f"{value:.1%}")
    display["avg_seconds"] = display["avg_seconds"].map(lambda value: "—" if pd.isna(value) else f"{value:.1f}s")
    display["flag"] = display["flag"].map(lambda flag: STATUS_LABELS.get(flag, str(flag)))
    display = display.rename(columns={
        "reviewer": "Reviewer", "n_reviews": "Reviews", "avg_seconds": "Avg time",
        "override_rate": "Override rate", "gold_catch_rate": "Gold catch rate",
        "short_reason_rate": "Short reasons", "flag": "Status",
        "comparison_samples": "AI comparisons", "gold_samples": "Gold checks",
    })
    st.subheader("Reviewer oversight indicators")
    st.dataframe(
        display, hide_index=True, width="stretch",
        column_config={
            "flag_reasons": st.column_config.ListColumn(
                "Flag reasons", help=FLAG_REASONS_HELP,
            ),
        },
    )
    if "flag_reasons" in display.columns:
        st.caption("Hover over the Flag reasons column header to see reason-code definitions and thresholds.")
    st.caption("— means no usable measurement. Rates apply to available samples; a green status does not establish effective oversight.")

    means_column, distribution_column = st.columns(2)
    with means_column:
        st.subheader("Average review time")
        measured = frame.dropna(subset=["avg_seconds"])
        if measured.empty:
            st.info("No usable review timings yet.")
        else:
            figure = go.Figure(go.Bar(
                x=measured["avg_seconds"].tolist(), y=measured["reviewer"].tolist(),
                orientation="h", marker_color="#7c5cff",
                hovertemplate="%{y}: %{x:.1f}s<extra></extra>",
            ))
            figure.update_layout(height=320, xaxis_title="Mean seconds", margin=dict(l=0, r=10, t=10, b=10))
            st.plotly_chart(figure, width="stretch", key="od_mean_time")
    with distribution_column:
        st.subheader("Time spent per review")
        if durations.empty:
            st.info("No individual review timings are available; averages cannot form a distribution.")
        else:
            figure = go.Figure()
            for reviewer, rows in durations.groupby("reviewer"):
                figure.add_trace(go.Histogram(
                    x=rows["seconds_spent"].tolist(), name=str(reviewer), nbinsx=20, opacity=0.7,
                ))
            figure.update_layout(height=320, barmode="overlay", xaxis_title="Seconds", yaxis_title="Reviews", margin=dict(l=0, r=10, t=10, b=10))
            st.plotly_chart(figure, width="stretch", key="od_time_distribution")


def main() -> None:
    st.set_page_config(page_title="Oversight Dashboard | LoopLedger", page_icon="📊", layout="wide")
    st.title("Oversight Dashboard")
    st.write("Inspect review activity, AI overrides, control checks and time spent reviewing.")
    st.button("Refresh metrics", key="od_refresh")
    try:
        ledger = importlib.import_module("loopledger.ledger")
        if callable(getattr(ledger, "init_db", None)):
            ledger.init_db()
        snapshot = load_backend_snapshot()
    except Exception as error:
        st.error(f"Could not load oversight metrics: {error}")
        return
    for warning in snapshot["warnings"]:
        st.warning(warning)
    stats = snapshot["system_stats"]
    labels = {
        "total": "Total applications",
        "auto_approved": "Auto-approved", "auto_rejected": "Auto-rejected",
        "sent_to_review": "Sent for review", "reviewed": "Reviewed", "pending": "Pending",
    }
    for column, (key, label) in zip(st.columns(6), labels.items()):
        value = stats.get(key)
        column.metric(label, "—" if value is None else value)
    frame = snapshot["reviewer_stats"]
    if frame.empty:
        st.info("No completed reviews yet. Submit an application review in Review Queue, then return here.")
        return
    render_reviewers(frame, snapshot["durations"])


if __name__ == "__main__":
    main()
