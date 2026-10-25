"""LoopLedger: read-only, structured and Markdown AI-oversight evidence exports.

The JSON and Markdown formats can be rendered from ONE in-memory report object.
Underlying B interfaces currently perform multiple separate database reads; this
module does not claim a single atomic SQLite transaction or regulatory compliance.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .compliance_mapping import COMPLIANCE_MAPPING
from .ledger import get_all_events, verify_chain
from .metrics import reviewer_stats, system_stats

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def _safe_json(value: Any) -> Any:
    """Convert pandas/NumPy values and non-finite floats to valid JSON values."""
    if isinstance(value, dict):
        return {str(key): _safe_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_safe_json(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        return _safe_json(value.item())
    return str(value)


def _as_percent(value: Any, missing: str = "N/A") -> str:
    """Display a 0..1 rate. Missing measurements never imply 0%."""
    if value is None:
        return missing
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return missing
    if not math.isfinite(rate):
        return missing
    if rate < 0 or rate > 1:
        raise ValueError(f"A rate must be between 0 and 1, received {rate!r}")
    return f"{rate * 100:.1f}%"


def _as_seconds(value: Any) -> str:
    """Represent absent/invalid timing without crashing Jinja templates."""
    if value is None:
        return "N/A"
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if not math.isfinite(seconds):
        return "N/A"
    if seconds < 0:
        raise ValueError(f"Review duration must not be negative: {seconds!r}")
    return f"{seconds:.2f}"


def build_report_json() -> dict:
    """Read B's interfaces once per report build; return a JSON-safe snapshot.

    CAUTION: calls to get_all_events, verify_chain, reviewer_stats and
    system_stats are separate reads. Another writer can change SQLite while
    this function runs. An atomic cross-module snapshot requires a future
    transaction-aware B API.
    """
    events = get_all_events()
    chain_ok, broken_id = verify_chain()
    reviewers = _safe_json(reviewer_stats().to_dict(orient="records"))
    stats = _safe_json(system_stats())
    event_counts = dict(Counter(str(event.get("event_type", "unknown")) for event in events))

    tip_hash = events[-1]["hash"] if events else None
    canonical = json.dumps(
        {
            "stats": stats,
            "reviewers": reviewers,
            "event_counts": event_counts,
            "tip_hash": tip_hash,
            "chain_ok": chain_ok,
            "broken_id": broken_id,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    report_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    report = {
        "project": "LoopLedger",
        "report_id": report_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_origin": (
            "Local SQLite ledger snapshot (non-atomic reads) via B's interfaces. "
            "The database may "
            "contain German Credit model predictions, seeded applications and "
            "synthetic controls; event provenance is not independently attested."
        ),
        "system_stats": stats,
        "reviewer_metrics": reviewers,
        "total_events": len(events),
        "event_counts": event_counts,
        "integrity": {
            "chain_intact": chain_ok,
            "first_broken_event_id": broken_id,
            "tip_hash": tip_hash,
            "scope": "Local SHA-256 event chain; not immutable or independently anchored",
        },
        "regulatory_mapping": COMPLIANCE_MAPPING,
        "methodology": {
            "override_rate": (
                "Number of matched reviews with an action different from the AI "
                "recommendation, including 'modify', divided by matched reviews. "
                "An override is not necessarily a correct decision."
            ),
            "gold_catch_rate": (
                "Among reviewed synthetic gold controls where the AI recommendation "
                "differs from the expected action, proportion for which the review "
                "action exactly matches that expected action (approve/reject/modify). "
                "Correct-AI controls are excluded. Null means no eligible controls."
            ),
            "avg_seconds": (
                "Arithmetic mean of usable nonnegative seconds_spent values "
                "recorded for a review, not verified attention time."
            ),
            "short_reason_rate": (
                "Share of submitted review reasons shorter than 12 characters "
                "after trimming whitespace; length is not a quality assessment."
            ),
            "flag": (
                "Illustrative heuristic: insufficient_data/watch/review_signals/" 
                "no_alert; not a competence or regulatory verdict."
            ),
            "rate_unit": "Fractions in JSON (0..1); percentages in Markdown; absent data is null/N/A.",
        },
        "limitations": [
            "Hackathon prototype, not an approved or validated lending system.",
            "The connected German Credit model is logistic regression with log-odds contributions, not XGBoost or SHAP.",
            "The stored database may mix model-generated and synthetic/seeded records; record provenance is not independently attested.",
            "Gold test answer keys follow synthetic demo policies, not expert ground truth.",
            "Risk-gate thresholds and oversight heuristics are illustrative and have not been calibrated for real lending.",
            "A hash chain detects straightforward edits to existing logged events but does not prevent privileged rewrites or prove the event history is complete.",
            "The event-chain check does not independently verify the separate cases table.",
            "Reviewer timings, overrides, gold checks and reason lengths are proxies, not proof of independent or effective human judgment.",
            "Neither legal applicability nor conformity with the EU AI Act or ISO/IEC 42001 is established.",
            "Underlying backend statistics and chain checks are read in separate transactions; this is not an atomic database snapshot.",
        ],
    }
    # Fail early rather than exporting invalid JSON with NaN/Infinity.
    json.dumps(report, ensure_ascii=False, allow_nan=False)
    return report


def render_report(data: dict) -> str:
    """Render an existing report object without performing any backend reads.

    Use this after build_report_json() to obtain matching JSON and Markdown:
      data = build_report_json()
      markdown = render_report(data)
    """
    if not isinstance(data, dict):
        raise TypeError("Report data must be a dictionary")
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["percent"] = _as_percent
    env.filters["seconds"] = _as_seconds
    template = env.get_template("evidence_report.md.j2")
    return template.render(**data).strip() + "\n"


def build_report() -> str:
    """Backward-compatible Markdown API expected by C's existing page/tests."""
    return render_report(build_report_json())


def build_report_bundle() -> tuple[dict, str]:
    """Generate JSON and Markdown from the same single in-memory report data."""
    report = build_report_json()
    return report, render_report(report)
