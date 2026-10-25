# LoopLedger — Compliance Mapping (D)

## Scope and status

LoopLedger is a **hackathon prototype** with a connected German Credit logistic-regression model, a risk gate, SQLite audit events, human review pages, oversight indicators and report exports. It does not make actual lending decisions. This document maps *potentially relevant evidence* to regulatory themes; it does not determine legal applicability, certify compliance, or provide legal advice.

| Source | Relevant expectation (summary) | LoopLedger supporting evidence | Remaining limitations |
|---|---|---|---|
| [EU AI Act Article 12](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-12) | Logging and traceability in applicable high-risk AI systems | Timestamped `prediction`, `gate`, `review` events and hash-chain consistency check | Local event log is not externally anchored; completeness, retention and access control are unverified |
| [EU AI Act Article 13](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-13) | Transparency and appropriate interpretation of AI outputs | AI recommendation, confidence and top logistic-regression log-odds contributions displayed in the Review Queue | These contributions are not SHAP, validated explanations or full instructions for use |
| [EU AI Act Article 14](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-14) | Effective oversight, intervention and mitigation of automation bias | Review decisions and reasons; elapsed time; override, short-reason and synthetic gold-control indicators | These are observational heuristics, not evidence that an individual truly or independently assessed the case |
| [ISO/IEC 42001:2023](https://webstore.iec.ch/en/publication/90574) | Organizational AI management and continuous improvement | Evidence report, event statistics, oversight monitoring dashboard | Organizational management-system effectiveness and conformity have not been assessed |

## What the evidence does and does not say

**Present:** Demonstration records for the cases that exist in the selected local database; a consistency check for observed audit events; reviewer metrics and a downloadable structured report.

**Not established:** Whether the event history is complete; whether reviewers are genuine, attentive or competent; whether model decisions are fair, accurate or lawful; whether any specific legal requirement applies or is satisfied.

The saved database can contain a mixture of real model-generated predictions and **synthetic fixtures**. A successful chain verification indicates internal consistency of observed events only. It does not prove an attacker with full database privileges has not replaced/recalculated the chain.

## Metric definitions

- **Override rate:** Proportion of matched reviews with an action differing from the model's advice; `modify` counts as an override. An override may be incorrect.
- **Gold catch rate:** Among reviewed synthetic controls **where the model's recommendation differs from the expected action**, proportion where the review action exactly equals that action (`approve`, `reject` or `modify`). Correct-AI controls are excluded; no eligible sample is `null`/N/A, not 0%.
- **Average review time:** Average recorded duration over usable timings. It may include time away from the page and does not establish attention.
- **Short-reason rate:** Share of submitted review reasons shorter than 12 characters after trimming. This is not natural-language quality assessment.
- **Heuristic flag:** `insufficient_data`, `watch`, `review_signals`, `no_alert`. Even `no_alert` does not establish effective human oversight.

All interpretations refer to the prototype only. Confirm real deployment requirements separately with appropriate legal and domain experts.
