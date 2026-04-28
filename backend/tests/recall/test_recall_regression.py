"""召回回归测试 — 基于标注数据集验证检索质量。"""

from __future__ import annotations

import json
import os
import asyncio

import pytest

from packages.common.types import Decision
from packages.connectors.feishu import FeishuConnector
from packages.distillation.pipeline import run_pipeline
from packages.retrieval.keyword_scorer import BM25Scorer
from packages.retrieval.reranker import create_reranker
from packages.retrieval.retriever import BookwormRetriever
from packages.storage.chunker import chunk_document
from packages.storage.embedder import embed_query, embed_texts
from packages.storage.graph_store import GraphStore
from packages.storage.metadata_store import MetadataStore
from packages.storage.vector_store import VectorStore

# 加载标注数据集
_GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "golden_dataset.json")
with open(_GOLDEN_PATH, "r", encoding="utf-8") as f:
    GOLDEN_DATASET = json.load(f)


@pytest.fixture(scope="module")
def knowledge_base():
    """构建内存知识库（复用 E2E Phase 1-3 流程）。"""

    async def _build():
        # Phase 1: 采集
        connector = FeishuConnector()
        await connector.connect()
        documents = []
        async for doc in connector.fetch_documents():
            documents.append(doc)

        # Phase 2: 蒸馏
        batch = run_pipeline(documents)
        doc_map = {d.doc_id: d for d in documents}

        # Phase 3: 入库
        vs = VectorStore(use_memory=True)
        await vs.initialize()
        gs = GraphStore(use_memory=True)
        await gs.initialize()
        ms = MetadataStore(use_memory=True)
        await ms.initialize()

        for r in batch.results:
            if r.decision != Decision.KEEP:
                continue
            doc = doc_map.get(r.doc_id)
            if not doc:
                continue

            cat = "/".join(r.librarian_result.key_topics[:2]) if r.librarian_result else ""
            summary = r.refined_result.summary if r.refined_result else ""
            kw = ",".join(r.refined_result.keywords) if r.refined_result else ""

            await ms.upsert_document({
                "id": doc.doc_id,
                "title": doc.title,
                "source_system": doc.source_system.value,
                "doc_type": r.librarian_result.doc_type.value if r.librarian_result else "其他",
                "status": "ACTIVE",
                "decision": r.decision.value,
                "kpi_retain": r.judge_result.kpi_retain if r.judge_result else None,
                "summary": summary,
                "keywords": kw,
                "category_path": cat,
                "org_id": "default",
                "created_at": None,
                "updated_at": None,
            })

            chunks = chunk_document(
                doc_id=doc.doc_id,
                content=doc.content,
                category_path=cat,
                doc_type=r.librarian_result.doc_type.value if r.librarian_result else "",
                source_system=doc.source_system.value,
                updated_at=doc.updated_at,
            )

            if chunks:
                texts = [c.content for c in chunks]
                embeddings = embed_texts(texts)
                for chunk, emb in zip(chunks, embeddings):
                    chunk.embedding = emb
                await vs.insert_chunks(chunks)

            if r.refined_result:
                await gs.add_document_node(doc.doc_id, {"title": doc.title})
                await gs.add_entities_and_relations(
                    doc.doc_id, r.refined_result.entities, r.refined_result.relations
                )

        # 构建 BM25 索引
        bm25 = BM25Scorer()
        bm25.build_index([
            {"chunk_id": c.chunk_id, "doc_id": c.doc_id, "content": c.content}
            for c in vs._memory_chunks
        ])

        reranker = create_reranker()
        retriever = BookwormRetriever(vs, gs, ms, keyword_scorer=bm25, reranker=reranker)

        return retriever, batch

    return asyncio.get_event_loop().run_until_complete(_build())


def _search_sync(retriever, query, top_k=5):
    """同步方式执行异步搜索。"""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(
        retriever.search(query=query, top_k=top_k)
    )


class TestRecallRegression:
    """召回回归测试。"""

    def test_recall_at_5(self, knowledge_base):
        """平均 recall@5 >= 0.6。"""
        retriever, _ = knowledge_base
        hits = 0
        total_expected = 0

        for tc in GOLDEN_DATASET:
            results = _search_sync(retriever, tc["query"], top_k=5)
            result_doc_ids = {r.doc_id for r in results}

            for expected_id in tc["expected_doc_ids"]:
                total_expected += 1
                if expected_id in result_doc_ids:
                    hits += 1

        recall = hits / total_expected if total_expected > 0 else 0
        assert recall >= 0.6, f"Recall@5 = {recall:.3f}, 期望 >= 0.6"

    def test_mrr(self, knowledge_base):
        """MRR >= 0.5。"""
        retriever, _ = knowledge_base
        reciprocal_ranks = []

        for tc in GOLDEN_DATASET:
            results = _search_sync(retriever, tc["query"], top_k=5)
            result_doc_ids = [r.doc_id for r in results]

            best_rank = None
            for expected_id in tc["expected_doc_ids"]:
                if expected_id in result_doc_ids:
                    rank = result_doc_ids.index(expected_id) + 1
                    if best_rank is None or rank < best_rank:
                        best_rank = rank

            reciprocal_ranks.append(1.0 / best_rank if best_rank else 0.0)

        mrr = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0
        assert mrr >= 0.5, f"MRR = {mrr:.3f}, 期望 >= 0.5"

    def test_no_noise_in_top_5(self, knowledge_base):
        """噪音文档不应出现在 top-5。"""
        retriever, _ = knowledge_base

        for tc in GOLDEN_DATASET:
            not_expected = tc.get("not_expected", [])
            if not not_expected:
                continue

            results = _search_sync(retriever, tc["query"], top_k=5)
            result_doc_ids = {r.doc_id for r in results}

            for noise_id in not_expected:
                assert noise_id not in result_doc_ids, (
                    f"查询 '{tc['query']}' 的 top-5 中包含噪音文档 {noise_id}"
                )

    def test_each_query_has_results(self, knowledge_base):
        """每条查询至少返回一个结果。"""
        retriever, _ = knowledge_base

        for tc in GOLDEN_DATASET:
            results = _search_sync(retriever, tc["query"], top_k=5)
            assert len(results) > 0, f"查询 '{tc['query']}' 无任何结果"
