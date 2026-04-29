"""块① 知识咨询智能体 API（决策书 §4 / PRD §3）。

端点：
  POST /architect/sessions                  创建对话（含 project_id + 初始样本）
  POST /architect/sessions/{id}/message     推进对话
  GET  /architect/sessions/{id}             查询完整 session
  GET  /architect/sessions/{id}/draft       获取主树草稿（YAML）
  POST /architect/sessions/{id}/export      触发导出 → 注册到 INDUSTRY_REGISTRY

权限：决策书 §4.1 锁定 DG 主导建体系。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from packages.architect import (
    export_to_industry_template,
    get_architect_agent,
    to_yaml,
)
from packages.common import get_logger
from packages.common.roles import ROLE_DG, RequireRole

log = get_logger("api.architect")

router = APIRouter(prefix="/architect", tags=["块① 咨询智能体"])


# ════════════════════════════════════════════════════════════════════════
#  Schemas
# ════════════════════════════════════════════════════════════════════════


class CreateSessionBody(BaseModel):
    project_id: str = Field(min_length=1)
    sample_texts: list[str] = Field(default_factory=list)


class MessageBody(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    sample_texts: list[str] = Field(default_factory=list)  # identify 阶段补传样本


class ExportBody(BaseModel):
    custom_code_suffix: str = Field(default="", max_length=32)
    register_globally: bool = True


class MessageResponse(BaseModel):
    session_id: str
    stage: str
    assistant: str
    draft: dict | None = None


# ════════════════════════════════════════════════════════════════════════
#  Endpoints
# ════════════════════════════════════════════════════════════════════════


@router.post("/sessions", response_model=dict)
async def create_session(
    body: CreateSessionBody,
    user=Depends(RequireRole(ROLE_DG)),
) -> dict:
    """新建对话会话（DG 主导建体系，§4.1）。"""
    agent = get_architect_agent()
    session = agent.create_session(
        project_id=body.project_id,
        sample_texts=body.sample_texts,
    )
    log.info("architect_api_session_created",
             session_id=session.session_id,
             user=getattr(user, "user_id", "?"))
    return {
        "session_id": session.session_id,
        "stage": session.stage,
        "project_id": session.project_id,
    }


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    user=Depends(RequireRole(ROLE_DG)),
) -> dict:
    """查询完整 session（含 history + draft）。"""
    agent = get_architect_agent()
    session = agent.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session 不存在")
    return session.model_dump()


@router.post("/sessions/{session_id}/message", response_model=MessageResponse)
async def post_message(
    session_id: str,
    body: MessageBody,
    user=Depends(RequireRole(ROLE_DG)),
) -> MessageResponse:
    """对话主入口 — 按当前 stage 路由到对应 transition。"""
    agent = get_architect_agent()
    try:
        result = await agent.process_message(
            session_id, body.content,
            sample_texts=body.sample_texts or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return MessageResponse(
        session_id=session_id,
        stage=result["stage"],
        assistant=result["assistant"],
        draft=result.get("draft"),
    )


@router.get("/sessions/{session_id}/draft", response_class=PlainTextResponse)
async def get_draft(
    session_id: str,
    user=Depends(RequireRole(ROLE_DG)),
) -> str:
    """获取主树草稿（YAML 格式，PRD F1.7.2）。"""
    agent = get_architect_agent()
    session = agent.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session 不存在")
    if session.draft is None or not session.draft.taxonomy:
        raise HTTPException(status_code=400, detail="session 尚未生成主树草稿")

    # 用 exporter 模拟一份不注册的 IndustryTemplate 转 YAML
    try:
        tpl = export_to_industry_template(session.draft, register_globally=False)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return to_yaml(tpl)


@router.post("/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    body: ExportBody,
    user=Depends(RequireRole(ROLE_DG)),
) -> dict:
    """完成导出 → 注册到 INDUSTRY_REGISTRY + 切 stage=export。"""
    agent = get_architect_agent()
    session = agent.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session 不存在")
    if session.draft is None:
        raise HTTPException(status_code=400, detail="session 尚未生成主树草稿")

    try:
        tpl = export_to_industry_template(
            session.draft,
            register_globally=body.register_globally,
            custom_code_suffix=body.custom_code_suffix,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # 切 stage
    session.stage = "export"
    log.info("architect_api_exported",
             session_id=session_id, code=tpl.code,
             user=getattr(user, "user_id", "?"))

    return {
        "session_id": session_id,
        "industry_code": tpl.code,
        "industry_name": tpl.name,
        "node_count": len(tpl.taxonomy),
        "registered": body.register_globally,
        "stage": session.stage,
    }
