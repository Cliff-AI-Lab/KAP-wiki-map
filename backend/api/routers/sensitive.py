"""敏感映射解码 API（决策书 §5.4 D11 + §8.2 全链路审计）。

端点:
  GET  /sensitive/decode/{mapping_id} — 高密级用户访问原文
  GET  /sensitive/summary?doc_id=... — 文档敏感映射摘要（审计用）

权限语义：
- decode 端点要求 max_access_level >= ACCESS_CONFIDENTIAL（秘密级 = 2）
- 每次解码写审计日志（user_id + mapping_id + timestamp）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from packages.common import get_logger
from packages.common.roles import ACCESS_CONFIDENTIAL, RequireAccessLevel
from packages.sensitive.mapping_store import (
    MappingStoreError,
    get_mapping_store,
)

log = get_logger("api.sensitive")

router = APIRouter(prefix="/sensitive", tags=["敏感数据"])


@router.get("/decode/{mapping_id}")
async def decode_mapping(
    mapping_id: str,
    request: Request,
    user=Depends(RequireAccessLevel(ACCESS_CONFIDENTIAL)),
) -> dict:
    """解码敏感映射 → 返回原文。

    要求用户密级 ≥ CONFIDENTIAL（秘密级）。
    每次访问写审计日志（决策书 §5.4 "映射表的每次读取都写审计日志"）。
    """
    if not mapping_id or len(mapping_id) > 64:
        raise HTTPException(status_code=400, detail="mapping_id 非法")

    store = get_mapping_store()
    try:
        data = await store.get(mapping_id)
    except MappingStoreError as e:
        log.error("decode_store_error", mapping_id=mapping_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"映射读取失败: {e}") from e

    if data is None:
        raise HTTPException(status_code=404, detail="mapping_id 不存在")

    # 审计日志（决策书 §5.4 D11 强制）
    log.info(
        "sensitive_mapping_accessed",
        mapping_id=mapping_id,
        user_id=getattr(user, "user_id", "unknown"),
        access_level=getattr(user, "max_access_level", -1),
        ip=request.client.host if request.client else "?",
    )

    return {
        "mapping_id": mapping_id,
        "original": data.get("original"),
        "meta": data.get("meta", {}),
        "decoded_by": getattr(user, "user_id", "unknown"),
    }


@router.get("/summary")
async def mapping_summary(
    doc_id: str,
    user=Depends(RequireAccessLevel(ACCESS_CONFIDENTIAL)),
) -> dict:
    """返回某文档的敏感映射数量摘要（不解码，只看分类计数）。

    用途：审计员核查文档脱敏情况，不暴露原文。
    """
    # 当前 mapping_store 没有按 doc_id 索引（M2 lite），返回提示
    # M3 加 doc → mapping_id 反向索引后实现完整查询
    return {
        "doc_id": doc_id,
        "user": getattr(user, "user_id", "unknown"),
        "note": "M2 lite：完整摘要功能在 M3 双层入库批引入反向索引后启用",
    }
