"""ISS-System Remote HTTP 客户端（轻量版）。

设计原则（feedback memory · KAP 轻量化）：
- 只暴露 AI 流程**实际依赖**的最小协议
- 当前唯一用例：DataScope ``DEPT_AND_CHILD`` 需要拉取部门子树
- 显示侧的 user/dept 元数据查询不实现（KAP 块② 不需要，块③ 用 ISS-Gateway 转发即可）

部署假设：KAP Python 与 iss-system 在同一私有化集群内，``iss_system_base_url`` 直连。
未来接入 Nacos 服务发现是 M2+ 工作。
"""

from __future__ import annotations

import time

import httpx

from packages.common import get_logger, settings

log = get_logger("auth.iss_remote")

# 部门子树缓存：dept_id → (descendants_list, expires_at)
# 私有化场景部门变动很慢，TTL 5 分钟足够；ISS dept 修改后 5 分钟内 KAP 看不到子部门变化是可接受的代价
_dept_descendants_cache: dict[int, tuple[list[int], float]] = {}


def _cache_get(dept_id: int) -> list[int] | None:
    item = _dept_descendants_cache.get(dept_id)
    if item is None:
        return None
    descendants, expires_at = item
    if time.time() > expires_at:
        _dept_descendants_cache.pop(dept_id, None)
        return None
    return descendants


def _cache_set(dept_id: int, descendants: list[int]) -> None:
    expires = time.time() + settings.iss_dept_cache_ttl
    _dept_descendants_cache[dept_id] = (descendants, expires)


def reset_dept_cache_for_test() -> None:
    _dept_descendants_cache.clear()


async def fetch_dept_descendants(dept_id: int) -> list[int]:
    """拉取部门 + 所有子部门的 ID 列表（用于 DataScope DEPT_AND_CHILD）。

    返回值始终包含 ``dept_id`` 自身（即使 ISS 返回的子树不含自身）。
    超时或网络故障时**降级为 [dept_id]**（仅本部门），不抛异常 —— 让 AI
    流程不至于因 ISS 网络抖动整体不可用，宁可权限缩小不可扩大（安全偏向）。

    Args:
        dept_id: ISS 部门 ID

    Returns:
        包含自身和所有后代部门 ID 的列表（顺序无意义）
    """
    cached = _cache_get(dept_id)
    if cached is not None:
        return cached

    base_url = settings.iss_system_base_url
    if not base_url:
        log.warning("iss_system_base_url_unset_dept_descendants_fallback", dept_id=dept_id)
        return [dept_id]

    url = f"{base_url.rstrip('/')}/system/dept/list"
    params = {"parentId": dept_id}
    try:
        async with httpx.AsyncClient(
            timeout=settings.iss_remote_timeout,
            verify=settings.llm_verify_ssl,
        ) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("iss_dept_descendants_failed_fallback_self",
                    dept_id=dept_id, error=str(e))
        return [dept_id]

    # ISS R<List<SysDept>> 标准响应：{"code":200,"data":[{deptId,parentId,ancestors,...}]}
    raw_list = payload.get("data") or payload.get("rows") or []
    descendants: set[int] = {dept_id}
    for d in raw_list:
        try:
            descendants.add(int(d["deptId"]))
        except (KeyError, TypeError, ValueError):
            continue

    result = sorted(descendants)
    _cache_set(dept_id, result)
    return result
