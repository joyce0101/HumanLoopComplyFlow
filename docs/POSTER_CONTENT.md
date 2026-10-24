# LoopLedger — Poster-ready English content

## Title

**LoopLedger**

*Beyond Human-in-the-Loop: Evidence for Meaningful AI Oversight*

## Problem

**A human approval click is not evidence of effective human oversight.** Routine approvals can conceal automation bias and weak review processes.

## Our approach

**Risk gate → Human review → Oversight indicators → Tamper-evident log → Evidence export**

1. **Risk gate:** Route selected AI recommendations for human review.
2. **Review workflow:** Record a human action, reason and time spent.
3. **Oversight metrics:** Track overrides, time and synthetic gold-control catches.
4. **Audit trail:** Chain event hashes and detect simple record tampering.
5. **Evidence package:** Export a structured Markdown/JSON summary and map evidence to regulatory themes.

## Technical stack

Python | Streamlit | SQLite | Jinja2 | SHA-256 | Pandas

**Demo note:** A/B/C are simulated offline; a trained German Credit model, XGBoost and SHAP are planned for team integration.

## Evaluation results (fill after actual demo)

- Number of demo cases: **[obtain from exported report]**
- Referred to human review: **[obtain from exported report]**
- Completed human reviews: **[obtain from exported report]**
- Synthetic gold catch rate: **[obtain from reviewer metrics]**
- Hash chain tamper-check: **[show PASS then FAIL after mock edit]**

**Do not insert fabricated success rates; label synthetic data.**

## Relevant assurance themes

EU AI Act Articles 12 (logging), 13 (transparency), 14 (human oversight) and ISO/IEC 42001 AI management practices. **Potential supporting evidence, not certified compliance.**

## Key message

"We don't just show that a human intervened; we provide evidence to assess what happened during human oversight."
