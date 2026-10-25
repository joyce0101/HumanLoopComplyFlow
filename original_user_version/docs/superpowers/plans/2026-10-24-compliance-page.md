# Compliance Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the user-requested fourth page in this order: four chain-check states, Markdown preview, Markdown/JSON downloads, loading/error handling and failure invalidation.

**Architecture:** Implement only `pages/4_Compliance.py` plus its tests. UI demo uses clearly marked synthetic responses and a small matching report fixture. Backend mode lazily calls B's `verify_chain()` and D's `build_report_json()` / `build_report()`; missing dependencies remain visible errors.

**Tech Stack:** Streamlit, Python standard library, pytest/AppTest.

**Spec:** The user's four-item checklist and `C_前端开发执行建议.md` section 6.

## Global Constraints

- Preserve A/B/D modules, report template, other pages, and database. No commit, push, SQL, or simulated database tampering.
- Chain state begins unchecked. A successful call yields passed or inconsistent; exceptions and malformed return values yield execution error.
- Explicit UI demo and Backend interfaces modes. Demo scenarios are response fixtures, never verification of the real database.
- Generate reports only after a completed check (pass or inconsistency). An inconsistent chain can still be exported as evidence with a FAIL result.
- Demo report Markdown and JSON derive from one fixture snapshot. Backend exports call the agreed D functions; report IDs and integrity must match the preceding check to reject changed/inconsistent outputs.
- Markdown preview is the exact downloadable Markdown. Both download buttons begin disabled and require a completely generated, valid bundle.
- Invalidate old preview and both downloads on new verification, source/scenario changes, generation failure, or stale integrity. Ordinary reruns and downloads do not regenerate evidence.
- JSON must be nonempty structured data serializable with allow_nan=False. Markdown must be nonblank. Reject partial exports.
- UI order: chain controls/status, report generation/preview, downloads. Use spinners for check/generation and retain clear actionable error text.

## Review Focus

- A demo pass being mistaken for real database verification.
- Old successful downloads remaining available after a failed retry or changed source.
- Inconsistent-chain evidence wrongly blocked or incorrectly labeled PASS.
- JSON/Markdown from differing backend snapshots offered together without detection.
- Missing B dependencies crashing the page before the user invokes backend functionality.

### Task 1: Chain check

- [ ] Test unchecked, passed, inconsistent and execution-error states and malformed backend results.
- [ ] Implement explicit source/scenario controls and deferred chain calls.

### Task 2: Report preview

- [ ] Test valid demo/backend bundles, exact preview text, empty or invalid output, and changed integrity/report IDs.
- [ ] Implement deferred report generation and Markdown preview.

### Task 3: Downloads

- [ ] Test initial disabled downloads, matching generated artifacts, and no regeneration during ordinary reruns.
- [ ] Implement Markdown / JSON download buttons with correct MIME types and source-labeled filenames.

### Task 4: Loading, errors, invalidation

- [ ] Test recheck, source/scenario switch, simulated generation error, backend failure and recovery.
- [ ] Add spinners and invalidate stale artifacts before attempts or context changes.
- [ ] Run the complete suite, independently review the final page, and verify browser behavior.

## Baseline findings

Before modifying this page, the full suite reported **38 passed, 2 failed**. Existing failures in `tests/test_run_batch.py`:

- `test_model_preview_uses_real_predictions_and_requires_explicit_identity_assumption`
- `test_model_preview_failure_is_a_failed_row_not_an_automatic_decision`

A now returns shared `Prediction` and `GateResult` objects and expects `case_id`, while the older batch adapter still uses dictionary fields and `decision_id`. These failures are outside this fourth-page change and must remain explicit in the final validation report.
