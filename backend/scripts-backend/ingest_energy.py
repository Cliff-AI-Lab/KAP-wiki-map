"""华能石化能源知识库 — 批量灌入脚本。

用法:
    python scripts/ingest_energy.py [--api URL] [--batch-size N] [--delay SEC]

前提:
    1. docker compose up -d (Milvus/Redis)
    2. uvicorn api.main:app --port 8000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

DEFAULT_API_BASE = "http://localhost:8000/api/v1"
DATA_DIR = Path(__file__).resolve().parent.parent / "test_data" / "energy"

SUPPORTED_EXT = {".txt", ".md", ".docx", ".pdf"}

_api_base = DEFAULT_API_BASE


def create_project(client: httpx.Client) -> str:
    """创建华能石化项目，返回 project_id。"""
    # 先检查是否已存在
    resp = client.get(f"{_api_base}/projects")
    resp.raise_for_status()
    for p in resp.json():
        if p.get("industry_code") == "energy":
            pid = p["id"]
            print(f"[OK] 已有能源项目: {pid} ({p['name']})")
            return pid

    # 创建新项目
    resp = client.post(f"{_api_base}/projects", json={
        "name": "华能石化知识库",
        "industry_code": "energy",
        "description": "华能石化有限公司企业知识管理系统 — 涵盖生产、安全、环保、应急、物流、采购六大业务领域",
    })
    resp.raise_for_status()
    data = resp.json()
    pid = data["id"]
    print(f"[OK] 创建能源项目: {pid} (含 {data.get('domain_count', '?')} 个知识域)")
    return pid


def collect_files() -> list[Path]:
    """收集 test_data/energy 下所有支持格式的文件。"""
    files = sorted(
        f for f in DATA_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
    )
    print(f"[OK] 发现 {len(files)} 个文件:")
    for f in files:
        print(f"     {f.name} ({f.stat().st_size:,} bytes)")
    return files


def ingest_batch(
    client: httpx.Client,
    files: list[Path],
    project_id: str,
) -> dict:
    """上传一批文件到 /ingest。"""
    multipart = [
        ("files", (f.name, open(f, "rb")))
        for f in files
    ]
    resp = client.post(
        f"{_api_base}/knowledge/ingest",
        files=multipart,
        data={"project_id": project_id},
        timeout=180,
    )
    # 关闭文件句柄
    for _, (_, fh) in multipart:
        fh.close()

    resp.raise_for_status()
    return resp.json()


def verify_results(client: httpx.Client, project_id: str):
    """验证灌入结果。"""
    print("\n" + "=" * 60)
    print("验证结果")
    print("=" * 60)

    # Stats
    resp = client.get(f"{_api_base}/knowledge/stats", params={"project_id": project_id})
    if resp.status_code == 200:
        stats = resp.json()
        print(f"\n[统计]")
        for k, v in stats.items():
            print(f"  {k}: {v}")

    # Domains
    resp = client.get(f"{_api_base}/knowledge/domains", params={"project_id": project_id})
    if resp.status_code == 200:
        data = resp.json()
        domains = data.get("domains", [])
        print(f"\n[知识体系] 共 {len(domains)} 个知识域:")
        for d in domains:
            indent = "  " if "/" not in d["domain_id"] else (
                "    " if d["domain_id"].count("/") == 1 else "      "
            )
            count = f" ({d['doc_count']}篇)" if d.get("doc_count", 0) > 0 else ""
            print(f"{indent}{d['name']}{count}")

    # Graph
    resp = client.get(f"{_api_base}/knowledge/graph-overview", params={"project_id": project_id})
    if resp.status_code == 200:
        g = resp.json()
        print(f"\n[知识图谱] {g.get('node_count', 0)} 个实体节点, {g.get('edge_count', 0)} 条关系")
        nodes = g.get("nodes", [])[:10]
        if nodes:
            print("  前10个实体:")
            for n in nodes:
                print(f"    {n.get('label', n.get('id', '?'))} [{n.get('type', '?')}]")
        edges = g.get("edges", [])[:5]
        if edges:
            print("  前5条关系:")
            for e in edges:
                print(f"    {e.get('source', '?')} --[{e.get('relation', '?')}]--> {e.get('target', '?')}")

    # Documents
    resp = client.get(f"{_api_base}/knowledge/documents", params={"project_id": project_id})
    if resp.status_code == 200:
        docs = resp.json()
        if isinstance(docs, list):
            print(f"\n[文档列表] 共 {len(docs)} 篇:")
            for d in docs[:5]:
                title = d.get("title", "?")
                decision = d.get("decision", "?")
                cat = d.get("category_path", "?")
                print(f"  [{decision}] {title}  →  {cat}")
            if len(docs) > 5:
                print(f"  ... 还有 {len(docs) - 5} 篇")


def main():
    parser = argparse.ArgumentParser(description="华能石化知识库批量灌入")
    parser.add_argument("--api", default=DEFAULT_API_BASE, help="API base URL")
    parser.add_argument("--batch-size", type=int, default=3, help="每批上传文件数")
    parser.add_argument("--delay", type=float, default=5, help="批次间延迟(秒)")
    args = parser.parse_args()

    global _api_base
    _api_base = args.api

    client = httpx.Client(timeout=180)

    # 1. 创建项目
    print("=" * 60)
    print("华能石化能源知识库 — 全流程灌入")
    print("=" * 60)
    project_id = create_project(client)

    # 2. 收集文件
    files = collect_files()
    if not files:
        print("[ERROR] test_data/energy/ 下无可用文件")
        sys.exit(1)

    # 3. 分批上传
    total_kept = 0
    total_chunks = 0
    for i in range(0, len(files), args.batch_size):
        batch = files[i : i + args.batch_size]
        batch_num = i // args.batch_size + 1
        names = ", ".join(f.name for f in batch)
        print(f"\n[批次 {batch_num}] 上传: {names}")

        try:
            result = ingest_batch(client, batch, project_id)
            dist = result.get("distillation", {})
            stor = result.get("storage", {})
            kept = dist.get("kept", 0)
            total_kept += kept
            chunks = stor.get("vector_chunks", 0)
            total_chunks += chunks
            print(f"  → 蒸馏: kept={kept}, archived={dist.get('archived', 0)}, "
                  f"discarded={dist.get('discarded', 0)}")
            print(f"  → 存储: chunks={chunks}, graph_nodes={stor.get('graph_nodes', 0)}, "
                  f"graph_edges={stor.get('graph_edges', 0)}")
        except httpx.HTTPStatusError as e:
            print(f"  → [ERROR] HTTP {e.response.status_code}: {e.response.text[:200]}")
        except Exception as e:
            print(f"  → [ERROR] {e}")

        # 批次间延迟（最后一批不等）
        if i + args.batch_size < len(files):
            print(f"  等待 {args.delay}s ...")
            time.sleep(args.delay)

    print(f"\n[完成] 共 kept {total_kept} 篇, {total_chunks} 个分块")

    # 4. 验证
    verify_results(client, project_id)

    client.close()


if __name__ == "__main__":
    main()
