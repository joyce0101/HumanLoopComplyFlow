"""Offline B acceptance run: binary reviews, metrics, reports and copy tampering.

Uses synthetic predictions, A's real gate and unchanged C/D backend consumers.
This validates B's persisted workflow, not C's session-only review submission.
"""

import argparse
import json
import math
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.demo_tamper import database_scope, make_tampered_copy


ROOT = Path(__file__).resolve().parents[1]


def _require(condition, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _write_bundle(directory: Path, name: str, bundle: dict) -> None:
    (directory / f"{name}.md").write_text(bundle["markdown"], encoding="utf-8")
    (directory / f"{name}.json").write_text(bundle["json_text"], encoding="utf-8")


def run_check(output_dir: Path | None = None) -> dict:
    """Run in a fresh artifact directory; preserve existing databases and files."""
    from loopledger import ledger, metrics
    from loopledger.schemas import ReviewAction
    from scripts.demo_reset import seed_oversight_demo

    if output_dir is None:
        directory = Path(tempfile.mkdtemp(prefix="loopledger-functional-"))
    else:
        directory = Path(output_dir).resolve()
        directory.mkdir(parents=True, exist_ok=False)
    clean = directory / "clean.db"
    damaged = directory / "tampered.db"
    steps = []
    with database_scope(clean):
        ledger.init_db()
        seed_oversight_demo(binary_only=True)
        _require(len(ledger.get_all_events()) == 44, "Functional seed must contain 44 events")
        pending = ledger.get_pending_reviews()
        _require(len(pending) == 2, "Functional seed must leave two pending reviews")
        steps.append("seed_with_real_risk_gate")

        actions = [
            ReviewAction(pred.case_id, "demo_judge", decision,
                         "Checked the application and supporting evidence.", 35.0)
            for pred, decision in zip(pending, ("approve", "reject"))
        ]
        for action in actions:
            ledger.submit_review(action)
        _require(not ledger.get_pending_reviews(), "Completed reviews must leave the queue")
        _require(len(ledger.get_all_events()) == 46, "Each successful review must append one event")
        steps.append("approve_and_reject_pending_cases")
        try:
            ledger.submit_review(actions[0])
        except ValueError:
            pass
        else:
            raise RuntimeError("Duplicate review was accepted")
        _require(len(ledger.get_all_events()) == 46, "Duplicate review must not append evidence")
        _require(all(event["payload"]["action"] in ("approve", "reject")
                     for event in ledger.get_all_events() if event["event_type"] == "review"),
                 "Functional check must not depend on modify")
        steps.append("reject_duplicate_submission")

        stats = metrics.system_stats()
        _require(stats == {
            "total": 16, "auto_approved": 1, "auto_rejected": 1,
            "sent_to_review": 14, "reviewed": 14, "pending": 0,
        }, "System counts do not match completed reviews")
        reviewers = metrics.reviewer_stats().set_index("reviewer")
        _require(reviewers.loc["careful_reviewer", "flag"] == "no_alert", "Careful fixture has an unexpected flag")
        _require(reviewers.loc["rubber_stamp", "flag"] == "review_signals", "Rubber-stamp fixture has an unexpected flag")
        dashboard = runpy.run_path(str(ROOT / "pages/3_Oversight_Dashboard.py"), run_name="b_functional_dashboard")
        snapshot = dashboard["load_backend_snapshot"]()
        _require(snapshot["system_stats"] == stats, "C dashboard backend counts differ")
        _require(len(snapshot["durations"]) == 14, "Dashboard must receive one duration per persisted review")
        steps.append("metrics_and_dashboard_backend")

        compliance = runpy.run_path(str(ROOT / "pages/4_Compliance.py"), run_name="b_functional_compliance")
        _require(compliance["verify_chain_for_source"]("Backend interfaces", None) == (True, None),
                 "Clean chain verification must pass")
        clean_bundle = compliance["build_export_bundle"](
            "Backend interfaces", {"status": "passed", "intact": True, "broken_id": None},
        )
        _require(json.loads(clean_bundle["json_text"])["system_stats"] == stats,
                 "Export must include persisted system statistics")
        _write_bundle(directory, "clean-report", clean_bundle)
        steps.append("clean_chain_and_evidence_download")

        tamper = make_tampered_copy(clean, damaged, 10)
        with database_scope(damaged):
            _require(compliance["verify_chain_for_source"]("Backend interfaces", None) == (False, 10),
                     "C chain interface must locate the tampered event")
            damaged_bundle = compliance["build_export_bundle"](
                "Backend interfaces", {"status": "inconsistent", "intact": False, "broken_id": 10},
            )
            _require("FAIL" in damaged_bundle["markdown"], "Damaged report must clearly report FAIL")
            _write_bundle(directory, "tampered-report", damaged_bundle)
        steps.append("tampered_copy_detected_at_10")

        _require(ledger.verify_chain() == (True, None), "Returning to the source must restore a clean check")
        _require(metrics.system_stats() == stats, "Copy tampering must not affect source cases")
        steps.append("return_to_clean_database")
        summary = {
            "status": "passed", "data_origin": "synthetic applications and predictions; A's real risk gate",
            "output_dir": str(directory), "clean_database": str(clean), "tampered_database": str(damaged),
            "events": 46, "system_stats": stats,
            "reviewer_metrics": metrics.reviewer_stats().to_dict(orient="records"),
            "tamper": tamper, "passed_steps": steps,
            "scope": "B persistence and unchanged C/D backend consumers; session-review persistence is not connected",
        }
    (directory / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return summary


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="New artifact directory; default is a unique temporary directory")
    parser.add_argument("--timeout-seconds", type=float, default=60, help="Maximum worker runtime (default: 60 seconds)")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive and finite")
    if args.worker:
        print(json.dumps(run_check(args.output_dir), allow_nan=False))
        return
    command = [sys.executable, str(Path(__file__).resolve()), "--worker"]
    if args.output_dir is not None:
        command.extend(["--output-dir", str(args.output_dir)])
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout_seconds)
    except subprocess.TimeoutExpired:
        parser.exit(1, f"Functional check timed out after {args.timeout_seconds:g} seconds; existing databases were not modified.\n")
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    if completed.returncode:
        raise SystemExit(completed.returncode)
    print(completed.stdout.strip())


if __name__ == "__main__":
    main()
