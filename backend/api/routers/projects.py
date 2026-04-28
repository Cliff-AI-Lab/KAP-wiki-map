"""项目管理 API — 行业模板选择与项目 CRUD。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.deps import get_domain_store, get_metadata_store, get_project_store
from api.schemas.projects import (
    IndustryListItem,
    IndustryTemplateOut,
    ProjectCreate,
    ProjectDetail,
    ProjectSummary,
    ProjectUpdate,
)
from packages.templates import get_template, list_industries, template_to_domains

router = APIRouter(prefix="/projects", tags=["项目管理"])


# ── 行业模板 ────────────────────────────────────────────


@router.get("/industries", response_model=list[IndustryListItem])
async def list_industry_templates():
    """列出所有可选行业模板。"""
    return list_industries()


@router.get("/industries/{code}/template", response_model=IndustryTemplateOut)
async def get_industry_template(code: str):
    """获取某行业的完整四级知识体系模板。"""
    template = get_template(code)
    if not template:
        raise HTTPException(status_code=404, detail=f"行业模板 '{code}' 不存在")
    return template


# ── 项目 CRUD ───────────────────────────────────────────


@router.post("", response_model=ProjectSummary, status_code=201)
async def create_project(body: ProjectCreate):
    """创建项目：选择行业 → 快照模板 → 自动填充知识域。"""
    template = get_template(body.industry_code)
    if not template:
        raise HTTPException(status_code=400, detail=f"行业 '{body.industry_code}' 不存在")

    # 快照模板 JSON
    snapshot = template.model_dump()["taxonomy"]

    project_store = get_project_store()
    proj = await project_store.create_project(
        name=body.name,
        industry_code=body.industry_code,
        description=body.description,
        taxonomy_snapshot=snapshot,
    )

    # 将模板展平为 KnowledgeDomain 并写入 domain_store
    domains = template_to_domains(template, proj["id"])
    domain_store = get_domain_store()
    for d in domains:
        await domain_store.upsert_domain(d, project_id=proj["id"])

    return ProjectSummary(
        id=proj["id"],
        name=proj["name"],
        industry_code=proj["industry_code"],
        industry_name=template.name,
        description=proj["description"],
        status=proj["status"],
        doc_count=0,
        domain_count=len(domains),
        created_at=proj["created_at"],
    )


@router.get("", response_model=list[ProjectSummary])
async def list_projects():
    """列出所有活跃项目。"""
    project_store = get_project_store()
    domain_store = get_domain_store()
    metadata_store = get_metadata_store()

    projects = project_store.list_projects()
    result = []
    for p in projects:
        pid = p["id"]
        domains = domain_store.list_domains(project_id=pid)
        # 统计文档数
        doc_count = 0
        docs = await metadata_store.list_documents(org_id=pid)
        doc_count = len(docs) if isinstance(docs, list) else docs.get("total", 0)

        industry_name = ""
        t = get_template(p["industry_code"])
        if t:
            industry_name = t.name

        result.append(ProjectSummary(
            id=pid,
            name=p["name"],
            industry_code=p["industry_code"],
            industry_name=industry_name,
            description=p.get("description", ""),
            status=p.get("status", "ACTIVE"),
            doc_count=doc_count,
            domain_count=len(domains),
            created_at=p.get("created_at"),
        ))
    return result


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: str):
    """获取项目详情（含知识体系快照）。"""
    project_store = get_project_store()
    proj = project_store.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")

    domain_store = get_domain_store()
    domains = domain_store.list_domains(project_id=project_id)

    industry_name = ""
    t = get_template(proj["industry_code"])
    if t:
        industry_name = t.name

    return ProjectDetail(
        id=proj["id"],
        name=proj["name"],
        industry_code=proj["industry_code"],
        industry_name=industry_name,
        description=proj.get("description", ""),
        status=proj.get("status", "ACTIVE"),
        doc_count=0,
        domain_count=len(domains),
        taxonomy_snapshot=proj.get("taxonomy_snapshot"),
        created_at=proj.get("created_at"),
        updated_at=proj.get("updated_at"),
    )


@router.put("/{project_id}", response_model=ProjectSummary)
async def update_project(project_id: str, body: ProjectUpdate):
    """更新项目信息。"""
    project_store = get_project_store()
    proj = await project_store.update_project(
        project_id,
        name=body.name,
        description=body.description,
        status=body.status,
    )
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")

    industry_name = ""
    t = get_template(proj["industry_code"])
    if t:
        industry_name = t.name

    return ProjectSummary(
        id=proj["id"],
        name=proj["name"],
        industry_code=proj["industry_code"],
        industry_name=industry_name,
        description=proj.get("description", ""),
        status=proj.get("status", "ACTIVE"),
        created_at=proj.get("created_at"),
    )
