"""D deliverable: audit evidence package in Markdown and structured JSON.

Uses the team's original interface contracts. No claims of certified compliance.
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
    """Convert pandas/numpy-native scalars and NaN to valid JSON-compatible data."""
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_safe_json(v) for v in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        return _safe_json(value.item())
    return str(value)


def _as_percent(value: float | None) -> str:
    if value is None:
        return "N/A (no control cases)"
    return f"{float(value) * 100:.1f}%"


def build_report_json() -> dict:
    """Return report snapshot as JSON-serialisable Python dict."""
    events = get_all_events()
    chain_ok, broken_id = verify_chain()
    reviewer_df = reviewer_stats()
    reviewers = _safe_json(reviewer_df.to_dict(orient="records"))
    stats = _safe_json(system_stats())
    event_counts = dict(Counter(str(evt.get("event_type", "unknown")) for evt in events))

    ledger_tip_hash = events[-1]["hash"] if events else None
    canonical = json.dumps({"stats": stats, "reviewers": reviewers,
                            "event_counts": event_counts, "tip_hash": ledger_tip_hash,
                            "chain_ok": chain_ok, "broken_id": broken_id},
                           sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    report_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return {
        "project": "LoopLedger",
        "report_id": report_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_origin": "Local SQLite ledger snapshot via B's interfaces; records may include dataset model outputs, manually seeded applications and synthetic controls. Historical provenance is not independently verified.",
        "system_stats": stats,
        "reviewer_metrics": reviewers,
        "total_events": len(events),
        "event_counts": event_counts,
        "integrity": {
            "chain_intact": chain_ok,
            "first_broken_event_id": broken_id,
            "tip_hash": ledger_tip_hash,
            "scope": "Local demo SQLite audit chain (not immutable or independently anchored)",
        },
        "regulatory_mapping": COMPLIANCE_MAPPING,
        "methodology": {
            "override_rate": "Share of reviews where human action differs from displayed AI advice; 'modify' counts as override",
            "gold_catch_rate": "Correct actions on deliberately inverted synthetic controls divided by reviewed controls; null when none",
            "avg_seconds": "Arithmetic mean seconds spent reviewing cases, measured or submitted by UI",
            "short_reason_rate": "Share of review reasons under 12 characters (prototype proxy, not semantic quality)",
            "flag": "Illustrative heuristic, not individual performance assessment",
            "rate_unit": "Fractions from 0 to 1 in JSON; shown as percentages in Markdown",
        },
        "limitations": [
            "Prototype with connected model, ledger and review interfaces; not a validated lending system.",
            "The batch page can use a German Credit logistic model and log-odds contributions, not SHAP. This snapshot does not independently establish the origin of every stored application.",
            "Synthetic control answers follow demo policies, not expert ground truth.",
            "Risk-gate thresholds are illustrative, not validated lending criteria.",
            "Hash chains detect simple event edits, but an attacker with database write access can reconstruct them.",
            "Human oversight metrics are proxies and do not prove an individual reviewer or system is effective.",
            "No determination of EU AI Act applicability, regulatory compliance, or ISO certification is made.",
            "Report metrics are read sequentially, not from one atomic DB snapshot; do not use for production attestation.",
        ],
    }


def build_report() -> str:
    """Render Markdown with no side effects, using D-owned Jinja2 template."""
    data = build_report_json()
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["percent"] = _as_percent
    template = env.get_template("evidence_report.md.j2")
    return template.render(**data).strip() + "\n"
