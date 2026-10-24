"""A：风险闸门，待实现。"""
"""Explicit, demonstrative policy routing; not an authorization to issue loans."""
import math
POLICY_VERSION="demo-gate-v2"
MIN_CONFIDENCE=0.70
LARGE_LOAN=15000

def evaluate_risk(application:dict,prediction:dict)->dict:
    reasons=[]
    try:
        conf=float(prediction.get("confidence"))
        if not math.isfinite(conf) or not 0.5<=conf<=1:
            reasons.append("Missing or invalid model confidence")
        elif conf<MIN_CONFIDENCE:
            reasons.append(f"Low model confidence (< {MIN_CONFIDENCE})")
    except (TypeError,ValueError):
        reasons.append("Missing or invalid model confidence")
    try:
        amount=float(application.get("credit_amount"))
        if not math.isfinite(amount) or not 0<amount<=1000000:
            reasons.append("Invalid credit amount")
        elif amount>LARGE_LOAN:
            reasons.append(f"Large loan amount (> {LARGE_LOAN})")
    except (TypeError,ValueError):
        reasons.append("Invalid credit amount")
    if application.get("identity_verified") is not True:
        reasons.append("Identity verification missing")
    if prediction.get("decision_id")!=application.get("decision_id"):
        reasons.append("Decision ID mismatch")
    if prediction.get("prediction") not in {"approve","reject"}:
        reasons.append("Missing AI recommendation")
    if not prediction.get("model_version"):
        reasons.append("Missing model version")
    blocked=bool(reasons)
    return {
        "decision_id":str(application.get("decision_id","UNASSIGNED")),
        "policy_version":POLICY_VERSION,
        "risk_level":"high" if blocked else "low",
        "requires_human_review":blocked,
        "reasons":reasons,
        "status":"pending_review" if blocked else "eligible_for_auto_processing",
        "note":"Backend must enforce authorization; this does not execute a loan."
    }

if __name__=="__main__":
    import json
    from model import predict, EXAMPLE_APPLICATION
    print(json.dumps(evaluate_risk(EXAMPLE_APPLICATION,predict(EXAMPLE_APPLICATION)),indent=2))
