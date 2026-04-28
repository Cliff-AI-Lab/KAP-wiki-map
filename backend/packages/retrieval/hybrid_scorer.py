"""综合评分引擎 — Score = α·S_vector + β·S_graph + γ·W_cat + δ·S_keyword"""

from __future__ import annotations

from packages.common import get_logger, settings

log = get_logger("retrieval.scorer")


def compute_catalog_weight(doc_path: str, target_path: str) -> float:
    """计算目录匹配权重 W_cat（分层匹配）。

    匹配规则：
    - 完全匹配 = 1.0
    - 父子关系（目标路径是文档路径的父目录或反之）= 0.7
    - 兄弟关系（共享同一父目录）= 0.4
    - 无关 = 0.1
    """
    if not doc_path or not target_path:
        return 0.5  # 无目录信息时给中间权重

    # 清理路径
    doc_parts = [p for p in doc_path.split("/") if p]
    target_parts = [p for p in target_path.split("/") if p]

    # 完全匹配
    if doc_parts == target_parts:
        return 1.0

    # 计算公共前缀长度
    common = 0
    for d, t in zip(doc_parts, target_parts):
        if d == t:
            common += 1
        else:
            break

    if common == 0:
        return 0.1

    # 父子关系：公共前缀 == 较短路径，即一个是另一个的子路径
    if common == min(len(doc_parts), len(target_parts)):
        return 0.7

    # 兄弟关系：公共前缀 == 两者长度 - 1（共享父目录，仅最后一层不同）
    if common == len(doc_parts) - 1 and common == len(target_parts) - 1:
        return 0.4

    # 有公共前缀但不属于上述情况 — 远亲关系
    if common >= 1:
        return 0.3

    return 0.1


def compute_hybrid_score(
    vector_score: float,
    graph_score: float,
    catalog_weight: float,
    keyword_score: float = 0.0,
    alpha: float | None = None,
    beta: float | None = None,
    gamma: float | None = None,
    delta: float | None = None,
) -> float:
    """计算综合评分：α·S_vec + β·S_graph + γ·W_cat + δ·S_keyword"""
    a = alpha if alpha is not None else settings.score_alpha
    b = beta if beta is not None else settings.score_beta
    g = gamma if gamma is not None else settings.score_gamma
    d = delta if delta is not None else settings.score_delta

    score = a * vector_score + b * graph_score + g * catalog_weight + d * keyword_score
    return round(score, 4)
