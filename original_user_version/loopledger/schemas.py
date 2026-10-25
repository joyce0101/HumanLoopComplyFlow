"""共享数据结构：按 PLAN.md 第 3.1 节实现，契约改动需全队同意。"""
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class Prediction:
    """模型预测：A 生成，B 保存。"""

    case_id: str
    features: dict
    decision: Literal["approve", "reject"]
    confidence: float
    top_factors: list[tuple[str, float]]
    is_gold: bool = False
    gold_correct_decision: Optional[str] = None


@dataclass
class GateResult:
    """风险闸门：是否需要人工审核及原因。"""

    needs_review: bool
    reasons: list[str]


@dataclass
class ReviewAction:
    """人工审核操作：C 收集，B 保存。"""

    case_id: str
    reviewer: str
    action: Literal["approve", "reject", "modify"]
    reason: str
    seconds_spent: float
