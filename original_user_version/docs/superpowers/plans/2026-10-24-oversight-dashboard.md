# Oversight Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Display oversight indicators from actual mock-session reviews, with an explicit adapter for B's future metrics interfaces.

**Architecture:** Implement the dashboard and its session aggregation adapter in `pages/3_Oversight_Dashboard.py`. Preserve original predictions on successful review submission and archive successful mock batches so metrics do not guess historical AI decisions or count only the latest batch. Backend mode calls B's functions; no page SQL or automatic fallback.

**Tech Stack:** Python, Streamlit, pandas, Plotly, pytest/AppTest.

**Spec:** `C_前端开发执行建议.md` section 5 and `PLAN.md` section 3.

## Global Constraints

- Preserve A/B modules, schemas, app.py, and database. No commit/push.
- Session mode reads existing `rq_pending_reviews`, `rq_submitted_reviews`, `rq_reviewed_predictions`, `rb_mock_batches`, and the last mock batch for migration. Do not generate reviews or seed state on dashboard visits.
- Successful reviews retain their original Prediction only after the submit sink succeeds. Successful mock batches retain history; model previews never enter that history.
- System totals cover unique known mock case IDs. Separate auto approval and rejection; exclude preview rows and failed predictions.
- Match original predictions by case ID; unknown comparisons and absent gold tests produce missing rates, not zero.
- Override rate includes modify as an override. Gold catch rate covers reviewed, known, deliberately inverted binary controls. Short reasons are stripped strings under 12 characters, matching D's current methodology.
- Mean duration and charts use only finite nonnegative measurements. Invalid timing counts are disclosed.
- Explicit demo heuristics: fewer than 5 reviews, incomplete timing, or missing AI comparisons means insufficient data; red for mean <5 seconds, short reasons >=80%, or at least 3 gold checks with catch rate <50%; yellow for mean <15 seconds, short reasons >=40%, at least 5 comparisons with zero override, or at least 3 gold checks with catch rate <80%; otherwise no heuristic alert. No claim of proven effective oversight.
- Backend mode uses `metrics.system_stats()` and `metrics.reviewer_stats()`. Use optional `ledger.get_all_events()` for individual durations, accepting JSON strings or dict payloads. Aggregate means cannot substitute for a duration distribution.
- Missing or failed backend calls are errors, not successful empty metrics or a fallback to session records.

## Review Focus

- Loss of original predictions after a review makes overrides/gold metrics silently incorrect.
- Historical batches double-counted, or real preview rows mixed with mock statistics.
- Empty, unmatched, or invalid timing data displayed as a measured zero or a green quality judgment.
- Gold answers exposed in review UI or dashboard detail output.
- Backend errors/missing events misrepresented as successful data or fabricated distributions.

### Task 1: Dashboard and minimal session history

**Files:** Modify `pages/3_Oversight_Dashboard.py`; add minimal history retention to `pages/1_Run_Batch.py` and `pages/2_Review_Queue.py`; create `tests/test_oversight_dashboard.py`.

**Interfaces:** `build_session_snapshot(state) -> dict`, `load_backend_snapshot() -> dict`; snapshots contain system_stats, reviewer_stats DataFrame, durations DataFrame, and warnings.

- [x] Write tests for known hand-calculated reviewer rates/flags, missing comparisons/gold data, invalid duration, unique historical totals, and actual submit/batch history retention.
- [x] Write AppTest cases for empty state, charts, refresh, backend mode/error, event timing payload formats and no database writes.
- [x] Observe expected failures before implementation: 14 failures due to missing dashboard controls/aggregation and absent session-history retention.
- [x] Implement aggregation, backend adapter, public aggregate display, explicit heuristics, and history retention after successful operations.
- [x] Run the complete suite: 40 passed, including 14 dashboard tests. Scoped diff whitespace check passed.
- [x] Independent review: no important findings; reviewer reproduced all 14 dashboard tests. Browser verification: a real mock-form submission updated the dashboard to 5 known cases, 1 reviewed, 4 pending, 100% override, no gold measurement, and an insufficient-data status; both time charts rendered.

## Verification and limitations

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/synoptix-review-venv/bin/python -m pytest -q --tb=short -p no:cacheprovider
```

The existing multipage server at `http://127.0.0.1:8502` serves the dashboard. Use sidebar navigation in the same browser session to retain mock reviews. B's real metrics are still unimplemented: backend adaptation has contract tests using test doubles, not a claim of live database integration. No database writes or commit/push were performed.
