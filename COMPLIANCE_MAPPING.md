# LoopLedger — Compliance Mapping (D)

## Scope and status

This is a **design-time evidence mapping** for the LoopLedger hackathon prototype, not legal advice, a demonstration of high-risk classification, an ISO certification or an attestation of compliance. The model and human review controls are mocks until replaced with the team's actual work. Applicability, adequate design and implementation must be independently assessed.

| Source | Relevant expectation (short description) | LoopLedger evidence | Remaining gap |
|---|---|---|---|
| [EU AI Act Article 12](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-12) | Logging & traceability for high-risk AI systems | Prediction/gate/review event trail; per-event timestamp; chain verification | Event coverage, retention, completeness and operator access controls need validation |
| [EU AI Act Article 13](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-13) | Transparency and adequate information to deployers | User-facing decision, confidence and mock factors | No validated explainability, instructions for use or measured limitations |
| [EU AI Act Article 14](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-14) | Effective human oversight and mechanisms to interpret/override, including awareness of automation bias | Review UI, logged actions, timing, override rates, synthetic gold tests | Metrics are indirect proxies; training, interventions and true oversight effectiveness have not been validated |
| [ISO/IEC 42001:2023](https://webstore.iec.ch/en/publication/90574) | Organizational AI management system and ongoing improvement | Summary metrics, traceability, evidence exports | Not a clause-by-clause management system review or accredited certification |

## How judges should read this

- **Evidence present:** The report shows what was technically logged or computed from the *demo*.
- **Not established:** No claim that the system meets any cited legal or standard requirement in full.
- **Missing controls:** Validated deployment procedures, complete transparency materials, access controls, log retention, real reviewer testing, governance processes and a formal risk assessment.

## Terms

- **Override rate:** Share of human review actions differing from displayed AI advice; it is not by itself a measure of correctness.
- **Gold-control catch rate:** Share of deliberately inverted synthetic AI suggestions that reviewers identified (by submitting the control's reference choice). Construct validity needs evaluation.
- **Hash-chain integrity:** A chain consistency check over saved events. It does not guarantee append-only immutability against a privileged attacker.
- **Heuristic flags:** Demo rules used to illustrate monitoring; not assessments of any real employees.

