"""三块互调 HTTP 客户端（M21 #1）。

约定的服务边界：

咨询中心（architect, :8011）
  POST /api/v1/architect/sessions                创建对话会话
  POST /api/v1/architect/sessions/{id}/message   发消息
  GET  /api/v1/architect/sessions/{id}/draft     拉本体草稿（人/机可读）

知识中心（storage, :8012）
  POST /api/v1/projects                          创建项目（接收 architect 草稿落库）
  POST /api/v1/ontology/migration/import         导入 L2 本体（M20 #2）
  POST /api/v1/wiki/compile                      触发 Wiki 编译
  GET  /api/v1/wiki/pages                        列 Wiki 页（供 portal 检索）
  GET  /api/v1/knowledge/documents               列文档（供 portal 检索）

消费中心（portal, :8013）
  POST /api/v1/qa/ask                            三路召回问答
  GET  /api/v1/observability/dashboard           运营仪表盘

无缝衔接典型链路：
  用户 → 咨询中心对话 → architect 输出 schema 草稿
       ↓ StorageClient.import_l2_ontology()
  知识中心 → 落 L2 + 编译 Wiki + 抽实体到图
       ↓ PortalClient.warmup_search_index()
  消费中心 → 用户在 ReaderHome 搜索 → 三路召回
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import httpx

from packages.common import get_logger

log = get_logger("integration.clients")


_DEFAULT_TIMEOUT = 30.0
_DEFAULT_HTTP_VERIFY = True


class BlockClient:
    """三块通用 HTTP 客户端基类（AsyncClient · 无同步阻塞）。"""

    def __init__(
        self,
        *,
        base_url: str,
        token: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        verify_ssl: bool = _DEFAULT_HTTP_VERIFY,
        block_name: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.block_name = block_name or "?"
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            verify=verify_ssl,
            headers=self._headers(),
        )

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json", "User-Agent": "kap-integration/1.0"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()

    async def health(self) -> dict[str, Any]:
        r = await self._client.get("/health")
        r.raise_for_status()
        return r.json()


# ════════════════════════════════════════════════════════════════════════
#  ArchitectClient · 调用咨询中心
# ════════════════════════════════════════════════════════════════════════


class ArchitectClient(BlockClient):
    """咨询中心客户端（其他块调用此处发起对话 / 拉草稿）。"""

    def __init__(self, **kw):
        super().__init__(block_name="architect", **kw)

    async def create_session(self, *, industry_hint: str = "") -> dict:
        r = await self._client.post(
            "/api/v1/architect/sessions",
            json={"industry_hint": industry_hint},
        )
        r.raise_for_status()
        return r.json()

    async def send_message(self, session_id: str, content: str) -> dict:
        r = await self._client.post(
            f"/api/v1/architect/sessions/{session_id}/message",
            json={"content": content},
        )
        r.raise_for_status()
        return r.json()

    async def get_draft(self, session_id: str) -> str:
        r = await self._client.get(
            f"/api/v1/architect/sessions/{session_id}/draft",
        )
        r.raise_for_status()
        return r.text


# ════════════════════════════════════════════════════════════════════════
#  StorageClient · 调用知识中心
# ════════════════════════════════════════════════════════════════════════


class StorageClient(BlockClient):
    """知识中心客户端（咨询中心 / 消费中心调用此处落库 / 查询）。"""

    def __init__(self, **kw):
        super().__init__(block_name="storage", **kw)

    async def import_l2_ontology(
        self, *, target_project_id: str, bundle: dict,
        on_conflict: str = "rename",
    ) -> dict:
        """咨询中心建好本体后调用此 API 落入知识中心 L2。"""
        r = await self._client.post(
            "/api/v1/ontology/migration/import",
            json={
                "target_project_id": target_project_id,
                "bundle": bundle,
                "on_conflict": on_conflict,
            },
        )
        r.raise_for_status()
        return r.json()

    async def list_wiki_pages(self, *, project_id: str = "") -> list[dict]:
        params = {"project_id": project_id} if project_id else None
        r = await self._client.get("/api/v1/wiki/pages", params=params)
        r.raise_for_status()
        return r.json()

    async def list_documents(self, *, project_id: str = "") -> list[dict]:
        params = {"project_id": project_id} if project_id else None
        r = await self._client.get("/api/v1/knowledge/documents", params=params)
        r.raise_for_status()
        return r.json()


# ════════════════════════════════════════════════════════════════════════
#  PortalClient · 调用消费中心
# ════════════════════════════════════════════════════════════════════════


class PortalClient(BlockClient):
    """消费中心客户端（仪表盘 / 召回测试 / 问答转发）。"""

    def __init__(self, **kw):
        super().__init__(block_name="portal", **kw)

    async def ask(
        self, *, question: str, project_id: str = "",
        top_k: int = 5,
    ) -> dict:
        r = await self._client.post(
            "/api/v1/qa/ask",
            json={"question": question, "project_id": project_id, "top_k": top_k},
        )
        r.raise_for_status()
        return r.json()

    async def get_dashboard(self, *, project_id: str = "") -> dict:
        params = {"project_id": project_id} if project_id else None
        r = await self._client.get(
            "/api/v1/observability/dashboard", params=params,
        )
        r.raise_for_status()
        return r.json()


# ════════════════════════════════════════════════════════════════════════
#  环境变量驱动的客户端工厂
# ════════════════════════════════════════════════════════════════════════


def _resolve_base(env_key: str, default: str) -> str:
    return os.environ.get(env_key) or default


def _resolve_token() -> str | None:
    return os.environ.get("KAP_INTEGRATION_TOKEN") or None


@asynccontextmanager
async def get_architect_client(
    *, base_url: str | None = None, token: str | None = None,
):
    client = ArchitectClient(
        base_url=base_url or _resolve_base("KAP_ARCHITECT_BASE", "http://localhost:8011"),
        token=token or _resolve_token(),
    )
    try:
        yield client
    finally:
        await client.aclose()


@asynccontextmanager
async def get_storage_client(
    *, base_url: str | None = None, token: str | None = None,
):
    client = StorageClient(
        base_url=base_url or _resolve_base("KAP_STORAGE_BASE", "http://localhost:8012"),
        token=token or _resolve_token(),
    )
    try:
        yield client
    finally:
        await client.aclose()


@asynccontextmanager
async def get_portal_client(
    *, base_url: str | None = None, token: str | None = None,
):
    client = PortalClient(
        base_url=base_url or _resolve_base("KAP_PORTAL_BASE", "http://localhost:8013"),
        token=token or _resolve_token(),
    )
    try:
        yield client
    finally:
        await client.aclose()
