"""
端到端演示脚本 — 跑通飞书数据的完整流程。

流程：飞书采集 → 噪音过滤 → 三级 Agent 蒸馏 → 入库 → 检索问答

用法：python -m scripts.demo_e2e
"""

from __future__ import annotations

import asyncio
import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.common import get_logger
from packages.common.types import Decision

log = get_logger("demo_e2e")

DIVIDER = "=" * 70


async def main():
    print(f"\n{DIVIDER}")
    print("  书虫智能体 (Bookworm Agent) — 端到端演示")
    print(f"{DIVIDER}\n")

    # ── Phase 1: 飞书数据采集 ──────────────────────────
    print("[Phase 1] 飞书数据采集")
    print("-" * 40)

    from packages.connectors.feishu import FeishuConnector

    connector = FeishuConnector()
    await connector.connect()

    documents = []
    async for doc in connector.fetch_documents():
        documents.append(doc)
        print(f"  采集: {doc.doc_id} | {doc.title[:40]}")

    print(f"\n  共采集 {len(documents)} 篇文档\n")

    # ── Phase 2: 知识蒸馏管线 ─────────────────────────
    print(f"[Phase 2] 知识蒸馏管线（噪音过滤 → Librarian → Auditor → Judge → Refiner）")
    print("-" * 40)

    from packages.distillation.pipeline import run_pipeline

    batch = run_pipeline(documents)

    print(f"\n  管线处理完成:")
    print(f"    总文档数:   {batch.total}")
    print(f"    噪音过滤:   {batch.noise_filtered} 篇")
    print(f"    保留 (KEEP): {batch.kept} 篇")
    print(f"    归档 (ARCHIVE): {batch.archived} 篇")
    print(f"    剔除 (DISCARD): {batch.discarded} 篇")
    print(f"    处理错误:   {batch.errors} 次")
    print()

    # 详细展示每个文档的决策
    print("  决策明细:")
    for r in batch.results:
        status_icon = {
            Decision.KEEP: "[KEEP]    ",
            Decision.ARCHIVE: "[ARCHIVE] ",
            Decision.DISCARD: "[DISCARD] ",
        }.get(r.decision, "[???]     ")
        noise_tag = " (噪音过滤)" if r.is_noise else ""
        kpi_str = ""
        if r.judge_result:
            kpi_str = f" | KPI={r.judge_result.kpi_retain:.3f}"
        print(f"    {status_icon} {r.doc_id} | {r.title[:35]}{noise_tag}{kpi_str}")
        if r.judge_result and r.judge_result.summary:
            print(f"               理由: {r.judge_result.summary[:60]}")
        if r.error:
            print(f"               错误: {r.error[:60]}")
    print()

    # ── Phase 3: 知识入库 ─────────────────────────────
    print(f"[Phase 3] 知识入库（向量化 + 图谱构建 + 元数据存储）")
    print("-" * 40)

    from packages.storage.vector_store import VectorStore
    from packages.storage.graph_store import GraphStore
    from packages.storage.metadata_store import MetadataStore
    from packages.storage.chunker import chunk_document
    from packages.storage.embedder import embed_texts

    vector_store = VectorStore(use_memory=True)
    await vector_store.initialize()
    graph_store = GraphStore(use_memory=True)
    await graph_store.initialize()
    metadata_store = MetadataStore(use_memory=True)
    await metadata_store.initialize()

    total_chunks = 0
    total_entities = 0

    # 构建 doc_id -> RawDocument 映射
    doc_map = {d.doc_id: d for d in documents}

    for r in batch.results:
        if r.decision != Decision.KEEP:
            continue

        doc = doc_map.get(r.doc_id)
        if not doc:
            continue

        # 元数据入库
        category_path = ""
        summary = ""
        keywords = ""

        if r.refined_result:
            summary = r.refined_result.summary
            keywords = ",".join(r.refined_result.keywords)
        if r.librarian_result and r.librarian_result.key_topics:
            category_path = "/".join(r.librarian_result.key_topics[:2])

        await metadata_store.upsert_document({
            "id": doc.doc_id,
            "title": doc.title,
            "source_system": doc.source_system.value,
            "doc_type": r.librarian_result.doc_type.value if r.librarian_result else "其他",
            "version_id": r.librarian_result.version_id if r.librarian_result else None,
            "status": "ACTIVE",
            "decision": r.decision.value,
            "kpi_retain": r.judge_result.kpi_retain if r.judge_result else None,
            "summary": summary,
            "keywords": keywords,
            "category_path": category_path,
            "created_at": doc.created_at,
            "updated_at": doc.updated_at,
        })

        # 文档分片 + 向量化
        chunks = chunk_document(
            doc_id=doc.doc_id,
            content=doc.content,
            category_path=category_path,
            doc_type=r.librarian_result.doc_type.value if r.librarian_result else "",
            source_system=doc.source_system.value,
            updated_at=doc.updated_at,
        )

        if chunks:
            texts = [c.content for c in chunks]
            embeddings = embed_texts(texts)
            for chunk, emb in zip(chunks, embeddings):
                chunk.embedding = emb

            await vector_store.insert_chunks(chunks)
            total_chunks += len(chunks)
            print(f"  入库: {doc.doc_id} | {len(chunks)} 切片 | {doc.title[:35]}")

        # 图谱构建
        if r.refined_result:
            await graph_store.add_document_node(doc.doc_id, {
                "title": doc.title,
                "doc_type": r.librarian_result.doc_type.value if r.librarian_result else "",
                "summary": summary[:200],
            })
            await graph_store.add_entities_and_relations(
                doc.doc_id,
                r.refined_result.entities,
                r.refined_result.relations,
            )
            total_entities += len(r.refined_result.entities)

    print(f"\n  入库完成:")
    print(f"    向量切片:  {total_chunks} 个")
    print(f"    图谱节点:  {graph_store.node_count} 个")
    print(f"    图谱边:    {graph_store.edge_count} 条")
    print(f"    实体总数:  {total_entities} 个")
    print()

    # ── Phase 4: 智能问答测试 ─────────────────────────
    print(f"[Phase 4] 智能问答测试")
    print("-" * 40)

    from packages.retrieval.retriever import BookwormRetriever
    from packages.retrieval.qa_engine import QAEngine

    retriever = BookwormRetriever(vector_store, graph_store, metadata_store)
    qa_engine = QAEngine(retriever)

    test_questions = [
        "最新的员工报销流程是什么？",
        "Q4有哪些重点项目？",
        "Docker部署需要什么配置要求？",
        "新员工入职需要准备什么材料？",
        "向量数据库选型的结论是什么？",
    ]

    for q in test_questions:
        print(f"\n  问：{q}")
        result = await qa_engine.ask(q, top_k=3)
        print(f"  答：{result.answer[:200]}...")
        print(f"  延迟：{result.latency_ms}ms | 参考来源：{len(result.sources)} 篇")
        if result.sources:
            for s in result.sources[:2]:
                print(
                    f"    - [{s.score:.3f}] {s.title or s.doc_id}"
                    f" (vec={s.vector_score:.3f}, graph={s.graph_score:.3f}, cat={s.catalog_weight:.3f})"
                )

    # ── 总结 ──────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("  端到端流程验证完成！")
    print(f"{DIVIDER}")
    print(f"""
  流程摘要：
    1. 飞书连接器采集了 {len(documents)} 篇文档（模拟数据模式）
    2. 噪音过滤器识别并剔除了 {batch.noise_filtered} 篇废话文档
    3. 三级 Agent 管线对 {batch.total - batch.noise_filtered} 篇文档进行了蒸馏评估
       - Librarian 提取元数据（类型/版本/主题/实体）
       - Conflict Auditor 检测版本冲突
       - Judge Agent 综合 LLM 评分 + KPI_retain 公式做出决策
       - Refiner Agent 对保留文档提炼摘要/关键词/实体关系
    4. {batch.kept} 篇文档入库（{total_chunks} 切片向量化 + {total_entities} 实体图谱化）
    5. 混合检索引擎（向量 + 图谱 + 目录权重）支撑智能问答
""")


if __name__ == "__main__":
    asyncio.run(main())
