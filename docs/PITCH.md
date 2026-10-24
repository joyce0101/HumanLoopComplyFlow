# 3-minute pitch — LoopLedger

## 0:00–0:30 — The problem

"AI is increasingly involved in high-stakes decisions. Many organizations add a human approval step, but a checkbox alone cannot show whether a reviewer carefully considered the AI's recommendation. If reviewers blindly follow the model, the oversight process may look robust on paper while missing obvious mistakes."

## 0:30–1:00 — Our solution

"LoopLedger is a lightweight assurance layer. First, a risk gate selects cases for human review. Then our review interface records the human's decision, reason and review duration. Finally, we analyze signals such as override rates, review-time patterns and deliberately incorrect synthetic control cases. These signals help identify where further oversight evaluation may be needed."

## 1:00–2:00 — Live demo

**[Open Run Batch]** "We submit a batch of simulated applications. Some are automatically processed, while others enter the review queue."

**[Open Review Queue]** "Here, the reviewer sees the model advice, confidence and example factors. The reviewer can agree or override with a reason."

**[Open Oversight Dashboard]** "We see how two simulated reviewers behave. Short review times and missed controls can be warning signals. They are not proof of negligence, and the thresholds must be validated for real deployment."

## 2:00–2:30 — Evidence / regulation

**[Open Compliance]** "Every prediction, gate decision and review is recorded in a hash-linked local log. We can verify its consistency and export a Markdown or JSON evidence summary. This report links our features to selected EU AI Act requirements and ISO/IEC 42001 at a high level. It also makes clear what this prototype does *not* establish."

**[Optional: demonstrate tamper]** "If someone naively edits a stored event, the check detects the change. A production system would need stronger controls such as external log anchoring."

## 2:30–3:00 — Impact and close

"Our target users are teams implementing or auditing human oversight for consequential AI systems. The next step would be to connect LoopLedger to real models, calibrate the risk gate on representative evidence, and validate oversight metrics with trained reviewers. Our goal is to move from *'a person clicked approve'* to *'we can produce and examine evidence of how oversight happened.'*"

## Judge Q&A anchors

- **How is this different from approval software?** Review-quality proxies and portable evidence, in addition to approval logs.
- **Are the flags fair to reviewers?** Not evaluated yet; never use these demo signals for personnel decisions.
- **Do your gold controls prove reviewers are competent?** No, synthetic controls are a research proxy and must be validated.
- **Is your hash chain immutable?** No. It detects naïve edits; privileged rewrites require independent anchoring or a trusted log service to detect.
- **Is this legally compliant?** We map evidence to relevant expectations but don't assert conformity or that a given deployment is legally classified as high-risk.
