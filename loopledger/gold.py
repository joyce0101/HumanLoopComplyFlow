"""A: Synthetic gold cases for human oversight.

The team's `modify` action means change/hold AI's proposed decision (including
requesting missing evidence), not automatically approving a loan.
Answer keys MUST remain backend-only; never serialize gold_correct_decision to UI.
"""
from dataclasses import asdict
try:
    from .schemas import Prediction
except ImportError:
    from schemas import Prediction

_CASES = [
    ("GOLD-001", "Identity verification missing", 3000, False, "approve", "modify",
     "Require ID verification before any approval.", {}),
    ("GOLD-002", "High amount without extra proof", 25000, True, "approve", "modify",
     "Large loans require an additional review/documentation step.", {"extra_proof":False}),
    ("GOLD-003", "All simulated policy checks passed", 2500, True, "approve", "approve",
     "All stated checks pass under this synthetic demo policy.", {"policy_checks_passed":True}),
    ("GOLD-004", "Authorized exception contradicts AI rejection", 3000, True, "reject", "modify",
     "Reviewer should change the AI's decision and examine the exception.",
     {"authorized_exception":True}),
    ("GOLD-005", "Claim and supporting document differ", 8000, True, "approve", "modify",
     "Investigate the inconsistent supporting documentation.", {"document_amount":1000}),
    ("GOLD-006", "Confirmed fraudulent identity in synthetic case", 2000, False,
     "approve", "reject", "Confirmed fraud triggers denial under demo policy.",
     {"fraud_confirmed":True}),
]

_ANSWERS={row[0]:(row[5],row[6],row[4]) for row in _CASES}
VALID_ACTIONS={"approve","reject","modify"}

def get_gold_cases(n: int = 5, include_answers: bool = False) -> list[Prediction]:
    """Return team's Prediction type. Default masks answer key for reviewer UI."""
    if not isinstance(n,int) or n<0:
        raise ValueError("n must be a nonnegative integer")
    output=[]
    for case_id, scenario, amount, verified, ai, expected, rationale, extra in _CASES[:n]:
        output.append(Prediction(
            case_id=case_id,
            features={"credit_amount":amount,"identity_verified":verified,
                      "scenario":scenario,**extra},
            decision=ai,
            confidence=0.95,  # scripted for demo; NOT an actual model probability
            top_factors=[],
            is_gold=True,
            gold_correct_decision=expected if include_answers else None
        ))
    return output

def make_gold_cases(n: int) -> list[Prediction]:
    """符合 PLAN.md 3.2 的服务端金标准生成接口。

    B 的 ledger.py 明确要求 gold_correct_decision 不得为 None，
    所以这里使用 include_answers=True。此对象仅允许交给可信持久层；
    前端不可直接序列化或展示这份对象，应过滤正确答案和 is_gold 标记。
    """
    return get_gold_cases(n, include_answers=True)


def public_review_payload(case: Prediction) -> dict:
    """Allowlist safe fields; always strips is_gold and gold_correct_decision."""
    return {"case_id":case.case_id,"features":case.features,"decision":case.decision,
            "confidence":case.confidence,"top_factors":case.top_factors}

def evaluate_gold_review(case_id: str, reviewer_action: str) -> dict:
    if reviewer_action not in VALID_ACTIONS:
        raise ValueError(f"Action must be one of {sorted(VALID_ACTIONS)}")
    if case_id not in _ANSWERS:
        raise ValueError(f"Unknown gold case: {case_id}")
    expected, rationale, ai = _ANSWERS[case_id]
    return {"case_id":case_id,"reviewer_action":reviewer_action,
            "expected_action":expected,
            "is_correct":reviewer_action==expected,
            "ai_error_detected":ai!=expected and reviewer_action==expected,
            "rationale":rationale,
            "synthetic_test":True}

def summarize_gold_reviews(reviews: list[dict]) -> dict:
    assessed=[evaluate_gold_review(r["case_id"],r["reviewer_action"]) for r in reviews]
    count=len(assessed)
    correct=sum(x["is_correct"] for x in assessed)
    return {"total":count,"correct":correct,
            "accuracy":round(correct/count,3) if count else None,
            "missed_cases":[x["case_id"] for x in assessed if not x["is_correct"]]}

if __name__=="__main__":
    import json
    print(json.dumps([public_review_payload(p) for p in get_gold_cases(5)],
                     indent=2,ensure_ascii=False))
