"""Selected UK GDPR requirements and prototype evidence; not a compliance verdict.

The existing mapping keys remain shared by the Markdown and JSON exports.
Requirements are paraphrased; applicability and exceptions need deployment review.
References checked on 25 October 2026, including the DUAA 2025 ADM amendments.
"""

UK_GDPR_SOURCE = "https://www.legislation.gov.uk/eur/2016/679"

COMPLIANCE_MAPPING = [
    {
        "framework": "UK GDPR",
        "reference": "Article 5(2) and Article 24(1) — Accountability",
        "expectation": "Controllers must implement appropriate measures and be able to demonstrate compliance.",
        "loopledger_feature": "Timestamped prediction, routing and review records; reviewer indicators and report exports",
        "evidence_field": "report_id, total_events, event_counts, reviewer_metrics",
        "limitation": "Technical records alone do not establish controller responsibility, policies, lawful processing or effective oversight.",
        "source_url": f"{UK_GDPR_SOURCE}/article/5",
    },
    {
        "framework": "UK GDPR",
        "reference": "Article 6(1) — Lawfulness of processing",
        "expectation": "Identify a valid legal basis for each personal-data processing purpose.",
        "loopledger_feature": "Report identifies the mixed dataset, model-output and synthetic-record context",
        "evidence_field": "data_origin",
        "limitation": "Data origin is not a legal basis. No deployment-specific basis, controller identity or purpose assessment is established by this report.",
        "source_url": f"{UK_GDPR_SOURCE}/article/6",
    },
    {
        "framework": "UK GDPR",
        "reference": "Articles 12(1), 13(2)(f), 14(2)(g) and 15(1)(h) — Transparency and access",
        "expectation": "Provide clear information; for decisions subject to Article 22C safeguards, explain automated decisions, their logic, significance and envisaged consequences.",
        "loopledger_feature": "Reviewers can inspect the recommendation, confidence, application fields and log-odds contributions",
        "evidence_field": "prediction event payloads; Review Queue application details and factor chart",
        "limitation": "A reviewer-facing explanation is not an applicant privacy notice or access-request service. Log-odds factors alone do not establish adequate information about decision logic and consequences.",
        "source_url": f"{UK_GDPR_SOURCE}/article/13",
    },
    {
        "framework": "UK GDPR",
        "reference": "Articles 22A-22C — Significant automated decisions and safeguards",
        "expectation": "For solely automated significant decisions, provide information and enable representations, human intervention and contestation; assess Article 22B restrictions.",
        "loopledger_feature": "Risk-based referral, human approval/rejection, reasons, timing and recorded departures from AI advice",
        "evidence_field": "system_stats.sent_to_review, reviewer_metrics, prediction/gate/review event payloads",
        "limitation": "The operator queue does not implement all four applicant safeguards or establish meaningful human involvement. Special-category decisions require assessment under Article 22B(1)-(3); Article 22B(4) bars reliance, wholly or partly, on Article 6(1)(ea) for solely automated significant decisions.",
        "source_url": f"{UK_GDPR_SOURCE}/article/22C",
    },
    {
        "framework": "UK GDPR",
        "reference": "Article 25(1)-(2) and Article 5(1)(c),(e) — Privacy by design, minimisation and retention",
        "expectation": "Build proportionate privacy safeguards into processing; limit data, storage duration and access by default.",
        "loopledger_feature": "Review UI uses a public-field allowlist and hashed application display identifiers",
        "evidence_field": "Review Queue public-field allowlist; stored prediction and review payloads",
        "limitation": "Hashed display IDs do not anonymise the stored records. Full records and original IDs remain in SQLite; purpose-based retention, erasure and access defaults are not established.",
        "source_url": f"{UK_GDPR_SOURCE}/article/25",
    },
    {
        "framework": "UK GDPR",
        "reference": "Article 30(1) — Records of processing activities",
        "expectation": "Where required, document controller, purposes, data categories, recipients, transfers, retention and security measures.",
        "loopledger_feature": "Event categories and system counts support a technical inventory of the demonstrated workflow",
        "evidence_field": "data_origin, event_counts, system_stats",
        "limitation": "An event log is not a record of processing activities. Controller/contact details, processing purposes, subject/data categories, recipient/transfer information and retention schedules require a separate register; applicability and Article 30(5) exceptions need assessment.",
        "source_url": f"{UK_GDPR_SOURCE}/article/30",
    },
    {
        "framework": "UK GDPR",
        "reference": "Article 32(1) — Security of processing",
        "expectation": "Use risk-appropriate confidentiality, integrity, availability and resilience measures, with regular security testing.",
        "loopledger_feature": "SHA-256 event-chain consistency checks and reproducible tamper-detection tests",
        "evidence_field": "integrity.chain_intact, integrity.first_broken_event_id, integrity.tip_hash",
        "limitation": "A chain PASS is not a security assessment. Privileged rewrites remain possible; authentication, access control, encryption, availability and recovery controls require separate assessment.",
        "source_url": f"{UK_GDPR_SOURCE}/article/32",
    },
    {
        "framework": "UK GDPR",
        "reference": "Article 35(1),(3)(a),(7) — Data protection impact assessment",
        "expectation": "Before likely high-risk processing, assess necessity, proportionality, rights risks and planned safeguards through a DPIA.",
        "loopledger_feature": "Routing counts, recorded review behaviour and integrity limitations can inform risk analysis",
        "evidence_field": "system_stats, reviewer_metrics, integrity, limitations",
        "limitation": "This evidence summary is not a DPIA. No completed assessment of necessity, proportionality, individual impacts or residual risks is produced.",
        "source_url": f"{UK_GDPR_SOURCE}/article/35",
    },
]
