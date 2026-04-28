"""问答引擎 — 基于检索结果生成结构化回答。

本模块是书虫智能体的核心问答组件，串联了完整的 RAG（检索增强生成）流程：
意图识别 → 知识检索 → 上下文构建 → LLM 回答生成。

主要职责：
- 接收用户问题，通过意图路由确定检索策略
- 调用 BookwormRetriever 进行多模态知识检索
- 将检索结果组装为 LLM 上下文，生成基于证据的回答
- 支持结果缓存以提升重复查询性能

依赖：
- packages.retrieval.retriever: 检索器，负责向量/元数据混合检索
- packages.retrieval.intent_router: 意图分类器，识别用户查询类型
- packages.distillation.llm_client: LLM 调用客户端
- packages.common.types: QAResponse / SearchResult 数据模型
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from packages.common import get_logger
from packages.common.types import QAResponse, SearchResult
from packages.distillation.llm_client import call_llm
from packages.retrieval.intent_router import classify_intent
from packages.retrieval.retriever import BookwormRetriever

if TYPE_CHECKING:
    from packages.retrieval.cache import ResultCache

log = get_logger("qa_engine")

# ── LLM 提示词模板 ──────────────────────────────────────────────

# 系统提示词：约束 LLM 仅基于检索到的参考资料回答，不编造信息
QA_SYSTEM_PROMPT = """你是企业知识库"知识图鉴"的智能问答助手。基于以下检索到的知识片段回答用户问题。

规则：
1. 仅基于提供的参考资料回答，不要编造信息
2. 如果参考资料不足以回答，请如实说明
3. 在回答中引用信息来源（文档标题）
4. 回答应简洁、专业、结构化"""

# 用户提示词模板：将检索到的参考资料和用户问题组装在一起
QA_USER_TEMPLATE = """## 参考资料
{context}

## 用户问题
{question}

请基于以上参考资料回答用户问题。"""


class QAEngine:
    """知识图鉴问答引擎 — V11 双路径 RAG 流水线。

    将意图识别、查询路由、知识检索、LLM 生成串联为一次 ask() 调用。
    V11 新增: QueryRouter 双路径选择 — Wiki快路径 / RAG深路径 / 混合路径。

    Attributes:
        retriever: 知识检索器，负责向量/元数据混合检索
        cache: 可选结果缓存
        query_router: V11 查询路由器（可选，未配置时走纯 RAG）
        wiki_store: V11 Wiki 存储（可选，供 Wiki 路径使用）
    """

    def __init__(
        self,
        retriever: BookwormRetriever,
        cache: ResultCache | None = None,
        query_router=None,
        wiki_store=None,
    ):
        self.retriever = retriever
        self.cache = cache
        self.query_router = query_router
        self.wiki_store = wiki_store

    async def ask(
        self,
        question: str,
        top_k: int | None = None,
        target_category: str | None = None,
        org_id: str = "default",
        user_access_level: str = "INTERNAL",
        user_department: str | None = None,
    ) -> QAResponse:
        """回答用户问题 — 完整的 RAG 流水线入口。

        流程：缓存检查 → 意图识别 → 知识检索 → 上下文构建 → LLM 生成 → 缓存写入

        Args:
            question: 用户的原始问题文本
            top_k: 检索返回的最大结果数，None 时由意图路由自动决定
            target_category: 指定检索的目标分类，None 时由意图路由自动推断
            org_id: 组织 ID，用于多租户数据隔离
            user_access_level: 用户访问级别（如 INTERNAL/PUBLIC），用于权限过滤
            user_department: 用户所属部门，用于部门级权限过滤

        Returns:
            QAResponse: 包含回答文本、来源列表、意图分类和耗时的结构化响应
        """
        start_time = time.time()

        # OPT-13: 缓存命中直接返回（含权限维度，防止跨权限泄露）
        if self.cache:
            cached = self.cache.get_qa(
                question, top_k, target_category, org_id,
                user_access_level=user_access_level,
                user_department=user_department,
            )
            if cached is not None:
                return cached

        # 意图识别 → 路由策略（决定检索的 top_k 和目标分类）
        routing = classify_intent(question)
        effective_top_k = top_k or routing.suggested_top_k
        effective_category = target_category or routing.suggested_category
        route_path = "rag"  # 默认走 RAG 路径
        route_decision = None  # V11 路由决策
        domain_path = ""
        # RBAC: 只有INTERNAL用户且无部门限制时才可走Wiki快路径
        # PUBLIC用户不安全(Wiki页可能聚合INTERNAL内容)，CONFIDENTIAL/SECRET用户需RAG精确过滤
        wiki_rbac_safe = (user_access_level == "INTERNAL") and not user_department

        # V11: QueryRouter 双路径选择
        if self.query_router and self.wiki_store:
            try:
                confidence = 0.0
                if self.retriever.domain_store:
                    from packages.retrieval.skills_router import route_by_skills
                    domains = self.retriever.domain_store.list_domains(project_id=org_id)
                    catalog_text = self.retriever.domain_store.get_domain_catalog_text(project_id=org_id)
                    if domains and catalog_text:
                        skills_result = await route_by_skills(question, org_id, domains, catalog_text)
                        domain_path = skills_result.domain_path if skills_result else ""
                        confidence = skills_result.confidence if skills_result else 0.0

                route_decision = await self.query_router.route(question, domain_path, confidence, org_id)
                route_path = route_decision.path
                log.info("qa_route_decision", path=route_path, confidence=route_decision.confidence,
                         reason=route_decision.reason)

                # Wiki 快路径: 直接基于 Wiki 页回答
                # RBAC: Wiki页聚合了源文档内容，当用户有访问限制时回退到RAG路径做权限过滤
                if route_path == "wiki" and route_decision.wiki_page_id and wiki_rbac_safe:
                    wiki_page = await self.wiki_store.get_page(route_decision.wiki_page_id, org_id)
                    if wiki_page and wiki_page.content:
                        wiki_context = f"[Wiki知识页: {wiki_page.title}]\n{wiki_page.content[:3000]}"
                        user_prompt = QA_USER_TEMPLATE.format(context=wiki_context, question=question)
                        answer = call_llm(QA_SYSTEM_PROMPT, user_prompt)
                        latency = int((time.time() - start_time) * 1000)
                        response = QAResponse(
                            answer=answer,
                            sources=[SearchResult(
                                doc_id=wiki_page.page_id, title=f"Wiki: {wiki_page.title}",
                                content=wiki_page.summary, score=1.0,
                            )],
                            intent_category=routing.intent.value,
                            routed_domains=[domain_path] if domain_path else [],
                            route_path="wiki",
                            latency_ms=latency,
                        )
                        if self.cache:
                            self.cache.set_qa(
                                question, top_k, target_category, org_id, response,
                                user_access_level=user_access_level,
                                user_department=user_department,
                            )
                        return response
            except Exception as e:
                log.warning("query_router_failed_fallback_rag", error=str(e))
                route_path = "rag"

        # V11 Hybrid 路径: Wiki 先答 + RAG 补充验证
        # RBAC: 有访问限制时不注入Wiki内容前缀，仅走RAG
        wiki_prefix = ""
        if route_path == "hybrid" and self.wiki_store and wiki_rbac_safe:
            try:
                if route_decision and route_decision.wiki_page_id:
                    wiki_page = await self.wiki_store.get_page(route_decision.wiki_page_id, org_id)
                    if wiki_page and wiki_page.content:
                        wiki_prefix = f"[Wiki预编译知识]\n{wiki_page.content[:2000]}\n\n[以下为RAG检索补充]\n"
            except Exception as e:
                log.warning("hybrid_wiki_fetch_failed", error=str(e))

        # RAG 路径 / Hybrid 路径: 调用检索器进行向量/元数据混合检索
        # V14: 传递 domain_path 避免 retriever 重复调用 SkillsRouter
        results = await self.retriever.search(
            query=question,
            top_k=effective_top_k,
            target_category=effective_category,
            org_id=org_id,
            user_access_level=user_access_level,
            user_department=user_department,
            domain_path=domain_path,
        )

        # 检索无结果时: hybrid 有 wiki 内容则用 wiki，否则兜底
        if not results:
            if wiki_prefix:
                # hybrid 模式有 wiki 内容，直接基于 wiki 回答
                user_prompt = QA_USER_TEMPLATE.format(context=wiki_prefix, question=question)
                answer = call_llm(QA_SYSTEM_PROMPT, user_prompt)
                return QAResponse(
                    answer=answer, sources=[],
                    intent_category=routing.intent.value,
                    route_path="hybrid",
                    latency_ms=int((time.time() - start_time) * 1000),
                )
            return QAResponse(
                answer="抱歉，未找到与您问题相关的知识内容。请尝试换一种方式提问。",
                sources=[],
                intent_category=routing.intent.value,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        # 将检索结果组装为编号的参考资料文本，每条最多取前500字
        context_parts = []
        for i, r in enumerate(results, 1):
            context_parts.append(
                f"[{i}] 来源：{r.title or r.doc_id}\n"
                f"    内容：{r.content[:500]}\n"
            )
        context = wiki_prefix + "\n".join(context_parts)

        # 调用 LLM 基于检索上下文生成最终回答
        user_prompt = QA_USER_TEMPLATE.format(context=context, question=question)
        answer = call_llm(QA_SYSTEM_PROMPT, user_prompt)

        latency = int((time.time() - start_time) * 1000)

        # hybrid 模式: 将 wiki 页也加入来源列表
        all_sources = list(results)
        if route_path == "hybrid" and wiki_prefix and route_decision and route_decision.wiki_page_id:
            all_sources.insert(0, SearchResult(
                doc_id=route_decision.wiki_page_id,
                title=f"Wiki: {route_decision.wiki_page_id}",
                content=wiki_prefix[:200], score=1.0,
            ))

        response = QAResponse(
            answer=answer,
            sources=all_sources,
            intent_category=routing.intent.value,
            routed_domains=[domain_path] if domain_path else [],
            route_path=route_path,
            latency_ms=latency,
        )

        # OPT-13: 写入缓存，加速后续相同问题的查询（含权限维度）
        if self.cache:
            self.cache.set_qa(
                question, top_k, target_category, org_id, response,
                user_access_level=user_access_level,
                user_department=user_department,
            )

        return response
