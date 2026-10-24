"""A：金标准测试题，待实现。"""
"""Synthetic gold-standard reviewer challenges. Never use them as real loans."""
from copy import deepcopy
GOLD=[
    {"case_id":"GOLD-001","scenario":"Missing identity verification",
     "applicant_summary":{"credit_amount":3000,"identity_verified":False},
     "ai_recommendation":"approve","expected_action":"request_more",
     "rationale":"Demo policy requires identity verification."},
    {"case_id":"GOLD-002","scenario":"High amount; extra proof is missing",
     "applicant_summary":{"credit_amount":25000,"identity_verified":True,"extra_proof":False},
     "ai_recommendation":"approve","expected_action":"request_more",
     "rationale":"Demo policy requires additional verification for a large loan."},
    {"case_id":"GOLD-003","scenario":"All exercise policy checks are met",
     "applicant_summary":{"credit_amount":2500,"identity_verified":True,"policy_checks_passed":True},
     "ai_recommendation":"approve","expected_action":"approve",
     "rationale":"All mandatory demo policy checks passed."},
    {"case_id":"GOLD-004","scenario":"AI denies despite valid documented exception",
     "applicant_summary":{"credit_amount":3000,"identity_verified":True,"authorized_exception":True},
     "ai_recommendation":"reject","expected_action":"approve",
     "rationale":"Verified authorization is recorded in this exercise."},
    {"case_id":"GOLD-005","scenario":"Application disagrees with proof",
     "applicant_summary":{"credit_amount":8000,"identity_verified":True,"document_amount":1000},
     "ai_recommendation":"approve","expected_action":"request_more",
     "rationale":"Inconsistent supporting documentation requires investigation."},
    {"case_id":"GOLD-006","scenario":"Synthetic confirmed identity fraud",
     "applicant_summary":{"credit_amount":2000,"identity_verified":False,"fraud_confirmed":True},
     "ai_recommendation":"approve","expected_action":"reject",
     "rationale":"Confirmed fraud is a rejection condition under the demo policy."}
]
ACTIONS={"approve","reject","request_more"}
def get_gold_cases(n=5, include_answers=False):
    if not isinstance(n,int) or n<0: raise ValueError("n must be nonnegative integer")
    cases=deepcopy(GOLD[:n])
    if not include_answers:
        for case in cases:
            case.pop("expected_action",None)
            case.pop("rationale",None)
    return cases
def evaluate_gold_review(case_id, reviewer_action):
    if reviewer_action not in ACTIONS:
        raise ValueError(f"Invalid action: {reviewer_action}")
    match=next((c for c in GOLD if c["case_id"]==case_id),None)
    if match is None: raise ValueError(f"Unknown case: {case_id}")
    return {"case_id":case_id,"reviewer_action":reviewer_action,
            "expected_action":match["expected_action"],
            "is_correct":reviewer_action==match["expected_action"],
            "ai_error_detected":(match["ai_recommendation"]!=match["expected_action"]
                                 and reviewer_action==match["expected_action"]),
            "rationale":match["rationale"],"synthetic_test":True}
def summarize_gold_reviews(reviews):
    assessed=[evaluate_gold_review(r["case_id"],r["reviewer_action"]) for r in reviews]
    correct=sum(r["is_correct"] for r in assessed)
    return {"total":len(assessed),"correct":correct,
            "accuracy":round(correct/len(assessed),3) if assessed else None,
            "missed_cases":[r["case_id"] for r in assessed if not r["is_correct"]]}
if __name__=="__main__":
    import json
    print(json.dumps(get_gold_cases(5),indent=2))
