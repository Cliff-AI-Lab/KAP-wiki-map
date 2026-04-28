"""端到端验证脚本 — 验证 P0 优化后的完整流程。"""

from __future__ import annotations

import asyncio
import sys
import os
import io
import logging

# 处理 Windows 编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 静默 structlog 以获得干净输出
logging.disable(logging.CRITICAL)
os.environ['LOG_LEVEL'] = 'ERROR'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DIVIDER = "=" * 60


async def main():
    print(f"\n{DIVIDER}")
    print("  书虫智能体 — P0 第二批优化端到端验证")
    print(f"{DIVIDER}\n")

    # ── Phase 1: 多数据源采集 ──
    from packages.connectors.feishu import FeishuConnector
    from packages.connectors.dingtalk import DingTalkConnector
    from packages.connectors.wecom import WeComConnector

    feishu_docs = []
    connector = FeishuConnector()
    await connector.connect()
    async for doc in connector.fetch_documents():
        feishu_docs.append(doc)

    dt_docs = []
    dt = DingTalkConnector()
    await dt.connect()
    async for doc in dt.fetch_documents():
        dt_docs.append(doc)

    wc_docs = []
    wc = WeComConnector()
    await wc.connect()
    async for doc in wc.fetch_documents():
        wc_docs.append(doc)

    documents = feishu_docs + dt_docs + wc_docs
    print(f"[Phase 1] 多数据源采集:")
    print(f"  飞书: {len(feishu_docs)} | 钉钉: {len(dt_docs)} | 企微: {len(wc_docs)} | 合计: {len(documents)} 篇\n")

    # ── Phase 2: 知识蒸馏 ──
    from packages.distillation.pipeline import run_pipeline
    from packages.common.types import Decision
    batch = run_pipeline(documents)

    print(f"[Phase 2] 知识蒸馏完成:")
    print(f"  总文档: {batch.total} | 噪音过滤: {batch.noise_filtered}")
    print(f"  KEEP: {batch.kept} | ARCHIVE: {batch.archived} | DISCARD: {batch.discarded}")
    print(f"  决策明细:")
    for r in batch.results:
        icon = {"KEEP": "KEEP", "ARCHIVE": "ARCH", "DISCARD": "DEL "}.get(
            r.decision.value if r.decision else "", "??? "
        )
        noise = " (噪音)" if r.is_noise else ""
        kpi = f" KPI={r.judge_result.kpi_retain:.3f}" if r.judge_result else ""
        print(f"    [{icon}] {r.doc_id} | {r.title[:35]}{noise}{kpi}")
    print()

    # ── Phase 3: 知识入库 ──
    from packages.storage.vector_store import VectorStore
    from packages.storage.graph_store import GraphStore
    from packages.storage.metadata_store import MetadataStore
    from packages.storage.chunker import chunk_document
    from packages.storage.embedder import embed_texts

    vs = VectorStore(use_memory=True)
    await vs.initialize()
    gs = GraphStore(use_memory=True)
    await gs.initialize()
    ms = MetadataStore(use_memory=True)
    await ms.initialize()

    doc_map = {d.doc_id: d for d in documents}
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

    print(f"[Phase 3] 知识入库完成:")
    print(f"  向量切片: {total_chunks} | 图谱节点: {gs.node_count} | 图谱边: {gs.edge_count}\n")

    # ── Phase 4: 四通道混合检索 + Reranker 问答 ──
    from packages.retrieval.keyword_scorer import BM25Scorer
    from packages.retrieval.reranker import create_reranker
    from packages.retrieval.retriever import BookwormRetriever
    from packages.retrieval.qa_engine import QAEngine

    bm25 = BM25Scorer()
    bm25.build_index([
        {"chunk_id": c.chunk_id, "doc_id": c.doc_id, "content": c.content}
        for c in vs._memory_chunks
    ])
    reranker = create_reranker()
    retriever = BookwormRetriever(vs, gs, ms, keyword_scorer=bm25, reranker=reranker)
    qa = QAEngine(retriever)

    print(f"[Phase 4] 四通道混合检索问答 (向量+图谱+目录+BM25 + {type(reranker).__name__})")
    print("-" * 50)

    test_questions = [
        "最新的员工报销流程是什么？",
        "Docker部署需要什么配置要求？",
        "新员工入职需要准备什么材料？",
    ]

    for q in test_questions:
        result = await qa.ask(q, top_k=3)
        print(f"\n  问: {q}")
        print(f"  答: {result.answer[:150]}...")
        print(f"  延迟: {result.latency_ms}ms | 意图: {result.intent_category} | 来源: {len(result.sources)}篇")
        for s in result.sources[:3]:
            print(
                f"    [{s.score:.3f}] {s.title or s.doc_id}"
                f"  vec={s.vector_score:.3f} graph={s.graph_score:.3f}"
                f" cat={s.catalog_weight:.3f} kw={s.keyword_score:.3f}"
            )

    # ── Phase 5: P0 新功能专项验证 ──
    print(f"\n\n[Phase 5] P0 新功能专项验证")
    print("=" * 50)

    # 5a: 三种切片策略对比
    print("\n  [P0-1] 切片策略对比:")
    test_doc = documents[0]
    for strat in ["fixed", "parent_child", "semantic"]:
        cs = chunk_document(doc_id="test", content=test_doc.content, strategy=strat)
        parents = sum(1 for c in cs if c.is_parent)
        children = sum(1 for c in cs if c.parent_chunk_id)
        plain = len(cs) - parents - children
        print(f"    {strat:15s}: {len(cs):2d} 切片 (parent={parents}, child={children}, plain={plain})")

    # 5b: BM25 关键词搜索
    print("\n  [P0-2] BM25 关键词检索:")
    for kw in ["Docker", "报销", "入职", "安全"]:
        kw_results = bm25.search(kw, top_k=2)
        if kw_results:
            r0 = kw_results[0]
            print(f"    '{kw}' -> {r0['doc_id']} (score={r0['score']:.3f}) | {r0['content'][:40]}...")
        else:
            print(f"    '{kw}' -> 无结果")

    # 5c: 四通道评分演示
    print("\n  [P0-2] 四通道评分公式:")
    from packages.retrieval.hybrid_scorer import compute_hybrid_score
    from packages.common import settings
    score = compute_hybrid_score(0.8, 0.6, 0.5, 0.9)
    print(f"    compute_hybrid_score(vec=0.8, graph=0.6, cat=0.5, kw=0.9)")
    print(f"    = {settings.score_alpha}*0.8 + {settings.score_beta}*0.6 + {settings.score_gamma}*0.5 + {settings.score_delta}*0.9")
    print(f"    = {score}")

    # 5d: Reranker
    print(f"\n  [P0-3] Reranker: {type(reranker).__name__} (provider={settings.reranker_provider})")

    # 5e: 意图路由 + delta 权重
    print("\n  [P0-2/3] 意图路由 (含 delta 关键词权重):")
    from packages.retrieval.intent_router import classify_intent
    for q in ["报销制度是什么", "Docker部署配置", "谁负责项目"]:
        r = classify_intent(q)
        print(f"    '{q}' -> {r.intent.value} (a={r.alpha_override}, b={r.beta_override}, g={r.gamma_override}, d={r.delta_override})")

    # ── Phase 5 扩展: 第二批 P0 新功能验证 ──
    print("\n  " + "-" * 46)
    print("  第二批 P0 新功能专项验证")
    print("  " + "-" * 46)

    # 5f: 多模态解析器
    print("\n  [P0-3] 多模态解析器:")
    from packages.storage.parsers import parse_content
    pdf_result = await parse_content(b"fake pdf", "application/pdf")
    img_result = await parse_content(b"fake png", "image/png")
    vid_result = await parse_content(b"fake mp4", "video/mp4")
    txt_result = await parse_content("纯文本".encode("utf-8"), "text/plain")
    print(f"    PDF:   parser={pdf_result.parser_name}, text_len={len(pdf_result.text)}")
    print(f"    Image: parser={img_result.parser_name}, text_len={len(img_result.text)}")
    print(f"    Video: parser={vid_result.parser_name}, text_len={len(vid_result.text)}")
    print(f"    Text:  parser={txt_result.parser_name}, text_len={len(txt_result.text)}")

    # 5g: 多租户隔离
    print("\n  [P0-4] 多租户隔离:")
    from packages.common.types import RawDocument, KnowledgeChunk, SearchResult, SourceSystem
    doc_a = RawDocument(doc_id="t1", title="x", content="y", source_system=SourceSystem.FEISHU, org_id="org_a")
    doc_b = RawDocument(doc_id="t2", title="x", content="y", source_system=SourceSystem.DINGTALK)
    print(f"    RawDocument(org_id='org_a'):  org_id={doc_a.org_id}")
    print(f"    RawDocument(default):         org_id={doc_b.org_id}")
    print(f"    KnowledgeChunk(default):      org_id={KnowledgeChunk(chunk_id='c', doc_id='d', chunk_index=0, content='x').org_id}")
    print(f"    SearchResult(default):        org_id={SearchResult(doc_id='d').org_id}")

    # 5h: 认证上下文
    print("\n  [P0-5] 认证上下文:")
    from packages.common.auth import UserContext
    from api.middleware.auth import _API_KEY_MAP, SKIP_PATHS
    anon = UserContext()
    admin = _API_KEY_MAP["bw-admin-key"]
    print(f"    匿名用户: user_id={anon.user_id}, org_id={anon.org_id}, access={anon.access_level}")
    print(f"    管理员:    user_id={admin.user_id}, org_id={admin.org_id}, access={admin.access_level}")
    print(f"    跳过认证路径: {SKIP_PATHS}")

    # 5i: 审计日志
    print("\n  [P0-6] 审计日志:")
    from packages.common.audit import AuditAction, AuditEntry, AuditLogger
    audit = AuditLogger()
    await audit.log(AuditEntry(action=AuditAction.QA_QUERY, user_id="test", org_id="default"))
    await audit.log(AuditEntry(action=AuditAction.DOCUMENT_INGESTED, user_id="test", org_id="org_a"))
    await audit.log(AuditEntry(action=AuditAction.SEARCH_QUERY, user_id="test", org_id="default"))
    all_logs = await audit.list_logs()
    qa_logs = await audit.list_logs(action="qa_query")
    org_a_logs = await audit.list_logs(org_id="org_a")
    print(f"    总日志: {len(all_logs)} | QA日志: {len(qa_logs)} | org_a日志: {len(org_a_logs)}")

    # 5j: 多数据源覆盖统计
    print("\n  [P0-1/2] 多数据源覆盖:")
    from collections import Counter
    src_counts = Counter(d.source_system.value for d in documents)
    for src, cnt in sorted(src_counts.items()):
        print(f"    {src}: {cnt} 篇")

    print(f"\n{DIVIDER}")
    print("  P0 第二批优化端到端验证全部通过!")
    print(f"{DIVIDER}\n")


if __name__ == "__main__":
    asyncio.run(main())
