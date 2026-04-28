"""意图路由引擎 — 查询意图分类与检索策略路由。

根据用户查询的意图类型，调整检索参数（top_k、权重偏好、目标目录等），
使不同类型的问题获得最优检索策略。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from packages.common import get_logger

log = get_logger("retrieval.intent")


class QueryIntent(str, Enum):
    """查询意图类别。"""
    REGULATION = "regulation"       # 制度查询：规章制度、管理办法
    PROCESS = "process"             # 流程查询：操作步骤、审批流程
    TECHNICAL = "technical"         # 技术问题：部署、配置、架构
    PERSON = "person"               # 人员查询：负责人、联系方式
    FACTUAL = "factual"             # 事实查询：具体数据、指标
    EXPLORATORY = "exploratory"     # 探索性查询：概述、总结
    GENERAL = "general"             # 通用查询


@dataclass
class RoutingResult:
    """路由结果 — 包含意图分类和调整后的检索参数。"""
    intent: QueryIntent
    confidence: float
    suggested_top_k: int = 5
    suggested_category: str | None = None
    # 评分权重覆盖（None 表示使用默认值）
    alpha_override: float | None = None   # 向量权重
    beta_override: float | None = None    # 图谱权重
    gamma_override: float | None = None   # 目录权重
    delta_override: float | None = None   # 关键词权重


# 意图识别规则（关键词 → 意图）
_INTENT_RULES: list[tuple[list[str], QueryIntent, float]] = [
    # 制度查询
    (
        ["制度", "规定", "管理办法", "规章", "政策", "条例", "准则", "规范"],
        QueryIntent.REGULATION,
        0.85,
    ),
    # 流程查询
    (
        ["流程", "怎么办", "如何", "步骤", "操作", "指南", "审批", "报销怎么",
         "入职", "离职", "请假", "出差"],
        QueryIntent.PROCESS,
        0.85,
    ),
    # 技术问题
    (
        ["部署", "配置", "安装", "代码", "接口", "API", "Docker", "数据库",
         "服务器", "报错", "异常", "bug", "架构", "技术方案"],
        QueryIntent.TECHNICAL,
        0.80,
    ),
    # 人员查询
    (
        ["谁负责", "联系方式", "负责人", "找谁", "对接人", "主管"],
        QueryIntent.PERSON,
        0.90,
    ),
    # 事实查询
    (
        ["多少", "几个", "什么时候", "日期", "数量", "金额", "比例", "指标"],
        QueryIntent.FACTUAL,
        0.75,
    ),
    # 探索性查询
    (
        ["介绍", "概述", "总结", "有哪些", "了解", "什么是", "解释"],
        QueryIntent.EXPLORATORY,
        0.70,
    ),
]

# 意图对应的检索策略（四通道权重之和为 1.0）
_INTENT_STRATEGIES: dict[QueryIntent, dict] = {
    QueryIntent.REGULATION: {
        "top_k": 3,
        "alpha": 0.30, "beta": 0.15, "gamma": 0.35, "delta": 0.20,
    },
    QueryIntent.PROCESS: {
        "top_k": 5,
        "alpha": 0.35, "beta": 0.20, "gamma": 0.20, "delta": 0.25,
    },
    QueryIntent.TECHNICAL: {
        "top_k": 8,
        "alpha": 0.40, "beta": 0.25, "gamma": 0.10, "delta": 0.25,
    },
    QueryIntent.PERSON: {
        "top_k": 5,
        "alpha": 0.25, "beta": 0.40, "gamma": 0.15, "delta": 0.20,
    },
    QueryIntent.FACTUAL: {
        "top_k": 3,
        "alpha": 0.35, "beta": 0.20, "gamma": 0.15, "delta": 0.30,
    },
    QueryIntent.EXPLORATORY: {
        "top_k": 10,
        "alpha": 0.35, "beta": 0.20, "gamma": 0.20, "delta": 0.25,
    },
    QueryIntent.GENERAL: {
        "top_k": 5,
        "alpha": None, "beta": None, "gamma": None, "delta": None,
    },
}

# 意图 → 建议目录前缀映射
_INTENT_CATEGORY_HINTS: dict[QueryIntent, list[str]] = {
    QueryIntent.REGULATION: ["规章制度", "管理制度"],
    QueryIntent.PROCESS: ["流程说明", "操作指南"],
    QueryIntent.TECHNICAL: ["技术文档", "部署文档"],
}


def classify_intent(query: str) -> RoutingResult:
    """对查询进行意图分类并返回路由结果。

    使用基于规则的关键词匹配。在 PoC 阶段避免额外 LLM 调用开销，
    后续可替换为 LLM-based intent classifier。
    """
    query_lower = query.lower()
    best_intent = QueryIntent.GENERAL
    best_confidence = 0.0
    best_match_count = 0

    for keywords, intent, base_confidence in _INTENT_RULES:
        match_count = sum(1 for kw in keywords if kw in query_lower)
        if match_count > 0:
            # 匹配关键词越多，置信度越高
            confidence = min(base_confidence + match_count * 0.05, 0.99)
            if match_count > best_match_count or (
                match_count == best_match_count and confidence > best_confidence
            ):
                best_intent = intent
                best_confidence = confidence
                best_match_count = match_count

    if best_intent == QueryIntent.GENERAL:
        best_confidence = 0.5

    # 根据意图选择检索策略
    strategy = _INTENT_STRATEGIES.get(best_intent, _INTENT_STRATEGIES[QueryIntent.GENERAL])

    # 尝试匹配建议目录
    suggested_category = None
    if best_intent in _INTENT_CATEGORY_HINTS:
        for cat in _INTENT_CATEGORY_HINTS[best_intent]:
            if cat in query:
                suggested_category = cat
                break

    result = RoutingResult(
        intent=best_intent,
        confidence=best_confidence,
        suggested_top_k=strategy["top_k"],
        suggested_category=suggested_category,
        alpha_override=strategy.get("alpha"),
        beta_override=strategy.get("beta"),
        gamma_override=strategy.get("gamma"),
        delta_override=strategy.get("delta"),
    )

    log.info(
        "intent_classified",
        query=query[:80],
        intent=result.intent.value,
        confidence=result.confidence,
    )

    return result
