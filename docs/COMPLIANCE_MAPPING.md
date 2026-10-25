# LoopLedger — UK GDPR Evidence Mapping

## Scope and status

LoopLedger is a **hackathon prototype** with a connected German Credit logistic-regression model, a risk gate, SQLite audit events, human review pages, oversight indicators and report exports. It does not issue loans. Report section 5 maps selected **UK GDPR** requirements to technical evidence and remaining gaps, read alongside the Data Protection Act 2018 and applicable Data (Use and Access) Act 2025 amendments. References were checked on 25 October 2026. This is not a full UK GDPR assessment or a compliance certification.

The mapping data lives in [compliance_mapping.py](../loopledger/compliance_mapping.py). Both Markdown and JSON use the existing `regulatory_mapping` field and the same requirement, feature, evidence-location, limitation and source-link fields.

| UK GDPR reference | Evidence to inspect | Remaining assessment |
|---|---|---|
| Articles 5(2), 24(1): accountability | `report_id`, event counts, timestamped review records and reviewer indicators | Controller responsibilities, policies and compliance are not established by technical records |
| Article 6(1): lawful basis | `data_origin` describes the dataset/demo context | Data origin does not establish a lawful basis for a deployment |
| Articles 12(1), 13(2)(f), 14(2)(g), 15(1)(h): transparency and access | Review Queue fields, recommendations and log-odds factors | Reviewer-facing information is not an applicant notice or an access-request process |
| Articles 22A-22C: significant automated decisions | Routing and human review events, reasons and departures from AI advice | Meaningful human involvement and the four applicant safeguards are not established; Article 22B restrictions require assessment |
| Articles 25(1)-(2), 5(1)(c),(e): design, minimisation and retention | UI field allowlist and hashed display IDs | Stored records remain identifiable; privacy defaults and retention/erasure controls require assessment |
| Article 30(1): processing activities | `data_origin`, `event_counts`, `system_stats` | An event log is not a record of processing activities; the separate register and any Article 30(5) exception need assessment |
| Article 32(1): security | Chain integrity result and tamper-detection tests | A local chain check does not assess confidentiality, availability, resilience or all security measures |
| Article 35(1),(3)(a),(7): DPIA | Routing counts, reviewer indicators and recorded limitations | These are possible inputs to risk analysis, not a completed DPIA |

## Official references

- [UK GDPR — legislation.gov.uk](https://www.legislation.gov.uk/eur/2016/679/contents).
- [Data Protection Act 2018](https://www.legislation.gov.uk/ukpga/2018/12/contents).
- [DUAA 2025 section 80: new Articles 22A-22D](https://www.legislation.gov.uk/ukpga/2025/18/section/80).
- [SI 2026/82 regulation 2: commencement on 5 February 2026](https://www.legislation.gov.uk/uksi/2026/82/regulation/2).
- [SI 2026/82 regulation 5: transitional provisions](https://www.legislation.gov.uk/uksi/2026/82/regulation/5).
- [ICO: individual rights and Article 22C safeguards](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/smart-data-schemes-and-data-protection/individual-rights/).

## Automated-decision framework used in this mapping

The section 80 reforms commenced on **5 February 2026**. The report therefore uses **Articles 22A-22C**, rather than the previous Article 22 exception structure:

- **22A:** Assess whether the decision has legal or comparably significant effects and whether a person meaningfully participates; profiling is relevant to that assessment.
- **22B:** Additional conditions apply to special-category data. Article 22B(4) also bars solely automated significant decisions that rely wholly or partly on recognised legitimate interests under Article 6(1)(ea).
- **22C:** For in-scope decisions, individuals must receive decision information and be able to make representations, obtain human intervention and contest the decision. An internal operator review queue does not by itself implement these four applicant safeguards.

Transitional provisions preserve the previous rules for certain decisions taken before 5 February 2026; assess historical cases separately. Also consider applicable regulations under Article 22D. Article 30 has conditional exemptions, and Article 35 requires a pre-processing DPIA when high risk is likely. The report does not determine these deployment-specific questions or supply a prescribed statutory report form.

## What the evidence does and does not say

**Present:** Demonstration records for the cases that exist in the selected local database; a consistency check for observed audit events; reviewer metrics and a downloadable structured report.

**Not established:** Whether the event history is complete; whether reviewers are genuine, attentive or competent; whether model decisions are fair, accurate or lawful; whether any specific legal requirement applies or is satisfied.

The saved database can contain a mixture of real model-generated predictions and **synthetic fixtures**. A successful chain verification indicates internal consistency of observed events only. It does not prove an attacker with full database privileges has not replaced/recalculated the chain.

## Metric definitions

- **Override rate:** Proportion of matched reviews with a recorded action differing from the model's advice. An override may be incorrect.
- **Gold catch rate:** Among reviewed synthetic controls **where the model's recommendation differs from the expected action**, proportion where the review action exactly equals the binary expected action (`approve` or `reject`). Correct-AI controls and legacy non-binary answer labels are excluded; no eligible sample is `null`/N/A, not 0%.
- **Average review time:** Average recorded duration over usable timings. It may include time away from the page and does not establish attention.
- **Short-reason rate:** Share of submitted review reasons shorter than 12 characters after trimming. This is not natural-language quality assessment.
- **Heuristic flag:** `insufficient_data`, `watch`, `review_signals`, `no_alert`. Even `no_alert` does not establish effective human oversight.

All interpretations refer to the prototype only. Confirm real deployment requirements separately with appropriate legal and domain experts.
