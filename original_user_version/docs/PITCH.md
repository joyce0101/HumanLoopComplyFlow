# 3-minute pitch — LoopLedger (current connected prototype)

## 0:00–0:30 — Problem

"AI is entering consequential decision workflows. Adding an approval button does not guarantee effective human oversight. Reviewers may follow the model without noticing an error; and even when a review happens, auditors need to know what was done and what evidence was retained."

## 0:30–1:00 — Solution

"LoopLedger combines AI decision routing, a real human review queue, oversight indicators and an auditable event log. We record the model advice, the risk gate, the human's action, the stated reason and elapsed time. Our dashboard uses override rates, review times, short reasons and deliberately constructed synthetic controls to highlight patterns worth further investigation."

## 1:00–2:00 — Live product walkthrough

**Run Batch:** "We load examples from the German Credit dataset. A trained logistic-regression model outputs an approval or rejection recommendation, confidence and main contributing factors. Risk rules route selected examples for manual review. Both the prediction and the gate result are saved in SQLite."

**Review Queue:** "We open a saved case, inspect the recommendation and factors, then approve, reject or choose Modify / hold with a reason. The review is saved to the database, including its duration. Modify means a hold or request for further evidence, not automatic loan approval."

**Oversight Dashboard:** "Here we see counts from the saved database and reviewers' oversight indicators. For a seeded demonstration, two synthetic reviewer patterns show different detection rates on deliberately wrong AI-control cases. These rates are illustrative and do not establish that a real reviewer is diligent or negligent."

## 2:00–2:30 — Evidence and integrity

**Compliance:** "The system uses SHA-256 hashes to link recorded events. It can check the chain for obvious edits and export corresponding Markdown and JSON evidence reports. The report explains related EU AI Act Articles 12, 13 and 14 and ISO/IEC 42001 at a high level; it does not claim legal compliance."

**Optional tamper demonstration:** "We modify only a copy of the demo database and show that the chain check identifies a mismatch. A privileged rewrite of the entire database would require stronger independent anchoring to detect."

## 2:30–3:00 — Impact

"Our goal is not to declare that every human decision is correct. It is to make oversight observable and reviewable: from a model recommendation to a stored human action, monitoring metrics and an exportable evidence trail. Future work includes stronger identity and governance controls, validated assessment metrics and independent audit logging."

## Judge Q&A anchors

- **Which ML algorithm is running?** Logistic regression trained on German Credit; factor values are log-odds contributions, not XGBoost or SHAP.
- **Are these live real-world loans?** No. Dataset cases and synthetic controls only. No loan is actually issued.
- **What does the gold-control rate measure?** Exact match to the expected action among synthetic reviewed controls where the AI advice is deliberately different. It is not a general accuracy or competence score.
- **Do you prove genuine human judgment?** No. Timing, reasons and actions are observable signals and can be misleading.
- **Is the log immutable?** No. Its local hash chain detects straightforward tampering, not arbitrary privileged database rewrites.
- **Is the system AI Act / ISO compliant?** We provide a high-level evidence mapping, not a conformity determination or certification.

## Demo preparation

- Use a disposable database. Complete Run Batch → Review Queue → Dashboard → Compliance at least once before presenting.
- Keep `docs/COMPLIANCE_MAPPING.md` and actual report values nearby; never substitute poster placeholders for measured output.
- For the red/green reviewer comparison, seed the B `oversight` profile and clearly label it **synthetic demonstration data**.
