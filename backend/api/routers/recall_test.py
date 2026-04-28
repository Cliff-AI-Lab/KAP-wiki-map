"""
召回测试 API 路由模块。

提供检索效果的详细测试接口，支持自定义检索权重、评分阈值过滤，
以及基于期望文档ID的评估指标计算（Recall@K、Precision@K、MRR）。
主要供开发和运维人员调试检索质量使用。

路由前缀: /knowledge
"""

from __future__ import annotations

import time

from fastapi import APIRouter

from api.deps import get_retriever
from api.schemas.recall_test import (
    RecallTestRequest,
    RecallTestResponse,
    ScoreBreakdown,
)
from packages.common import settings

router = APIRouter(prefix="/knowledge", tags=["召回测试"])


@router.post("/recall-test", response_model=RecallTestResponse)
async def recall_test(req: RecallTestRequest) -> RecallTestResponse:
    """
    召回测试端点 — 详细测试检索效果，返回评分拆解。

    处理流程：
    1. 解析权重参数（alpha/beta/gamma/delta），未指定时使用全局默认值
    2. 执行混合检索（向量 + 图谱 + 目录 + 关键词）
    3. 构建每条结果的详细评分拆解（各维度分数）
    4. 应用可选的分数阈值过滤
    5. 若提供了期望文档ID，计算 Recall@K、Precision@K、MRR 评估指标

    权重说明：
    - alpha: 向量检索权重
    - beta: 图谱检索权重
    - gamma: 目录权重
    - delta: 关键词检索权重
    """
    start = time.time()
    retriever = get_retriever()

    # 解析实际生效的权重：请求参数优先，否则使用全局配置
    eff_alpha = req.alpha if req.alpha is not None else settings.score_alpha
    eff_beta = req.beta if req.beta is not None else settings.score_beta
    eff_gamma = req.gamma if req.gamma is not None else settings.score_gamma
    eff_delta = req.delta if req.delta is not None else settings.score_delta

    # 执行检索：scope 为 "folder" 时限定在指定目录下检索
    target_category = req.scope_value if req.scope == "folder" else None
    results = await retriever.search(
        query=req.query,
        top_k=req.top_k,
        target_category=target_category,
    )

    # 构建详细评分拆解，内容截断为500字
    breakdowns = [
        ScoreBreakdown(
            chunk_id=r.chunk_id,
            doc_id=r.doc_id,
            title=r.title,
            content=r.content[:500],
            final_score=r.score,
            vector_score=r.vector_score,
            graph_score=r.graph_score,
            catalog_weight=r.catalog_weight,
            keyword_score=r.keyword_score,
            category_path=r.category_path,
        )
        for r in results
    ]

    # 应用分数阈值：过滤掉低于阈值的结果
    if req.score_threshold is not None:
        breakdowns = [b for b in breakdowns if b.final_score >= req.score_threshold]

    # ── 计算评估指标（需提供 expected_doc_ids） ──────────
    recall_at_k = None
    precision_at_k = None
    mrr = None
    hit_expected: list[str] = []
    missed_expected: list[str] = []

    if req.expected_doc_ids:
        expected = set(req.expected_doc_ids)
        retrieved_doc_ids = [b.doc_id for b in breakdowns]
        retrieved_set = set(retrieved_doc_ids)

        hit_expected = list(expected & retrieved_set)       # 命中的期望文档
        missed_expected = list(expected - retrieved_set)    # 未召回的期望文档
        recall_at_k = len(hit_expected) / len(expected) if expected else 0.0
        precision_at_k = len(hit_expected) / len(breakdowns) if breakdowns else 0.0

        # MRR（Mean Reciprocal Rank）: 第一个命中期望文档的倒数排名
        mrr = 0.0
        for i, doc_id in enumerate(retrieved_doc_ids):
            if doc_id in expected:
                mrr = 1.0 / (i + 1)
                break

    latency = int((time.time() - start) * 1000)  # 计算接口耗时（毫秒）

    return RecallTestResponse(
        query=req.query,
        mode=req.mode,
        scope=req.scope,
        total_hits=len(breakdowns),
        results=breakdowns,
        latency_ms=latency,
        effective_weights={
            "alpha": eff_alpha,
            "beta": eff_beta,
            "gamma": eff_gamma,
            "delta": eff_delta,
        },
        recall_at_k=recall_at_k,
        precision_at_k=precision_at_k,
        mrr=mrr,
        hit_expected=hit_expected,
        missed_expected=missed_expected,
    )
