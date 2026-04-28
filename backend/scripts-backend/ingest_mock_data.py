"""一键灌入多源 mock 数据到运行中的书虫服务。

用法: python -X utf8 -m scripts.ingest_mock_data
"""

from __future__ import annotations

import asyncio
import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DIVIDER = "=" * 60


async def main():
    print(f"\n{DIVIDER}")
    print("  书虫智能体 — 多源 Mock 数据灌入")
    print(f"{DIVIDER}\n")

    # ── Phase 1: 采集 ──
    from packages.connectors.feishu import FeishuConnector
    from packages.connectors.dingtalk import DingTalkConnector
    from packages.connectors.wecom import WeComConnector

    all_docs = []

    for name, ConnClass in [("飞书", FeishuConnector), ("钉钉", DingTalkConnector), ("企微", WeComConnector)]:
        conn = ConnClass()
        await conn.connect()
        docs = []
        async for doc in conn.fetch_documents():
            docs.append(doc)
        all_docs.extend(docs)
        print(f"  [{name}] 采集 {len(docs)} 篇文档")

    print(f"  合计: {len(all_docs)} 篇\n")

    # ── Phase 2: 蒸馏 ──
    from packages.distillation.pipeline import run_pipeline
    from packages.common.types import Decision

    batch = run_pipeline(all_docs)
    print(f"[Phase 2] 知识蒸馏:")
    print(f"  KEEP: {batch.kept} | ARCHIVE: {batch.archived} | DISCARD: {batch.discarded} | 噪音: {batch.noise_filtered}\n")

    # ── Phase 3: 入库（通过 deps 单例写入运行中的内存存储） ──
    from api.deps import init_stores, get_vector_store, get_graph_store, get_metadata_store, get_keyword_scorer
    from packages.storage.chunker import chunk_document
    from packages.storage.embedder import embed_texts

    await init_stores()
    vs = get_vector_store()
    gs = get_graph_store()
    ms = get_metadata_store()
    bm25 = get_keyword_scorer()

    doc_map = {d.doc_id: d for d in all_docs}
    total_chunks = 0

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
            "org_id": doc.org_id,
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
            org_id=doc.org_id,
        )

        if chunks:
            texts = [c.content for c in chunks]
            embeddings = embed_texts(texts)
            for chunk, emb in zip(chunks, embeddings):
                chunk.embedding = emb
            await vs.insert_chunks(chunks)
            total_chunks += len(chunks)

        if r.refined_result:
            await gs.add_document_node(doc.doc_id, {"title": doc.title})
            await gs.add_entities_and_relations(
                doc.doc_id, r.refined_result.entities, r.refined_result.relations
            )

    # 构建 BM25 索引
    bm25.build_index([
        {"chunk_id": c.chunk_id, "doc_id": c.doc_id, "content": c.content}
        for c in vs._memory_chunks
    ])

    print(f"[Phase 3] 入库完成:")
    print(f"  文档: {len(await ms.list_documents())} 篇")
    print(f"  向量切片: {total_chunks}")
    print(f"  图谱节点: {gs.node_count} | 图谱边: {gs.edge_count}")
    print(f"  BM25索引: {vs.chunk_count} 条")

    print(f"\n{DIVIDER}")
    print("  数据灌入完成! 现在可以通过 API 问答了")
    print(f"  API 文档: http://localhost:8000/docs")
    print(f"{DIVIDER}\n")


if __name__ == "__main__":
    asyncio.run(main())
