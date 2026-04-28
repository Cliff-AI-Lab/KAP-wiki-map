"""双路径查询路由器 (QueryRouter) — V11 知识图鉴核心。

根据查询复杂度和 Wiki 可用性，决定走 Wiki 快路径还是 RAG 深路径。
这是知识图鉴第一原则"双引擎架构"的检索层实现。

路由逻辑:
- Wiki路径: 简单/直接/概览问题 + 目标域有Wiki页 + SkillsRouter置信度>0.7
- RAG路径: 复杂/跨域/精确数值问题 + 无Wiki页 + 置信度<0.5
- Hybrid: 重要问题 → Wiki先答 + RAG验证

类比: Wiki = CPU L1缓存 (预编译,秒读) / RAG = 内存 (原始分块,需检索组装)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from packages.common import get_logger
from packages.common.types import RouteDecision

if TYPE_CHECKING:
    from packages.storage.wiki_store import WikiStore

log = get_logger("retrieval.query_router")

# 复杂查询特征关键词
_COMPLEX_INDICATORS = [
    "对比", "比较", "区别", "和.*有什么不同",
    "分别", "同时", "多个", "所有",
    "具体.*数值", "精确", "参数",
    "多少度", "多少MPa", "浓度",
]

# 简单查询特征关键词
_SIMPLE_INDICATORS = [
    "是什么", "什么是", "包含哪些", "有哪些",
    "概述", "简介", "总结", "说明",
    "频率", "标准", "要求", "规定",
    "流程", "步骤",
]


class QueryRouter:
    """双路径查询路由器。

    核心理念（第一原则）:
    - 简单查询走 Wiki 快路径 → 秒级响应，低 Token
    - 复杂查询走 RAG 深路径 → 全面深入，多文档综合
    - 重要查询双路径交叉验证 → 高置信度
    """

    def __init__(self, wiki_store: WikiStore):
        self.wiki_store = wiki_store

    async def route(
        self,
        question: str,
        domain_path: str,
        confidence: float,
        project_id: str = "default",
    ) -> RouteDecision:
        """判断查询走哪条路径。

        Args:
            question: 用户问题
            domain_path: SkillsRouter 返回的域路径
            confidence: SkillsRouter 的置信度
            project_id: 项目 ID

        Returns:
            RouteDecision(path="wiki"|"rag"|"hybrid")
        """
        # Step 1: 检查目标域是否有编译好的 Wiki 页
        wiki_available = False
        wiki_page_id = None
        if domain_path:
            page = await self.wiki_store.get_page(domain_path, project_id)
            if page and page.status == "published":
                wiki_available = True
                wiki_page_id = domain_path

        # Step 2: 评估查询复杂度
        complexity = self._assess_complexity(question)

        # Step 3: 路由决策
        if not wiki_available:
            # 无 Wiki 页 → 只能走 RAG
            return RouteDecision(
                path="rag",
                confidence=confidence,
                reason="目标域无编译Wiki页",
            )

        if complexity == "low" and confidence >= 0.7:
            # 简单查询 + 高置信域匹配 + Wiki 可用 → Wiki 快路径
            return RouteDecision(
                path="wiki",
                wiki_page_id=wiki_page_id,
                confidence=confidence,
                reason=f"简单查询，Wiki页可直接回答 (域置信度{confidence:.2f})",
            )

        if complexity == "high":
            # 复杂查询 → RAG 深路径
            return RouteDecision(
                path="rag",
                confidence=confidence,
                reason=f"复杂/跨域查询，需RAG深度检索",
            )

        # 中等复杂度或中等置信度 → 混合路径
        return RouteDecision(
            path="hybrid",
            wiki_page_id=wiki_page_id,
            confidence=confidence,
            reason=f"中等复杂度，Wiki先答RAG补充 (域置信度{confidence:.2f})",
        )

    def _assess_complexity(self, question: str) -> str:
        """评估查询复杂度: low / medium / high。

        low: 单域直接查询/概览/简单事实
        medium: 需要一定综合但不跨域
        high: 跨域对比/精确数值/多文档综合
        """
        q = question.lower()

        # 检查复杂特征
        complex_score = sum(
            1 for pattern in _COMPLEX_INDICATORS
            if re.search(pattern, q)
        )

        # 检查简单特征
        simple_score = sum(
            1 for pattern in _SIMPLE_INDICATORS
            if re.search(pattern, q)
        )

        if complex_score >= 2:
            return "high"
        if complex_score >= 1 and simple_score == 0:
            return "high"
        if simple_score >= 1 and complex_score == 0:
            return "low"
        if len(question) > 50 and complex_score >= 1:
            return "high"

        return "medium"
