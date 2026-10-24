"""D: possible evidence mapping; not a finding of regulatory compliance."""

COMPLIANCE_MAPPING = [
    {
        "framework": "EU AI Act",
        "reference": "Article 12 — Record-keeping",
        "expectation": "High-risk AI systems should provide appropriate automatic logging and traceability.",
        "loopledger_feature": "Timestamped prediction, gate and review events; SHA-256 event-chain checks",
        "evidence_field": "event_counts, total_events, integrity.chain_intact",
        "limitation": "No independent event anchoring; coverage, retention and operator access controls need validation.",
        "source_url": "https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-12",
    },
    {
        "framework": "EU AI Act",
        "reference": "Article 13 — Transparency to deployers",
        "expectation": "Provide information enabling deployers to interpret and use system outputs appropriately.",
        "loopledger_feature": "Visible AI recommendation, confidence and logistic-regression log-odds factors",
        "evidence_field": "prediction event payload; application review interface",
        "limitation": "Illustrative explanations are not SHAP, causality or validated instructions for use.",
        "source_url": "https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-13",
    },
    {
        "framework": "EU AI Act",
        "reference": "Article 14 — Human oversight",
        "expectation": "Enable meaningful monitoring, interpretation, intervention and awareness of automation bias.",
        "loopledger_feature": "Review UI; recorded actions and reasons; override, review-time and synthetic gold-control measures",
        "evidence_field": "reviewer_metrics, system_stats, review event payloads",
        "limitation": "Heuristic review indicators and synthetic controls do not establish effective oversight.",
        "source_url": "https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-14",
    },
    {
        "framework": "ISO/IEC 42001:2023",
        "reference": "AI management system (high-level alignment)",
        "expectation": "Organizational processes for establishing, maintaining and improving AI management.",
        "loopledger_feature": "Structured monitoring records and downloadable evidence summaries",
        "evidence_field": "report metadata, system_stats, reviewer_metrics, integrity",
        "limitation": "No organizational management-system assessment or accredited ISO certification.",
        "source_url": "https://webstore.iec.ch/en/publication/90574",
    },
]
