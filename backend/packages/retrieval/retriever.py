"""检索引擎 — V8 Skills 式精准 RAG 检索。

核心流程（对齐核心理念 §三：按体系逐层检索，降低 Token 消耗）：
1. 意图分类 → 动态调整权重和 top_k
2. ★ SkillsRouter 体系路径定位 → 匹配到知识体系中的具体分支
3. ★ 分支激活 → Milvus domain_id 前缀匹配（只搜索目标分支及子分支）
4. RBAC 权限过滤
5. 图谱(V8双向索引实体共现) + BM25 混合评分
6. Reranker 精排
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.common import get_logger, settings
from packages.common.types import AccessLevel, SearchResult
from packages.retrieval.hybrid_scorer import compute_catalog_weight, compute_hybrid_score
from packages.retrieval.intent_router import classify_intent
from packages.retrieval.keyword_scorer import BM25Scorer
from packages.retrieval.llm_router import RouteResult, route_query
from packages.retrieval.reranker import BaseReranker
from packages.storage.domain_store import DomainStore
from packages.storage.embedder import embed_query
from packages.storage.graph_store import GraphStore
from packages.storage.metadata_store import MetadataStore
from packages.storage.vector_store import VectorStore

if TYPE_CHECKING:
    from packages.retrieval.cache import ResultCache

log = get_logger("retrieval")

_ACCESS_LEVEL_RANK: dict[str, int] = {
    AccessLevel.PUBLIC.value: 0,
    AccessLevel.INTERNAL.value: 1,
    AccessLevel.CONFIDENTIAL.value: 2,
    AccessLevel.SECRET.value: 3,
}


class BookwormRetriever:
    """书虫检索引擎 — V8 Skills 模式：意图分类 + SkillsRouter 体系路由 + 分支激活检索。"""

    def __init__(
        self,
        vector_store: VectorStore,
        graph_store: GraphStore,
        metadata_store: MetadataStore,
        domain_store: DomainStore | None = None,
        keyword_scorer: BM25Scorer | None = None,
        reranker: BaseReranker | None = None,
        cache: ResultCache | None = None,
    ):
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.metadata_store = metadata_store
        self.domain_store = domain_store
        self.keyword_scorer = keyword_scorer or BM25Scorer()
        self.reranker = reranker
        self.cache = cache

    async def search(
        self,
        query: str,
        top_k: int = 5,
        target_category: str | None = None,
        user_access_level: str = AccessLevel.INTERNAL.value,
        user_department: str | None = None,
        org_id: str = "default",
        domain_path: str = "",
    ) -> list[SearchResult]:
        """
        V7 Skills 模式检索：
        1. 意图分类 → 动态权重
        2. LLM 读知识域目录 → 选择分支（路由）
        3. Milvus 按 domain_id 精准检索
        4. RBAC 权限过滤
        5. 实体共现 + BM25 混合评分
        6. Reranker 精排
        """
        log.info("retrieval_start", query=query[:100], top_k=top_k)

        # 缓存命中直接返回
        if self.cache:
            cached = self.cache.get_search(
                query, top_k, target_category, org_id, user_access_level,
            )
            if cached is not None:
                return cached

        # ── Step 1: 意图分类 — 动态调整权重和 top_k ──
        intent_result = classify_intent(query)
        effective_top_k = intent_result.suggested_top_k or top_k
        alpha = intent_result.alpha_override or settings.score_alpha
        beta = intent_result.beta_override or settings.score_beta
        gamma = intent_result.gamma_override or settings.score_gamma
        delta = intent_result.delta_override or settings.score_delta

        log.info(
            "intent_routed",
            intent=intent_result.intent.value,
            confidence=intent_result.confidence,
            top_k=effective_top_k,
            alpha=alpha, beta=beta, gamma=gamma, delta=delta,
        )

        candidate_multiplier = settings.reranker_candidate_multiplier if self.reranker else 3

        # ── Step 2: V8 SkillsRouter 体系路径定位 ──
        # 对齐核心理念：按体系逐层打开，先定位分支再检索
        route_result = RouteResult()
        domain_filter = None
        doc_id_filter = None

        if self.domain_store and self.domain_store.card_count > 0:
            catalog_text = self.domain_store.get_domain_catalog_text(project_id=org_id)

            # V14: 如果 QA 引擎已经计算了 domain_path，直接使用（避免重复调用 SkillsRouter）
            if domain_path:
                domain_filter = [domain_path]
                log.info("retriever_using_precomputed_domain", domain_path=domain_path)
            else:
                # V8: 使用 SkillsRouter 做体系路径定位
                try:
                    from packages.retrieval.skills_router import route_by_skills
                    domains = self.domain_store.list_domains(project_id=org_id)
                    skills_route = await route_by_skills(query, org_id, domains, catalog_text)

                    if skills_route.confidence >= 0.5 and skills_route.domain_path:
                        domain_filter = [skills_route.domain_path]
                        log.info(
                            "skills_router_activated",
                            query=query[:60],
                            domain_path=skills_route.domain_path,
                            confidence=round(skills_route.confidence, 3),
                            reasoning=skills_route.reasoning[:80],
                        )
                    else:
                        # 置信度不足 → 降级到 LLMRouter
                        log.info("skills_router_low_confidence", confidence=skills_route.confidence)
                        route_result = await route_query(query, catalog_text)
                        doc_id_filter = route_result.selected_doc_ids or None
                        domain_filter = route_result.selected_domains or None
                except Exception as e:
                    log.warning("skills_router_failed_fallback_llm", error=str(e))
                    route_result = await route_query(query, catalog_text)
                    doc_id_filter = route_result.selected_doc_ids or None
                    domain_filter = route_result.selected_domains or None

        # ── Step 3: V8 分支激活 — Milvus 前缀匹配检索 ──
        query_embedding = embed_query(query)

        vector_hits = await self.vector_store.search(
            query_embedding=query_embedding,
            top_k=effective_top_k * candidate_multiplier,
            org_id=org_id,
            doc_id_filter=doc_id_filter,
            domain_filter=domain_filter if not doc_id_filter else None,
        )

        # V8 fallback: 分支无结果 → 扩大到父分支
        if not vector_hits and domain_filter:
            parent_filters = []
            for df in domain_filter:
                if "/" in df:
                    parent_filters.append(df.rsplit("/", 1)[0])
            if parent_filters:
                log.info("skills_fallback_parent_branch", parents=parent_filters)
                vector_hits = await self.vector_store.search(
                    query_embedding=query_embedding,
                    top_k=effective_top_k * candidate_multiplier,
                    org_id=org_id,
                    domain_filter=parent_filters,
                )

        # 最终 fallback: 全量检索
        if not vector_hits:
            if domain_filter or doc_id_filter:
                log.info("skills_fallback_to_full_search")
                vector_hits = await self.vector_store.search(
                    query_embedding=query_embedding,
                    top_k=effective_top_k * candidate_multiplier,
                    org_id=org_id,
                )

        if not vector_hits:
            log.info("retrieval_no_vector_hits")
            return []

        # ── Step 4: RBAC 权限过滤 ────────────────────
        user_rank = _ACCESS_LEVEL_RANK.get(user_access_level, 1)
        filtered_hits = []
        for hit in vector_hits:
            doc_id = hit["doc_id"]
            doc_meta = await self.metadata_store.get_document(doc_id)
            if not doc_meta:
                continue

            doc_access = doc_meta.get("access_level", AccessLevel.INTERNAL.value)
            doc_rank = _ACCESS_LEVEL_RANK.get(doc_access, 1)
            if user_rank < doc_rank:
                continue

            if doc_rank >= _ACCESS_LEVEL_RANK[AccessLevel.CONFIDENTIAL.value]:
                doc_dept = doc_meta.get("department_id", "")
                if doc_dept and user_department and doc_dept != user_department:
                    continue

            hit["_meta"] = doc_meta
            filtered_hits.append(hit)

        if not filtered_hits:
            log.info("retrieval_all_filtered_by_rbac")
            return []

        # ── Step 5: 实体共现 + BM25 混合评分 ─────────
        graph_scores = await self._compute_graph_scores(query, filtered_hits)

        keyword_scores: dict[str, float] = {}
        if self.keyword_scorer:
            kw_results = self.keyword_scorer.search(query, top_k=effective_top_k * candidate_multiplier)
            for kwr in kw_results:
                keyword_scores[kwr["chunk_id"]] = kwr["score"]

        results = []
        for hit in filtered_hits:
            doc_id = hit["doc_id"]
            v_score = hit["score"]
            g_score = graph_scores.get(doc_id, 0.0)
            cat_path = hit.get("category_path", "")
            w_cat = compute_catalog_weight(cat_path, target_category or "")
            k_score = keyword_scores.get(hit.get("chunk_id", ""), 0.0)

            final_score = compute_hybrid_score(v_score, g_score, w_cat, k_score,
                                                alpha=alpha, beta=beta, gamma=gamma, delta=delta)
            doc_meta = hit["_meta"]

            results.append(SearchResult(
                doc_id=doc_id,
                chunk_id=hit.get("chunk_id", ""),
                title=doc_meta.get("title", "") if doc_meta else "",
                content=hit.get("content", ""),
                score=final_score,
                vector_score=v_score,
                graph_score=g_score,
                catalog_weight=w_cat,
                keyword_score=k_score,
                doc_type=hit.get("doc_type") or doc_meta.get("doc_type", ""),
                source_system=hit.get("source_system") or doc_meta.get("source_system", ""),
                category_path=cat_path,
                org_id=org_id,
            ))

        results.sort(key=lambda r: r.score, reverse=True)

        # ── Step 6: Reranker 精排 ────────────────────
        if self.reranker and len(results) > effective_top_k:
            results = await self.reranker.rerank(query, results, effective_top_k)
        else:
            results = results[:effective_top_k]

        log.info(
            "retrieval_done",
            result_count=len(results),
            intent=intent_result.intent.value,
            routed_domains=route_result.selected_domains,
            routed_doc_ids=route_result.selected_doc_ids,
            top_score=results[0].score if results else 0,
        )

        # 写入缓存
        if self.cache and results:
            self.cache.set_search(
                query, top_k, target_category, org_id, user_access_level, results,
            )

        return results

    async def _compute_graph_scores(
        self, query: str, vector_hits: list[dict]
    ) -> dict[str, float]:
        """V7: 简化图谱评分 — 基于实体共现匹配。

        不再做 shortest_path 计算（太重），改为：
        - 查询实体 ∩ 文档实体 → 完全匹配 1.0
        - 查询实体的一跳邻居 ∩ 文档实体 → 0.6
        - 有实体但无匹配 → 0.1
        """
        scores: dict[str, float] = {}
        query_entities = await self._extract_query_entities(query)

        # 预取查询实体的一跳邻居
        query_neighbors: set[str] = set()
        if query_entities:
            for q_ent in query_entities[:5]:
                related = await self.graph_store.find_related_docs(q_ent, max_hops=1)
                # 从 find_related_docs 的逻辑中提取邻居实体
                for edge in self.graph_store._edges:
                    if edge["source"] == q_ent:
                        query_neighbors.add(edge["target"])
                    elif edge["target"] == q_ent:
                        query_neighbors.add(edge["source"])

        for hit in vector_hits:
            doc_id = hit["doc_id"]
            doc_entities = await self.graph_store.get_doc_entities(doc_id)

            if not doc_entities:
                scores[doc_id] = 0.0
                continue
            if not query_entities:
                scores[doc_id] = min(len(doc_entities) * 0.1, 0.5)
                continue

            doc_ent_set = set(doc_entities)
            query_ent_set = set(query_entities)

            # 完全匹配
            direct_overlap = query_ent_set & doc_ent_set
            if direct_overlap:
                scores[doc_id] = min(1.0, 0.5 + len(direct_overlap) * 0.25)
                continue

            # 一跳邻居匹配
            neighbor_overlap = query_neighbors & doc_ent_set
            if neighbor_overlap:
                scores[doc_id] = min(0.6, 0.3 + len(neighbor_overlap) * 0.15)
                continue

            scores[doc_id] = 0.1

        return scores

    async def _extract_query_entities(self, query: str) -> list[str]:
        """从查询文本中提取与图谱匹配的实体。"""
        import re
        tokens = re.split(r"[，。？！、\s,.\?!]+", query)
        tokens = [t.strip() for t in tokens if len(t.strip()) >= 2]

        matched: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            entities = await self.graph_store.find_entity_by_keyword(token)
            for ent in entities:
                if ent not in seen:
                    seen.add(ent)
                    matched.append(ent)
        return matched
