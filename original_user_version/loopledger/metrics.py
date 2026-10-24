"""Read-only oversight indicators from persisted ledger data.

Rates are fractions, absent measurements are None, and flags are illustrative
signals rather than assessments of competence. See docs/OVERSIGHT_METRICS.md for the
denominators, sample requirements and integration contract.
"""

from collections import defaultdict
import json
import math

import pandas as pd

from . import ledger


MIN_REVIEWS = 5
MIN_GOLD_SAMPLES = 3
SHORT_REASON_CHARS = 12
REVIEWER_COLUMNS = [
    "reviewer", "n_reviews", "avg_seconds", "override_rate", "gold_catch_rate",
    "short_reason_rate", "flag", "comparison_samples", "gold_samples",
    "timed_samples", "flag_reasons",
]


def _seconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _flag(row: dict) -> tuple[str, list[str]]:
    incomplete = []
    if row["n_reviews"] < MIN_REVIEWS:
        incomplete.append("fewer_than_5_reviews")
    if row["timed_samples"] != row["n_reviews"]:
        incomplete.append("missing_or_invalid_timings")
    if row["comparison_samples"] != row["n_reviews"]:
        incomplete.append("missing_ai_predictions")
    if incomplete:
        return "insufficient_data", incomplete

    red, yellow = [], []
    if row["avg_seconds"] < 5:
        red.append("avg_seconds_below_5")
    elif row["avg_seconds"] < 15:
        yellow.append("avg_seconds_below_15")
    if row["short_reason_rate"] >= 0.8:
        red.append("short_reason_rate_at_least_0.8")
    elif row["short_reason_rate"] >= 0.4:
        yellow.append("short_reason_rate_at_least_0.4")
    if row["comparison_samples"] >= MIN_REVIEWS and row["override_rate"] == 0:
        yellow.append("zero_overrides_across_5_or_more_reviews")
    if row["gold_samples"] >= MIN_GOLD_SAMPLES:
        if row["gold_catch_rate"] < 0.5:
            red.append("gold_catch_rate_below_0.5")
        elif row["gold_catch_rate"] < 0.8:
            yellow.append("gold_catch_rate_below_0.8")
    if red:
        return "review_signals", red + yellow
    if yellow:
        return "watch", yellow
    return "no_alert", []


def reviewer_stats() -> "pd.DataFrame":
    """Aggregate completed review events against their preceding AI prediction.

    The first seven columns follow PLAN.md. Extra sample counts and reason codes
    support the existing dashboard and make warnings reviewable. Gold catch rate
    excludes correct-AI controls; only known AI-error probes test error detection.
    """
    originals, groups = {}, defaultdict(list)
    # One ordered read gives a consistent event snapshot. Match the original
    # available at review time, never a later prediction or mutable cases row.
    for event in ledger.get_all_events():
        payload = event["payload"]
        if event["event_type"] == "prediction":
            originals[payload["case_id"]] = payload
        elif event["event_type"] == "review":
            groups[payload["reviewer"]].append((payload, originals.get(payload["case_id"])))

    rows = []
    for reviewer, reviews in sorted(groups.items()):
        durations, overrides, gold_checks = [], [], []
        for action, pred in reviews:
            duration = _seconds(action.get("seconds_spent"))
            if duration is not None:
                durations.append(duration)
            if pred is None or pred.get("decision") not in ("approve", "reject"):
                continue
            overrides.append(action["action"] == "modify" or action["action"] != pred["decision"])
            correct = pred.get("gold_correct_decision")
            if (
                pred.get("is_gold") is True
                and correct in ("approve", "reject", "modify")
                and correct != pred["decision"]
            ):
                gold_checks.append(action["action"] == correct)
        row = {
            "reviewer": reviewer,
            "n_reviews": len(reviews),
            "avg_seconds": math.fsum(durations) / len(durations) if durations else None,
            "override_rate": sum(overrides) / len(overrides) if overrides else None,
            "gold_catch_rate": sum(gold_checks) / len(gold_checks) if gold_checks else None,
            "short_reason_rate": sum(
                len(action["reason"].strip()) < SHORT_REASON_CHARS for action, _ in reviews
            ) / len(reviews),
            "comparison_samples": len(overrides),
            "gold_samples": len(gold_checks),
            "timed_samples": len(durations),
        }
        row["flag"], row["flag_reasons"] = _flag(row)
        rows.append(row)
    frame = pd.DataFrame(rows, columns=REVIEWER_COLUMNS)
    # Keep Python None in exports, including mixed measured/unmeasured rows.
    # pandas otherwise coerces an absent rate to NaN, which is invalid strict JSON.
    for column in ("avg_seconds", "override_rate", "gold_catch_rate"):
        frame[column] = pd.Series([row[column] for row in rows], dtype=object)
    return frame


def system_stats() -> dict:
    """Count current cases, keeping automatic approvals and rejections separate.

    sent_to_review includes pending and completed manual cases. A newly stored
    prediction is pending until its gate routes it, following ledger fail-closed
    behavior. This function performs no initialization or business writes.
    """
    with ledger._connection() as connection:
        cases = connection.execute("SELECT status, prediction FROM cases").fetchall()
    stats = {
        "total": len(cases), "auto_approved": 0, "sent_to_review": 0,
        "reviewed": 0, "pending": 0, "auto_rejected": 0,
    }
    for case in cases:
        status = case["status"]
        if status == "auto":
            decision = json.loads(case["prediction"])["decision"]
            if decision not in ("approve", "reject"):
                raise ValueError("An automatic case has an invalid AI decision")
            stats["auto_approved" if decision == "approve" else "auto_rejected"] += 1
        elif status in ("pending", "reviewed"):
            stats[status] += 1
            stats["sent_to_review"] += 1
        else:
            raise ValueError(f"Unknown case status: {status!r}")
    return stats
