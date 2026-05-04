"""KAP 三块互调 HTTP 客户端（M21 #1 · 松耦合）。

- 三块各自独立部署时，通过约定的 HTTP API 互相调用
- 单体部署时，HTTP 调用本进程的同一 API（base_url=http://127.0.0.1:8001）
- Client 默认走 ``httpx.AsyncClient``（KAP 强约束：禁止同步 httpx.Client）

使用方式：
    from packages.integration import get_storage_client

    async with get_storage_client() as client:
        await client.commit_l2_ontology(project_id="p1", ...)

环境变量：
    KAP_ARCHITECT_BASE   咨询中心 base URL（默认 http://localhost:8011）
    KAP_STORAGE_BASE     知识中心 base URL（默认 http://localhost:8012）
    KAP_PORTAL_BASE      消费中心 base URL（默认 http://localhost:8013）
    KAP_INTEGRATION_TOKEN  服务间互调 JWT/api_key（夹在 Authorization header）
"""

from packages.integration.clients import (
    ArchitectClient,
    BlockClient,
    PortalClient,
    StorageClient,
    get_architect_client,
    get_portal_client,
    get_storage_client,
)

__all__ = [
    "ArchitectClient",
    "BlockClient",
    "PortalClient",
    "StorageClient",
    "get_architect_client",
    "get_portal_client",
    "get_storage_client",
]
