# Review Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the user-approved mock review workflow in `pages/2_Review_Queue.py`.

**Architecture:** Keep the five mock `Prediction` fixtures and page helpers in the requested page. Use existing shared dataclasses unchanged. Store mock queue and submissions in namespaced Streamlit session state; never call the database or imply persistence.

**Tech Stack:** Python, Streamlit, Plotly; pytest and Streamlit AppTest for verification.

**Spec:** `C_前端开发执行建议.md`, section 3, plus the user's approved five-case proposal in this conversation.

## Global Constraints

- Edit the requested page in the user's current checkout; preserve existing edits to `loopledger/schemas.py` and `loopledger/__init__.py`.
- Fixtures: C-001 reject/0.62, C-002 approve/0.66, C-003 approve/0.92, C-004 reject/0.69, C-005 approve/0.94 with hidden gold answer reject.
- Explicit mock mode; no SQLite writes, model calls, or gold labels/answers in the review UI.
- Approve and reject require nonblank reviewer and reason. Modify stays disabled until its contract is defined.
- Timer survives same-case reruns, resets when selection changes, and is retained after validation or submit failure.
- Successful submission emits a real ReviewAction, removes only that case, and retains feedback after rerun. Empty queue remains usable.
- No commit or push is part of this request.

## Review Focus

- Gold metadata accidentally exposed through generic object rendering or chart data.
- Streamlit reruns reseeding completed cases or restarting the current timer.
- Validation or persistence failure clearing user input or advancing the queue.
- Two submissions for a completed case or stale selection after removal.
- Form/widget state updates after widget construction causing Streamlit exceptions.

### Task 1: Mock review workflow

**Files:**
- Modify: `pages/2_Review_Queue.py`
- Create: `tests/test_review_queue.py`

**Interfaces:**
- Consumes: existing `Prediction` and `ReviewAction` dataclasses.
- Produces: `make_mock_pending_reviews() -> list[Prediction]`, `submit_mock_review(action: ReviewAction) -> None`, and a renderable Streamlit review page.

- [x] Write AppTest cases for case selection and hidden metadata; blank inputs; approve/reject; timer stability; submit failure; and queue exhaustion.
- [x] Run the tests against the placeholder page and confirm failures are due to missing UI behavior: 8 failures caused by absent page controls.
- [x] Implement the mock fixtures, session initialization, explicit public-field rendering, signed contribution chart, validated form, and successful queue transitions.
- [x] Run the complete pytest suite and check the requested page diff for whitespace errors: 8 passed; diff check passed.
- [x] Obtain an independent code review: no material findings; reviewer independently reproduced 8 passing tests. Browser loading and layout also verified using the standalone launch command.

## Verification and launch

From the repository root, using the temporary environment created for this task:

```bash
/tmp/synoptix-review-venv/bin/python -m pytest -q -p no:cacheprovider
/tmp/synoptix-review-venv/bin/python -m streamlit run pages/2_Review_Queue.py
```

Only Streamlit, Plotly, pytest, and their dependencies were installed in that environment. With the project dependencies installed in another environment, use that environment's `python -m streamlit run pages/2_Review_Queue.py` instead. No real ledger or model functionality is claimed.
