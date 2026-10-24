"""A: Risk gate. Uses shared Prediction/GateResult contract; no loan execution."""
import math
try:
    from .schemas import Prediction, GateResult
except ImportError:
    from schemas import Prediction, GateResult

MIN_CONFIDENCE=0.70
LARGE_LOAN=15000

def evaluate_risk(application: dict, prediction: Prediction) -> GateResult:
    """Fail closed on invalid/unsupported inputs; thresholds are demonstration policy."""
    if not isinstance(prediction, Prediction):
        raise TypeError("prediction must be a shared_types.Prediction")
    reasons=[]
    try:
        confidence=float(prediction.confidence)
        if not math.isfinite(confidence) or not 0.5<=confidence<=1:
            reasons.append("Invalid prediction confidence")
        elif confidence<MIN_CONFIDENCE:
            reasons.append(f"Low model confidence (< {MIN_CONFIDENCE})")
    except (TypeError,ValueError):
        reasons.append("Invalid prediction confidence")
    try:
        amount=float(application.get("credit_amount"))
        if not math.isfinite(amount) or amount<=0 or amount>1000000:
            reasons.append("Invalid credit amount")
        elif amount>LARGE_LOAN:
            reasons.append(f"Large loan amount (> {LARGE_LOAN})")
    except (TypeError,ValueError):
        reasons.append("Invalid credit amount")
    if application.get("identity_verified") is not True:
        reasons.append("Identity verification missing")
    if application.get("case_id")!=prediction.case_id:
        reasons.append("Case ID mismatch")
    if prediction.decision not in ("approve","reject"):
        reasons.append("Invalid AI decision")
    # Gold exercises always go to human reviewers, even when amount/confidence seem safe.
    if prediction.is_gold:
        reasons.append("Gold-standard oversight test")
    return GateResult(needs_review=bool(reasons),reasons=reasons)

if __name__=="__main__":
    from dataclasses import asdict
    import json
    try:
        from .model import predict, EXAMPLE_APPLICATION
    except ImportError:
        from model import predict, EXAMPLE_APPLICATION
    print(json.dumps(asdict(evaluate_risk(EXAMPLE_APPLICATION,predict(EXAMPLE_APPLICATION))),
                     indent=2,ensure_ascii=False))
