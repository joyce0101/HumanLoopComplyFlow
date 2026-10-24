# LoopLedger — English Demo Script and Judge Q&A

Companion to [DEMO_SCENARIOS.md](DEMO_SCENARIOS.md). Prepared against the current implementation on 25 October 2026.

**Format:** one presenter and an optional silent operator. Read the blockquotes aloud. Instructions marked **Operator** and all code blocks are preparation notes, not spoken text. The main script is intended for approximately 12 minutes, including clicks, brief pauses and the database-copy demonstration. Questions are additional.

Use only **Approve application** and **Reject application**. Use the project-root `loopledger.db` for the demonstration and a separate copy for the tamper scene. Predictions from the trained model, scripted gold controls and synthetic reviewer histories must remain clearly identified.

## 1. Operator preparation

Run commands from the project root in a Python environment with the project dependencies installed.

The saved demonstration checkpoint contains **66 applications, 14 completed reviews, 146 events and 18 pending cases**. Scene 1's batch has already been run. To continue this checkpoint, start the application below, show the existing result and proceed to Scene 2 without running another batch.

For a full rehearsal from Scene 1, first stop the demonstration server and run the following reset. **It clears the current contents of `loopledger.db` without making a backup. Skip this block when continuing the saved checkpoint.**

```bash
python scripts/demo_reset.py --db loopledger.db --force --profile functional
LOOPLEDGER_DB_PATH=loopledger.db python - <<'PY'
from loopledger import ledger
from loopledger.schemas import ReviewAction

for pred, decision in zip(ledger.get_pending_reviews(), ("approve", "reject")):
    ledger.submit_review(ReviewAction(
        pred.case_id, "demo_judge", decision,
        "Checked the application and supporting evidence.", 35.0,
    ))
print("Chain check:", ledger.verify_chain())
PY
```

Terminal A:

```bash
LOOPLEDGER_DB_PATH=loopledger.db python -m streamlit run app.py --server.port 8503
```

Open http://127.0.0.1:8503/. Keep Terminal B ready for the later copy/tamper command.

After the optional reset, the database contains 16 synthetic applications, 14 completed reviews and 46 events, with no pending cases. The script's running totals assume this fresh starting point. Its reviewer profiles are preloaded test fixtures. Use **live_reviewer** for all on-stage reviews, so those profiles remain unchanged.

Freeze the dataset and model artifact for rehearsal and presentation. The batch counts and individual examples below were checked against the current artifact. If the page shows different numbers, read the page and use the alternate lines; do not quote a rehearsed number that the audience cannot see.

### Finding the three live cases

Run this read-only lookup **after** the live batch has completed. The operator can do it while the presenter explains the batch counts. Copy the displayed APP identifier into the queue's searchable selector. New batch identifiers change on each run, so identifiers copied from a previous rehearsal cannot be reused.

```bash
LOOPLEDGER_DB_PATH=loopledger.db python - <<'PY'
import hashlib
from loopledger.ledger import get_pending_reviews

pending = get_pending_reviews()
ordinary = [p for p in pending if not p.is_gold and p.confidence < 0.70]
preferred = next((p for p in ordinary if p.features.get('credit_amount') == 9271), None)
targets = [
    ('LOW CONFIDENCE', preferred or (ordinary[0] if ordinary else None)),
    ('HIGH AMOUNT GOLD', next((p for p in pending if p.is_gold
                              and p.features.get('credit_amount') == 25000), None)),
    ('CORRECT AI CONTROL', next((p for p in pending if p.is_gold
                                 and p.features.get('policy_checks_passed') is True), None)),
]
for label, pred in targets:
    if pred is None:
        print(label, 'NOT FOUND — use the corresponding alternate script')
        continue
    public_id = 'APP-' + hashlib.sha256(pred.case_id.encode()).hexdigest()[:12]
    print(label, public_id, 'amount=', pred.features.get('credit_amount'),
          'AI=', pred.decision, 'confidence=', f'{pred.confidence:.2%}')
PY
```

This lookup reads stored cases. It does not submit or modify a review.

## 2. Word-for-word presentation

### 00:00–00:45 — Opening

**Operator:** Show the homepage at port 8503.

**Presenter:**

> Good morning. We are presenting LoopLedger, a prototype for making AI-assisted decisions easier to review and trace.
>
> We connect four stages: model recommendations, human review, oversight indicators, and an evidence report.
>
> Today we will use a loan-classification example. You will see predictions from a trained model, deliberately constructed control cases, and prepared reviewer histories. I will identify each as we go.
>
> Our goal is to show what happened during a review, which patterns may need attention, and what evidence the system retains.

### 00:45–02:10 — Scene 1: automatic routing

**Operator:** Open **Run Batch**. Set **Number of applications** to 50. Check **Assume identity verified for this dataset demo**. Click **Run batch** once and wait for completion.

**Presenter:**

> We begin with fifty applications. Forty-five are sampled dataset cases evaluated by our trained model. Five are synthetic controls with preset answers.
>
> I am selecting the identity-verification assumption for this demonstration. This sets a business flag. It does not perform an identity check or approve a loan.
>
> The current result is twenty-seven automatic approvals, five automatic rejections, and eighteen cases requiring human review.
>
> For example, the model recommends approving an application for one thousand, two hundred and thirty-seven dataset units, with confidence close to ninety-eight percent. Another application can be automatically rejected. Automatic routing works in both directions.
>
> The gate sends uncertain cases, large amounts and other triggered conditions to a person. The application records these outcomes; it does not issue loans.

**Operator:** Point to the routing counts. Run the case lookup above while the presenter finishes this section.

**Alternate line if counts differ — replace the sentence giving 27/5/18:**

> These counters show the actual split for this run: automatic approvals, automatic rejections, and cases sent for human review. Our rehearsal used the same dataset and model; the values on this screen are the ones we will use today.

**If asked why the dashboard later shows 66 applications:** the prepared database already had 16. This batch adds 50; the batch counter and cumulative database counter measure different things.

### 02:10–03:45 — Scene 2: an uncertain model recommendation

**Operator:** Open **Review Queue** and select the **LOW CONFIDENCE** application found by the lookup. Confirm the amount is 9,271 before using the specific-number sentence below. Hover over two bars, allowing the audience to read each tooltip.

**Presenter:**

> This application requests nine thousand, two hundred and seventy-one units over thirty-six months. The model recommends rejection, with confidence of about fifty-three percent. That falls below our review threshold of seventy percent.
>
> The reviewer can inspect the credit history, account information, savings and employment details. The chart shows the ten largest feature contributions for this prediction.
>
> Hovering over a bar explains the field, the recorded application value, and the direction of its contribution. Red pushes the model toward rejection; green pushes it toward approval. These are contributions to log odds. They are separate from the overall confidence shown on the left.
>
> After inspecting the information, I will record a decision and a reason. The reviewer can agree with the model or choose a different action. An override by itself does not establish that the human was correct.

**Operator:** Enter reviewer **live_reviewer**. Read the displayed data, then enter the demonstration reason below and click **Reject application**. This scene demonstrates the workflow, not an independently validated correct answer for this ordinary dataset case.

```text
Checked the recorded credit history, savings and repayment term before deciding.
```

**Alternate first sentence if a different ordinary case was selected:**

> This application has model confidence below our review threshold. We will use the recommendation and values shown here to demonstrate the review process.

### 03:45–05:20 — Scene 3: a confident but deliberately wrong recommendation

**Operator:** Select **HIGH AMOUNT GOLD**. Point to the amount and **Extra proof: False**. Do not look for ten factor bars on this synthetic control; no model contributions are supplied for it.

**Presenter:**

> This is a synthetic gold control. It requests twenty-five thousand units and has no additional supporting proof, but its displayed AI recommendation is approval.
>
> The displayed confidence is ninety-five percent. That number is scripted for this control; it is not a measurement of our model's performance.
>
> The amount exceeds our demonstration threshold, and gold controls always go to human review. Within this demo policy, the expected action is rejection because the required supporting evidence is missing.
>
> I will inspect the evidence and reject the application, with a reason linked to what is missing. The system records the action, reviewer name, reason and elapsed time.
>
> The GOLD label is visible to make this demonstration understandable. This is a controlled example, not a blinded experiment on real reviewers.

**Operator:** Use **live_reviewer**, enter the reason below, and click **Reject application**.

```text
The requested amount exceeds the demo threshold and additional supporting evidence is missing.
```

**If this control is unavailable:** use the gold control for 3,000 units with **Identity verified: False**. Explain its missing identity evidence and preset rejection answer. Identify its 95% confidence as scripted. Do not substitute invented model predictions.

### 05:20–06:10 — Scene 4: agreeing with a correct recommendation

**Operator:** Select **CORRECT AI CONTROL**, for 2,500 units, with **Policy checks passed: True**.

**Presenter:**

> Here the control says that all simulated policy checks passed. The AI recommends approval, and its preset answer is also approval.
>
> I will approve this case after checking the available information. Human review does not require disagreement with the model.
>
> This case is excluded from the error catch rate because the AI did not make an error under its preset answer. The metric asks whether a reviewer caught known AI errors. It is not accuracy across every gold case.

**Operator:** Submit **Approve application**, reviewer **live_reviewer**, with this reason:

```text
Checked the recorded application evidence and the stated policy checks before approving.
```

### 06:10–08:20 — Scene 5: contrasting review behavior

**Operator:** Open **Oversight Dashboard**, refresh, and point to the prepared profiles. Hover over the **Flag reasons** column header. Show the review-time charts.

**Presenter:**

> We can now look at the recorded review activity. The comparison profiles on this page are synthetic test histories prepared before the presentation. Our live actions use a different reviewer name.
>
> The careful-reviewer profile has six reviews, an average time of fifty seconds, and three correct responses to three AI-error controls. It has no short reasons, and no heuristic alert is triggered.
>
> The rubber-stamp profile also has six reviews. Its average time is two seconds. It follows every AI recommendation, misses all three error controls, and uses short reasons throughout. Those signals trigger a red status for further investigation.
>
> Green means no configured alert was triggered. Red identifies a pattern worth investigating. Neither color establishes a person's competence.
>
> Our live reviewer has only three reviews. One is an eligible AI-error control, so a correct response gives one out of one, or one hundred percent. The sample is still too small, and the status is grey.
>
> This is why we show sample counts alongside rates. A perfect percentage from one case is very different from evidence collected across many independent reviews.

**Expected prepared profiles — do not read every cell:**

| Reviewer | Reviews | Mean time | Overrides | Eligible gold checks | Catch rate | Short reasons | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| careful_reviewer | 6 | 50 seconds | 50% | 3 | 100% | 0% | No heuristic alert |
| rubber_stamp | 6 | 2 seconds | 0% | 3 | 0% | 100% | Review signals |
| demo_judge | 2 | 35 seconds | 50% | 0 | N/A | 0% | Insufficient data |

The live-reviewer paragraph assumes exactly the three submissions in Scenes 2–4 and a fresh reviewer name. If any scene was skipped or repeated, describe the actual review count and gold sample count shown on screen.

### 08:20–11:20 — Scene 6: checking and exporting the evidence

**Operator:** Open **Compliance** on port 8503. Click **Verify chain**, then **Generate report**. Download the Markdown and JSON files.

**Presenter:**

> Each stored event is linked to the previous event using a SHA-two-fifty-six hash. We can check whether the recorded sequence remains consistent.
>
> The clean database passes this check. The report summarizes the saved activity, reviewer indicators and integrity result. The page checks that the Markdown and JSON report identifiers match, and that the integrity result agrees with the check, before enabling downloads.
>
> We will now create a copy of this database and alter one event in the copy. The original stays unchanged.

**Operator, Terminal B:**

```bash
python scripts/demo_tamper.py --source loopledger.db --output loopledger-tampered.db --event-id 10
```

The output file must not already exist. Create this copy after the live reviews, so both pages refer to the same business-data checkpoint.

```bash
LOOPLEDGER_DB_PATH=loopledger-tampered.db python -m streamlit run app.py --server.port 8504
```

**Operator:** Open http://127.0.0.1:8504/, navigate to **Compliance**, verify the chain, and show the first inconsistent event. Generate the failure report if time permits.

**Presenter:**

> The altered copy fails at event number ten. Its report records that failure, so the discrepancy can be retained as evidence.
>
> Returning to the original database, the check still passes. We have demonstrated detection of an altered event in this local chain.
>
> The security boundary matters. Someone with full database control could rebuild the entire chain. Stronger protection would require independent checkpoints or external storage controls.
>
> These exports support inspection of technical evidence. They do not certify compliance or establish that every decision was fair or correct.

**Operator:** Return to port 8503 and verify the original chain again.

### 11:20–12:00 — Closing

**Operator:** Leave the clean report or dashboard visible.

**Presenter:**

> LoopLedger connects a model recommendation to a human action, recorded review indicators, and an exportable evidence summary.
>
> In this prototype, we can inspect that workflow from end to end. The next work is to validate the assessment methods, improve the control cases, and strengthen identity and audit protections.
>
> Thank you. We welcome your questions.

## 3. Judge questions and suggested spoken answers

These are answers to prepare, not additional presentation sections. Keep the first answer short; expand only if asked. Numerical model metrics below were read from the current saved artifact, not measured during a human-review study.

### Q1. What is the main contribution beyond an approval button or an ordinary log?

**Answer:** We connect the original recommendation, routing decision, human action and review indicators through stored case identifiers and audit events. A reviewer can inspect one application, while a supervisor can examine patterns across reviews and export an evidence summary. The contribution is the connected workflow. We have not yet demonstrated that it improves real-world decision quality.

### Q2. Which model are you actually running? Is this XGBoost with SHAP?

**Answer:** The current implementation is scikit-learn logistic regression trained on German Credit. Numerical features are standardized, and categorical features are one-hot encoded. The chart uses coefficient-times-input contributions to log odds. XGBoost and SHAP appeared in the original plan, but they are not the implemented explanation method.

### Q3. How accurate is the model?

**Answer:** The current saved artifact records 77.2 percent accuracy, a ROC-AUC of 0.8043, and a Brier score of 0.156 on a fixed held-out set of 250 rows, with 750 training rows. Those are benchmark results for this dataset and split. We repeatedly sample that same held-out set for the demo; this is not a new external validation, fairness assessment or production lending evaluation.

### Q4. What does Confidence mean? Does 98% mean the decision is 98% certain to be correct?

**Answer:** It is the model's predicted probability for its recommended class: the larger of the predicted good-credit and bad-credit probabilities. It is not a measured probability that the whole decision is correct or appropriate. We have not established calibration on a deployment population. We use the displayed value as one demonstration routing signal, not a guarantee.

### Q5. Why use a 70% confidence threshold and a 15,000 amount threshold?

**Answer:** They are explicit demonstration rules in the risk gate. They make the routing behavior understandable and testable. They are not validated lending thresholds. A deployment would need thresholds defined with domain specialists and evaluated against the intended population, workload, error costs and operating policy.

### Q6. What does the identity checkbox verify?

**Answer:** It sets an identity-verified flag for the dataset examples. The dataset has no identity-verification evidence, and the application does not perform a document or identity check. Gold controls keep their own predefined identity flags. Selecting the checkbox does not override low confidence, high amounts or other review conditions.

### Q7. Why only approve and reject? What happens when documents are missing?

**Answer:** The implemented review workflow is binary. Our synthetic missing-evidence cases use rejection under the demonstration policy. There is no document-upload, evidence-request or resubmission lifecycle yet. We would need to define that operating process before using this in a setting where an application should be paused rather than decided.

### Q8. What are gold cases, and who decided the answers?

**Answer:** They are synthetic control cases with preset expected actions, created from our demonstration rules. Some deliberately disagree with the displayed AI advice; others are correct-AI controls. They have not been established as expert-reviewed ground truth for real lending. The model-module controls use a scripted 95% confidence and do not supply model feature contributions.

### Q9. GOLD is visible. Does this demonstrate genuine human oversight?

**Answer:** It demonstrates the workflow and scoring mechanism under visible control conditions. It does not validate blinded error detection or genuine attention. The marker is visible so judges can follow the example. A formal evaluation would need independently reviewed controls, appropriate blinding, balanced errors and a study protocol.

### Q10. Exactly how is Gold catch rate calculated?

**Answer:** For each reviewer, we take completed gold cases with a valid approve-or-reject answer where the original AI advice differs from that answer. The numerator is the number of exact matches between the human action and the expected answer. Correct-AI controls, pending cases, ordinary applications and unsupported historical answers are excluded. With no eligible cases, the rate is unavailable, not zero.

**Useful example:** One caught error and one missed error give one out of two, or 50%. Reviewing an additional correct-AI control does not change that denominator.

### Q11. Could someone game the score by always rejecting?

**Answer:** Yes, that is a real limitation of the current live templates: their eligible errors are approval recommendations with rejection answers. Always rejecting can therefore achieve a perfect live-template catch rate. The seeded comparison includes error probes in both directions, but we have not added an overall control-accuracy or false-override measure. The current catch rate alone cannot establish good oversight.

### Q12. Why doesn't rejecting a correct-AI control reduce the catch rate?

**Answer:** The metric specifically measures detection of known AI errors, so correct-AI controls are excluded. That means an incorrect human rejection of a correct recommendation is not captured by this rate. We would need a separate measure of control accuracy or harmful overrides to evaluate both kinds of mistake.

### Q13. Are the green and red reviewer results from real people?

**Answer:** No. Those are synthetic histories generated by our demonstration script. They check that the stored events produce the expected indicators and alerts. The live actions are recorded separately under live_reviewer. We have not conducted a controlled study of real reviewers or shown that the system improves their decisions.

### Q14. Why is a reviewer with 100% catch rate still grey?

**Answer:** A percentage does not show sample size. In this demo, the live reviewer has only three reviews and one eligible error control. The current rules prioritize insufficient data when there are fewer than five reviews or when required timings or prediction matches are missing. Gold-rate alerts additionally require at least three eligible error controls. These are demonstration heuristics, not validated statistical confidence thresholds.

### Q15. Does a short review, short reason or zero overrides prove rubber-stamping?

**Answer:** No. A fast decision can be justified, a short reason can be meaningful, and agreement can be correct. Our system exposes those observations and combines them with control-case outcomes. Its alerts are prompts for investigation. We have not validated their sensitivity, specificity or suitability for staff performance assessment.

### Q16. What do the ten factors mean, and why are some green and some red?

**Answer:** They are the ten largest absolute contributions to this particular model prediction. Positive values increase the model's log odds of the bad-credit class, which the demo maps to rejection; negative values move the other way. The hover text identifies the input and its recorded value. The full model also includes all remaining features and an intercept. A contribution is neither a causal effect nor a percentage-point change in probability.

### Q17. What about old records with only five factors, or cases with no factors?

**Answer:** We keep the stored evidence. For an older record, extra factors are displayed only if the current model reproduces the stored decision, confidence and existing contribution prefix. Those extra factors are labelled as recomputed and are not written back. This matching does not prove artifact identity; proper historical reproduction needs retained model versions. Cases without usable contributions show an explanation instead of invented bars.

### Q18. Is the audit trail immutable? What if someone recomputes every hash?

**Answer:** It is a local hash chain, not immutable storage. The check detects straightforward edits and certain deletions while the necessary local state remains intact. An attacker with full database access can rewrite records and rebuild the chain. Independent anchoring, protected storage and access controls would be needed to strengthen that guarantee. The chain check also does not independently verify the separate cases table.

### Q19. Can the exported report independently prove every event is valid?

**Answer:** The current export is a summary with activity counts, reviewer metrics, the integrity result and the ledger tip hash. It does not include the complete raw event history needed to recompute every link independently. An external verifier would need the underlying events and a trusted reference point. The report also cannot prove that unrecorded events never happened.

### Q20. Why allow a failed integrity report to be downloaded?

**Answer:** A detected inconsistency is evidence worth retaining, so a report can be generated with a clear FAIL result. That is different from a verification execution error or report-generation failure. Those failures leave no valid export bundle, and the download controls stay disabled. We do not replace a failed check with a simulated pass.

### Q21. What if two reviewers submit the same case, or routing fails halfway through?

**Answer:** A review updates the pending status and appends its audit event in one SQLite write transaction. A duplicate or competing submission is rejected when the case is no longer pending. Prediction and gate recording are separate transactions: if the prediction saves but the gate does not, the case remains pending for manual review and the failure is shown. We have not established high-volume production scalability.

### Q22. Are reports and metrics read from one atomic database snapshot?

**Answer:** No. The report module offers a combined builder, but the current page still calls the JSON and Markdown interfaces separately. It compares their report identifiers and the integrity result, which can detect some changes but does not provide an atomic snapshot. The underlying reads also use separate transactions. We finish the reviews before exporting in this demo; a stronger implementation would coordinate the snapshot and use the combined builder.

### Q23. How do you authenticate reviewers or verify attention time?

**Answer:** The current application records a reviewer name entered in a form. It does not authenticate that identity in the application. Elapsed time can include time away from the page, and reasons can be superficial. These are recorded signals, not verified attention. Authentication, role-based access and stronger evidence collection would be necessary before relying on the records operationally.

### Q24. Why do batch Case IDs and review Application IDs look different?

**Answer:** The batch shows the stored case identifier, while the review page displays a deterministic APP alias derived from it. Submission still uses the original case identifier, so the records remain linked. The alias is a display convention, not encryption or a security boundary. Gold cases also have a visible demonstration marker.

### Q25. Can repeated batches contain the same applicants?

**Answer:** They can contain the same dataset rows. Sampling uses a fixed random seed, and each run creates new case identifiers. We currently have no source-row deduplication. This is useful for reproducible demonstrations, but we would need stable source identities and an explicit reprocessing policy for an operational workflow.

### Q26. Is the model fair, especially if it uses age, sex or foreign-worker status?

**Answer:** We have not established fairness or suitability for deployment. The baseline retains the original dataset inputs, including sensitive demographic information. Before any operational use, we would need a review of permissible inputs, representative data, subgroup performance and calibration, and an appropriate governance assessment. The current model is a demonstration component, not an approved lending system.

### Q27. Are you compliant with the EU AI Act or ISO/IEC 42001?

**Answer:** We provide a technical evidence summary and a high-level mapping to topics such as logging, transparency and human oversight. We have not established legal applicability, conformity or certification. Those require an assessment of the actual system, its use and organizational controls beyond this prototype.

### Q28. Why did you leave out the authorized-exception control case?

**Answer:** We found an inconsistency: its scenario text suggests changing the AI rejection, while its current stored expected answer is also rejection. We did not silently rewrite that historical record or use it as evidence of successful error detection. The script uses clearer examples. The template's wording and expected answer need to be reconciled before a formal evaluation.

### Q29. Who is this for, and what would you validate next?

**Answer:** The intended users are teams running AI-assisted review processes and people responsible for examining their records. We have not validated customer demand or commercial impact. Our next evaluation would use domain-reviewed, balanced controls and a study of real reviewer behavior, including false overrides and ordinary-case outcomes. We would also strengthen identity, evidence-handling and audit protections.

## 4. Recovery lines for the presenter

Use one relevant line, then continue. Do not claim an operation succeeded unless its result is visible or available in the saved evidence.

**Batch counts differ:**

“We will use the counts shown on this run. The routing rules are unchanged: triggered conditions go to human review, and the other cases retain their automatic routing.”

**The exact ordinary example is unavailable:**

“We will use another ordinary application below the confidence threshold. The explanation and review process are the same, and we will read its actual values.”

**A control was already reviewed:**

“That control has already left the pending queue after a saved decision. I will use the remaining prepared control, or show its recorded result in the evidence summary.”

**The copy file already exists:**

“The script refuses to overwrite an existing copy. We will use a new output filename so the original and previous evidence remain intact.”

**The browser or service is unavailable:**

“The live interface is unavailable at the moment. We can show the saved backend rehearsal report, which is clearly identified as the prepared sixteen-case dataset. It does not contain the live batch we have just attempted.”

**Report generation fails:**

“The application has not produced a valid report bundle, so the downloads remain disabled. We will retain the error and use the prepared rehearsal evidence, without presenting it as a new live export.”

## 5. Quick reference and final checks

- The 50-case batch uses 45 model predictions plus five scripted controls. Rehearsed routing: 27 automatic approvals, five automatic rejections, 18 manual cases.
- Initial cumulative count: 16. After the one live batch: 66. After the three planned live reviews: 17 total completed reviews and 15 pending cases, assuming no other activity.
- The clean rehearsal starts with 46 events. The live batch adds 100, and three reviews add three: the final live report should contain 149 events if no other events were added.
- Live reviews: **live_reviewer** only. Do not submit under **careful_reviewer**, **rubber_stamp** or **demo_judge**.
- Long reasons in the script are examples of recorded explanations; their length does not prove substance.
- Model sample amounts remain dataset units. Historical account/savings bands refer to original DM units, not current pounds or euros.
- Actual probabilities and labels must be checked on screen. The model metrics in Q3 come from the saved artifact; do not describe them as human-review results.
- The source script's previously verified backend rehearsal does not replace a complete browser rehearsal of these exact steps.
- Rehearse this script aloud once, including the case lookup, hover pauses, report download and second-port switch. Read no code aloud.

### Implementation references

- [Model and confidence calculation](../loopledger/model.py)
- [Risk gate](../loopledger/gate.py)
- [Current gold templates](../loopledger/gold.py)
- [Persisted reviewer metrics](../loopledger/metrics.py)
- [Review interface and hover explanations](../pages/2_Review_Queue.py)
- [Report generation and limitations](../loopledger/evidence.py)
- [Isolated rehearsal](../scripts/demo_check.py)
- [Copy-only tamper demonstration](../scripts/demo_tamper.py)
