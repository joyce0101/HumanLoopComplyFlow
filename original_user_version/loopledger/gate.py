"""A: Risk gate. Uses shared Prediction/GateResult contract; no loan execution."""
import math
try:
    from .schemas import Prediction, GateResult
except ImportError:
    from schemas import Prediction, GateResult

MIN_CONFIDENCE=0.70
LARGE_LOAN=15000

def check(pred: Prediction) -> GateResult:
    """团队 PLAN.md 3.2 标准接口：只传入 Prediction 对象。

    业务申请信息直接从 pred.features 读取；异常或缺失字段会触发人工审核。
    本闸门不执行任何真实贷款审批。
    """
    if not isinstance(pred, Prediction):
        raise TypeError("pred 必须是 schemas.Prediction")
    return evaluate_risk(pred.features, pred)


def evaluate_risk(application: dict, prediction: Prediction) -> GateResult:
    """Fail closed on invalid/unsupported inputs; thresholds are demonstration policy."""
    if not isinstance(prediction, Prediction):
        raise TypeError("prediction must be a schemas.Prediction")
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
    if "case_id" in application and application.get("case_id")!=prediction.case_id:
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
    print(json.dumps(asdict(check(predict(EXAMPLE_APPLICATION, "LOAN-001"))),
                     indent=2,ensure_ascii=False))
