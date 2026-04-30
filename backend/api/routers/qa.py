"""
问答 API 路由模块。

提供智能问答接口，接收用户自然语言问题，经过意图识别、知识检索、答案生成后
返回答案及来源文档。支持按知识目录限定检索范围和按项目隔离。

路由前缀: /qa
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from api.deps import get_qa_engine
from api.middleware.auth import get_current_user
from api.schemas.qa import AskRequest, AskResponse, SourceItem
from packages.observability import arecord_query

router = APIRouter(prefix="/qa", tags=["问答"])
log = logging.getLogger("api.qa")


@router.post("/ask", response_model=AskResponse)
async def ask_question(req: AskRequest, request: Request) -> AskResponse:
    """智能问答接口。

    处理流程：
    1. 从请求上下文获取当前用户信息（权限级别、所属部门）
    2. 调用问答引擎执行检索增强生成（RAG）
    3. 将引擎返回的结果转换为 API 响应格式（来源内容截断为300字）

    异常处理：
    - AssertionError: 问答引擎未初始化，返回 503
    - 其他异常: 记录错误日志，返回 503 并附带异常类型名称
    """
    try:
        engine = get_qa_engine()
        user = get_current_user(request)
        result = await engine.ask(
            question=req.question,
            top_k=req.top_k,
            target_category=req.target_category,
            org_id=req.project_id,
            user_access_level=user.access_level,   # 用户权限级别，用于文档访问控制
            user_department=user.department_id,     # 用户所属部门，用于部门级数据隔离
        )
        # M7 #2 · 召回埋点（M11 #1 加 retrieved_doc_ids 让 GT 自动构造可用）
        try:
            await arecord_query(
                project_id=req.project_id or "",
                user_id=getattr(user, "user_id", "") or "",
                query_text=req.question,
                source_count=len(result.sources),
                retrieved_doc_ids=[s.doc_id for s in result.sources],
                latency_ms=int(result.latency_ms or 0),
            )
        except Exception:
            log.exception("query_log_record_failed")
        return AskResponse(
            answer=result.answer,
            sources=[
                SourceItem(
                    doc_id=s.doc_id,
                    title=s.title,
                    content=s.content[:300],        # 截断来源内容，避免响应过大
                    score=s.score,
                    vector_score=s.vector_score,
                    graph_score=s.graph_score,
                    catalog_weight=s.catalog_weight,
                    source_system=s.source_system,
                    category_path=s.category_path,
                )
                for s in result.sources
            ],
            intent_category=result.intent_category,
            latency_ms=result.latency_ms,
        )
    except AssertionError:
        raise HTTPException(status_code=503, detail="问答引擎未初始化，请稍后重试")
    except Exception as e:
        log.exception("qa_ask_failed")
        raise HTTPException(
            status_code=503,
            detail=f"问答服务暂时不可用：{type(e).__name__}",
        )
