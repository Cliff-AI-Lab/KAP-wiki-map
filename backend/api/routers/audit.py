"""
审计日志 API 路由模块。

提供审计日志的查询接口，支持按操作类型过滤和分页限制。
所有审计查询自动限定在当前用户所属组织范围内，确保数据隔离。

路由前缀: /audit
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request

from api.deps import get_audit_logger
from api.middleware.auth import get_current_user

router = APIRouter(prefix="/audit", tags=["审计"])


@router.get("/logs")
async def list_audit_logs(
    request: Request,
    action: Optional[str] = Query(default=None, description="按操作类型过滤"),
    limit: int = Query(default=100, ge=1, le=1000, description="返回条数上限"),
) -> list[dict]:
    """查询审计日志。

    根据当前登录用户的组织ID查询审计记录，可按操作类型（如 ingest、delete、ask 等）
    进行过滤，默认返回最近100条记录。
    """
    user = get_current_user(request)  # 从请求上下文提取当前用户信息
    audit = get_audit_logger()
    return await audit.list_logs(org_id=user.org_id, action=action, limit=limit)
