# LoopLedger — Poster-ready English content (connected prototype)

## Title

**LoopLedger**

*From Human-in-the-Loop to Evidence of Human Oversight*

## Problem

**A human approval click alone cannot establish meaningful oversight.** AI-assisted decisions may be accepted without sufficient scrutiny, and traditional approval records may provide too little context for an assurance review.

## Our solution

**Model recommendation → Risk gate → Saved human review → Oversight indicators → Hash-linked audit evidence → Report export**

1. **AI and gate:** A German Credit logistic-regression model produces a suggestion and log-odds contributing factors. A configurable demo policy routes selected cases to a reviewer.
2. **Human review:** Reviewers can approve, reject or mark **Modify / hold**, providing a reason; the action and recorded elapsed time are saved.
3. **Oversight indicators:** Mean review time, override rate, short-reason rate and synthetic gold-control catch rate support further investigation.
4. **Event integrity:** SHA-256 hashes link saved events. A local chain check can detect straightforward modifications to logged records.
5. **Portable evidence:** Streamlit's Compliance page exports Markdown and JSON summaries of saved case counts, reviewer indicators and chain status.

## Implemented technical stack

**Python · Streamlit · scikit-learn Logistic Regression · German Credit · Pandas · Plotly · SQLite · SHA-256 · Jinja2 · pytest**

The current implementation uses **logistic regression and feature contributions to log-odds**. XGBoost and SHAP were in the original proposal but are not part of the connected demo.

## Evaluation / demonstration

Use only observed results from a final test database. Replace the placeholders below **after** running the live or seeded demo:

| Measure | Verified demo value |
|---|---|
| Number of stored applications | [read from exported `system_stats.total`] |
| Automatically approved / rejected | [read both counts] |
| Completed / pending reviews | [read both counts] |
| Synthetic gold-control catch rates | [read from `reviewer_metrics`, state sample sizes] |
| Clean event-chain verification | [show PASS on clean disposable DB] |
| Tampered-copy verification | [show FAIL and first broken event ID] |

**A repeatable seeded demonstration** can show contrasting behavior of a careful synthetic reviewer and a rubber-stamp synthetic reviewer; this is not a performance evaluation of real people. Use the B demo scripts, and do not mix synthetic seed data with claims about model performance.

## Assurance mapping and limits

Potential supporting evidence for **EU AI Act Article 12** (logs), **Article 13** (transparency), **Article 14** (human oversight), and **ISO/IEC 42001** (organizational AI management). This is **not** a legal compliance assessment or certification.

**Limits:** The local hash chain is not immutable against privileged rewrites; metrics are heuristic; the training data and thresholds do not establish real-world lending fairness or safety; raw event history and overall statistics are not read in one atomic transaction.

## Closing line

"LoopLedger turns an approval workflow into inspectable evidence—not a claim that the human or the AI was always right."
