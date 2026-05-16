"""实体消歧（M22 #5）— 候选合并 lite。

候选合并算法：
- 字符串相似度（归一化编辑距离 Levenshtein / 字符级共现）
- 可选 embedding cosine 相似度（caller 传入向量）
- type_id 不同的实体**绝不合并**（不同语义类型）
- L1 实体类型组成的实体（行业本体级）默认不在候选中，需要 caller 显式声明
  本模块通过 `l1_type_ids` 参数排除

输出：MergeCandidate 列表，由 SME 经 4×6 矩阵审核 + decision_log 仲裁。
绝不自动合并（决策书 D12 人工兜底）。

LLM 仲裁接口预留：高歧义对（字符串差大但 embedding 近）可调 `llm_arbitrate_merge`,
本 M22 #5 lite 留接口未实现。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from packages.common import get_logger
from packages.common.types import ExtractedEntity

log = get_logger("extraction.entity_resolver")


@dataclass
class MergeCandidate:
    """实体合并候选对。"""
    entity_a_id: str
    entity_b_id: str
    entity_a_name: str
    entity_b_name: str
    type_id: str               # 必须相等
    string_similarity: float   # 0-1, 1 = 完全相同
    vector_similarity: float | None = None  # 0-1, None 表示未提供向量
    score: float = 0.0         # 综合分（caller 可自定义权重）


def _normalized_edit_distance(s1: str, s2: str) -> float:
    """返回归一化字符串相似度（0-1）, 1 = 完全相同。

    用经典 Levenshtein, 不依赖外部库, 中英文混合可用。
    """
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0

    m, n = len(s1), len(s2)
    # DP rolling array
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        curr = [i] + [0] * n
        for j in range(1, n + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    distance = prev[n]
    max_len = max(m, n)
    return 1.0 - (distance / max_len)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def find_merge_candidates(
    entities: list[ExtractedEntity],
    embeddings: dict[str, list[float]] | None = None,
    string_threshold: float = 0.85,
    vector_threshold: float = 0.92,
    l1_type_ids: set[str] | None = None,
) -> list[MergeCandidate]:
    """扫描实体列表找合并候选对。

    Args:
        entities: 待消歧实体
        embeddings: {entity_id → vector}, 可选; 提供时启用向量相似度
        string_threshold: 字符串相似度阈值, 高于此值进候选
        vector_threshold: 向量相似度阈值, 与字符串"或"关系（任一满足即候选）
        l1_type_ids: L1 行业本体实体类型集合; L1 类型的实体不参与合并候选
            （行业本体不可漂移）

    Returns:
        MergeCandidate 列表, 按 score 降序
    """
    l1_set = l1_type_ids or set()
    candidates: list[MergeCandidate] = []

    n = len(entities)
    for i in range(n):
        a = entities[i]
        if a.type_id in l1_set:
            continue
        for j in range(i + 1, n):
            b = entities[j]
            # 类型必须一致, 且非 L1
            if a.type_id != b.type_id or b.type_id in l1_set:
                continue
            if a.entity_id == b.entity_id:
                continue

            str_sim = _normalized_edit_distance(a.name, b.name)
            vec_sim: float | None = None
            if embeddings:
                ea = embeddings.get(a.entity_id)
                eb = embeddings.get(b.entity_id)
                if ea and eb:
                    vec_sim = _cosine(ea, eb)

            # 候选条件: 字符串或向量任一过阈
            hit_str = str_sim >= string_threshold
            hit_vec = vec_sim is not None and vec_sim >= vector_threshold
            if not (hit_str or hit_vec):
                continue

            # score = 字符串和向量加权（向量优先, 字符串 fallback）
            if vec_sim is not None:
                score = 0.6 * vec_sim + 0.4 * str_sim
            else:
                score = str_sim

            candidates.append(MergeCandidate(
                entity_a_id=a.entity_id, entity_b_id=b.entity_id,
                entity_a_name=a.name, entity_b_name=b.name,
                type_id=a.type_id,
                string_similarity=str_sim,
                vector_similarity=vec_sim,
                score=score,
            ))

    candidates.sort(key=lambda c: c.score, reverse=True)
    log.info("entity_resolver_done",
             total_entities=len(entities), candidates=len(candidates))
    return candidates


# ── LLM 仲裁接口（lite 模式预留，M23 实现）────────────────


async def llm_arbitrate_merge(
    candidate: MergeCandidate,
    context_a: str = "",
    context_b: str = "",
) -> tuple[bool, str]:
    """高歧义对的 LLM 仲裁（lite 模式未实现, 调用直接返回 False + 提示）。

    M23 候选: 接 acall_llm_json 实现, prompt 给 LLM 看候选对的周边上下文
    （context_a/b 来自 build_context_window）, LLM 回答是否合并 + 理由。
    """
    return False, "M22 #5 lite: LLM 仲裁未实现, 候选对仍需 SME 经 governance API 审核"
