"""Wiki API 路由 — 知识 Wiki 页的 CRUD 和编译触发。

V11.2: 三层 Wiki 体系 (Karpathy LLM Wiki)
  - source_summary: 每篇源文档的知识卡片
  - domain_overview: 域级概览页
  - index: 项目级全局索引

端点:
  GET  /wiki/pages           — 列出项目所有 Wiki 页 (支持 page_type 过滤)
  GET  /wiki/pages/{page_id} — 获取单个 Wiki 页（含 Markdown 全文）
  GET  /wiki/stats           — Wiki 统计（页数/覆盖率/分类计数）
  GET  /wiki/schema          — LLM 可读的 Schema 索引
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from pydantic import BaseModel

from packages.common import get_logger
from packages.common.types import WikiPage
from api.deps import get_wiki_store, get_domain_store
from api.middleware.auth import get_current_user
from packages.storage.wiki_store import WikiStore
from packages.storage.domain_store import DomainStore

log = get_logger("api.wiki")

router = APIRouter(prefix="/wiki", tags=["wiki"])


# ── Response Models ──

class WikiPageSummary(BaseModel):
    """Wiki 页摘要（列表用，不含全文）。"""
    page_id: str
    title: str
    summary: str
    page_type: str
    parent_page_id: str
    source_doc_count: int
    cross_ref_count: int
    compiled_at: str | None
    version: int
    status: str


class WikiPageDetail(BaseModel):
    """Wiki 页完整内容（含 Markdown）。"""
    page_id: str
    title: str
    content: str
    summary: str
    page_type: str
    parent_page_id: str
    source_doc_ids: list[str]
    cross_refs: list[str]
    compiled_at: str | None
    version: int
    status: str


class WikiStats(BaseModel):
    """Wiki 统计信息。"""
    total_pages: int
    published_pages: int
    stale_pages: int
    source_pages: int
    domain_pages: int
    index_pages: int
    total_source_docs: int
    domain_coverage: float


# ── Endpoints ──

@router.get("/pages", response_model=list[WikiPageSummary])
async def list_wiki_pages(
    request: Request,
    project_id: str = Query(default="default", description="项目ID"),
    page_type: str = Query(default="", description="页面类型过滤: source_summary/domain_overview/index"),
    wiki_store: WikiStore = Depends(get_wiki_store),
) -> list[WikiPageSummary]:
    """列出项目下所有 Wiki 页（不含全文内容）。

    RBAC: Wiki页是编译聚合产物，不保留源文档访问级别。
    PUBLIC 用户和有部门限制的用户应通过 RAG 路径获取过滤后的内容。
    """
    user = get_current_user(request)
    if user.org_id != "default" and user.org_id != project_id:
        raise HTTPException(403, "无权访问该项目的 Wiki 页")
    # RBAC: PUBLIC 用户不应直接读取可能含 INTERNAL 内容的 Wiki 页
    if hasattr(user, 'access_level') and user.access_level == "PUBLIC":
        raise HTTPException(403, "请通过知识检索获取内容")
    pages = await wiki_store.list_pages(
        project_id=project_id,
        page_type=page_type if page_type else None,
    )

    return [
        WikiPageSummary(
            page_id=p.page_id,
            title=p.title,
            summary=p.summary,
            page_type=p.page_type,
            parent_page_id=p.parent_page_id,
            source_doc_count=len(p.source_doc_ids),
            cross_ref_count=len(p.cross_refs),
            compiled_at=p.compiled_at.isoformat() if p.compiled_at else None,
            version=p.version,
            status=p.status,
        )
        for p in pages
    ]


@router.get("/pages/{page_id:path}", response_model=WikiPageDetail)
async def get_wiki_page(
    request: Request,
    page_id: str,
    project_id: str = Query(default="default", description="项目ID"),
    wiki_store: WikiStore = Depends(get_wiki_store),
) -> WikiPageDetail:
    """获取单个 Wiki 页的完整内容（含 Markdown 全文）。"""
    user = get_current_user(request)
    if user.org_id != "default" and user.org_id != project_id:
        raise HTTPException(403, "无权访问该项目的 Wiki 页")
    if hasattr(user, 'access_level') and user.access_level == "PUBLIC":
        raise HTTPException(403, "请通过知识检索获取内容")
    page = await wiki_store.get_page(page_id, project_id=project_id)

    if not page:
        raise HTTPException(status_code=404, detail=f"Wiki 页 '{page_id}' 不存在")

    return WikiPageDetail(
        page_id=page.page_id,
        title=page.title,
        content=page.content,
        summary=page.summary,
        page_type=page.page_type,
        parent_page_id=page.parent_page_id,
        source_doc_ids=page.source_doc_ids,
        cross_refs=page.cross_refs,
        compiled_at=page.compiled_at.isoformat() if page.compiled_at else None,
        version=page.version,
        status=page.status,
    )


class WikiPageUpdate(BaseModel):
    """V15 Phase G: Wiki 页编辑/创建请求体 (PUT = upsert 语义)。

    Karpathy LLM Wiki 第 9 条: Wiki 必须可被人编辑，LLM 只是草稿机。
    不存在则新建（保留 target_ref 格式的 page_id），存在则编辑（其他字段保留），
    存储层 version 自动 +1。
    """
    title: str
    content: str
    summary: str = ""
    page_type: str = "domain_overview"
    parent_page_id: str = ""
    source_doc_ids: list[str] = []
    cross_refs: list[str] = []
    status: str = "published"
    editor: str = "admin"


@router.put("/pages/{page_id:path}", response_model=WikiPageDetail)
async def update_wiki_page(
    request: Request,
    page_id: str,
    body: WikiPageUpdate,
    project_id: str = Query(default="default", description="项目ID"),
    wiki_store: WikiStore = Depends(get_wiki_store),
) -> WikiPageDetail:
    """V15 Phase G: 人工 upsert Wiki 页。存在则编辑保留未传字段，不存在则新建。"""
    user = get_current_user(request)
    if user.org_id != "default" and user.org_id != project_id:
        raise HTTPException(403, "无权编辑该项目的 Wiki 页")

    existing = await wiki_store.get_page(page_id, project_id=project_id)

    from packages.common.types import WikiPage
    updated = WikiPage(
        page_id=page_id,
        title=body.title,
        content=body.content,
        summary=body.summary or (existing.summary if existing else ""),
        page_type=body.page_type if not existing else existing.page_type,
        parent_page_id=body.parent_page_id if not existing else existing.parent_page_id,
        source_doc_ids=existing.source_doc_ids if existing else body.source_doc_ids,
        cross_refs=existing.cross_refs if existing else body.cross_refs,
        compiled_at=existing.compiled_at if existing else None,
        version=existing.version if existing else 0,  # upsert_page 内部 +1
        status=body.status,
    )
    await wiki_store.upsert_page(updated, project_id=project_id)
    action = "edited" if existing else "created"
    log.info(f"wiki_page_{action}", page_id=page_id, project_id=project_id,
             editor=body.editor, status=updated.status)

    fresh = await wiki_store.get_page(page_id, project_id=project_id)
    assert fresh is not None
    return WikiPageDetail(
        page_id=fresh.page_id,
        title=fresh.title,
        content=fresh.content,
        summary=fresh.summary,
        page_type=fresh.page_type,
        parent_page_id=fresh.parent_page_id,
        source_doc_ids=fresh.source_doc_ids,
        cross_refs=fresh.cross_refs,
        compiled_at=fresh.compiled_at.isoformat() if fresh.compiled_at else None,
        version=fresh.version,
        status=fresh.status,
    )


@router.get("/stats", response_model=WikiStats)
async def get_wiki_stats(
    request: Request,
    project_id: str = Query(default="default", description="项目ID"),
    wiki_store: WikiStore = Depends(get_wiki_store),
    domain_store: DomainStore = Depends(get_domain_store),
) -> WikiStats:
    """获取 Wiki 统计信息。"""
    user = get_current_user(request)
    if user.org_id != "default" and user.org_id != project_id:
        raise HTTPException(403, "无权访问该项目")

    pages = await wiki_store.list_pages(project_id=project_id)
    domains = domain_store.list_domains(project_id=project_id)

    published = [p for p in pages if p.status == "published"]
    stale = [p for p in pages if p.status == "stale"]
    source_pages = [p for p in pages if p.page_type == "source_summary"]
    domain_pages = [p for p in pages if p.page_type == "domain_overview"]
    index_pages = [p for p in pages if p.page_type == "index"]
    total_source_docs = sum(len(p.source_doc_ids) for p in domain_pages)

    l2_plus_domains = [d for d in domains if len(d.domain_id.split("/")) >= 2]
    wiki_domain_ids = {p.page_id for p in domain_pages}
    covered = sum(1 for d in l2_plus_domains if d.domain_id in wiki_domain_ids)
    coverage = covered / max(len(l2_plus_domains), 1)

    return WikiStats(
        total_pages=len(pages),
        published_pages=len(published),
        stale_pages=len(stale),
        source_pages=len(source_pages),
        domain_pages=len(domain_pages),
        index_pages=len(index_pages),
        total_source_docs=total_source_docs,
        domain_coverage=round(coverage, 2),
    )


class WikiSchema(BaseModel):
    """Schema 索引 — Karpathy 架构最顶层，LLM 可直接消费的知识目录。"""
    schema_text: str
    page_count: int
    domain_coverage: float
    compiled_domains: list[str]


@router.get("/schema", response_model=WikiSchema)
async def get_wiki_schema(
    request: Request,
    project_id: str = Query(default="default", description="项目ID"),
    wiki_store: WikiStore = Depends(get_wiki_store),
    domain_store: DomainStore = Depends(get_domain_store),
) -> WikiSchema:
    """生成 LLM 可读的 Schema 索引。"""
    user = get_current_user(request)
    if user.org_id != "default" and user.org_id != project_id:
        raise HTTPException(403, "无权访问该项目")

    pages = await wiki_store.list_pages(project_id=project_id)
    domains = domain_store.list_domains(project_id=project_id)
    domain_map = {d.domain_id: d for d in domains}

    domain_pages = [p for p in pages if p.page_type == "domain_overview" and p.status == "published"]
    source_pages = [p for p in pages if p.page_type == "source_summary" and p.status == "published"]

    # 按域分组 source pages
    domain_sources: dict[str, list[WikiPage]] = {}
    for sp in source_pages:
        domain_sources.setdefault(sp.parent_page_id, []).append(sp)

    lines = [
        "# 知识图鉴 Schema 索引",
        "",
        f"> 共 {len(domain_pages)} 个知识域 · {len(source_pages)} 篇文档 | 项目: {project_id}",
        "",
    ]

    for dp in sorted(domain_pages, key=lambda p: p.page_id):
        domain = domain_map.get(dp.page_id)
        depth = len(dp.page_id.split("/"))
        prefix = "#" * min(depth + 1, 4)

        domain_name = domain.name if domain else dp.title
        doc_count = len(dp.source_doc_ids)
        cross_count = len(dp.cross_refs)

        lines.append(f"{prefix} {domain_name} [{dp.page_id}]")
        if dp.summary:
            lines.append(f"摘要: {dp.summary}")
        lines.append(f"文档数: {doc_count} | 交叉引用: {cross_count} | 版本: v{dp.version}")

        # 列出该域下的源文档
        sources = domain_sources.get(dp.page_id, [])
        if sources:
            lines.append("源文档:")
            for sp in sources:
                lines.append(f"  - [{sp.page_id}] {sp.title}: {sp.summary[:80]}")

        if dp.cross_refs:
            refs = ", ".join(f"[[{ref}]]" for ref in dp.cross_refs[:5])
            lines.append(f"关联: {refs}")
        lines.append("")

    schema_text = "\n".join(lines)

    l2_plus = [d for d in domains if len(d.domain_id.split("/")) >= 2]
    wiki_ids = {p.page_id for p in domain_pages}
    coverage = sum(1 for d in l2_plus if d.domain_id in wiki_ids) / max(len(l2_plus), 1)

    return WikiSchema(
        schema_text=schema_text,
        page_count=len(domain_pages) + len(source_pages),
        domain_coverage=round(coverage, 2),
        compiled_domains=[p.page_id for p in domain_pages],
    )
