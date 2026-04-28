"""飞书连接器 — 支持真实 API 模式和模拟数据模式。"""

from __future__ import annotations

from typing import AsyncIterator

import httpx

from packages.common import get_logger, settings
from packages.common.exceptions import ConnectorError
from packages.common.types import RawDocument, SourceSystem
from packages.connectors.base import ConnectorBase
from packages.connectors.feishu.mock_data import MOCK_DOCUMENTS

log = get_logger("connector.feishu")


class FeishuConnector(ConnectorBase):
    source_system = SourceSystem.FEISHU

    def __init__(self) -> None:
        self._mock_mode = settings.feishu_mock_mode
        self._access_token: str | None = None
        self._client: httpx.AsyncClient | None = None

    # ── 连接 / 授权 ─────────────────────────────────

    async def connect(self) -> None:
        if self._mock_mode:
            log.info("feishu_connector_mock_mode", doc_count=len(MOCK_DOCUMENTS))
            return

        self._client = httpx.AsyncClient(
            base_url="https://open.feishu.cn/open-apis",
            timeout=30.0,
        )
        await self._obtain_tenant_token()
        log.info("feishu_connector_connected")

    async def _obtain_tenant_token(self) -> None:
        """通过 app_id/app_secret 获取 tenant_access_token。"""
        assert self._client is not None
        resp = await self._client.post(
            "/auth/v3/tenant_access_token/internal",
            json={
                "app_id": settings.feishu_app_id,
                "app_secret": settings.feishu_app_secret,
            },
        )
        data = resp.json()
        if data.get("code") != 0:
            raise ConnectorError(f"飞书授权失败: {data.get('msg')}")
        self._access_token = data["tenant_access_token"]

    # ── 拉取文档 ─────────────────────────────────────

    async def fetch_documents(self, incremental: bool = True) -> AsyncIterator[RawDocument]:
        if self._mock_mode:
            async for doc in self._fetch_mock():
                yield doc
        else:
            async for doc in self._fetch_real(incremental):
                yield doc

    async def _fetch_mock(self) -> AsyncIterator[RawDocument]:
        """从模拟数据生成 RawDocument 流。"""
        for item in MOCK_DOCUMENTS:
            doc = RawDocument(
                doc_id=item["doc_id"],
                title=item["title"],
                content=item["content"],
                source_system=SourceSystem.FEISHU,
                source_id=item.get("source_id", ""),
                created_at=item.get("created_at"),
                updated_at=item.get("updated_at"),
                created_by=item.get("created_by", ""),
                last_modifier=item.get("last_modifier", ""),
                file_size=len(item["content"].encode("utf-8")),
            )
            log.info("feishu_mock_doc", doc_id=doc.doc_id, title=doc.title)
            yield doc

    async def _fetch_real(self, incremental: bool) -> AsyncIterator[RawDocument]:
        """通过飞书开放 API 拉取知识库文档（待完整实现）。"""
        assert self._client is not None and self._access_token is not None
        headers = {"Authorization": f"Bearer {self._access_token}"}

        # 获取知识库空间列表
        resp = await self._client.get("/wiki/v2/spaces", headers=headers)
        data = resp.json()
        if data.get("code") != 0:
            raise ConnectorError(f"获取知识库列表失败: {data.get('msg')}")

        for space in data.get("data", {}).get("items", []):
            space_id = space["space_id"]
            async for doc in self._fetch_space_docs(space_id, headers):
                yield doc

    async def _fetch_space_docs(
        self, space_id: str, headers: dict
    ) -> AsyncIterator[RawDocument]:
        """拉取单个知识空间下的文档。"""
        assert self._client is not None
        page_token = ""
        while True:
            params = {"space_id": space_id, "page_size": 50}
            if page_token:
                params["page_token"] = page_token

            resp = await self._client.get(
                f"/wiki/v2/spaces/{space_id}/nodes",
                headers=headers,
                params=params,
            )
            data = resp.json()

            for node in data.get("data", {}).get("items", []):
                content = await self._get_doc_content(node["obj_token"], headers)
                yield RawDocument(
                    doc_id=f"feishu_{node['node_token']}",
                    title=node.get("title", "无标题"),
                    content=content,
                    source_system=SourceSystem.FEISHU,
                    source_id=node["node_token"],
                    file_size=len(content.encode("utf-8")),
                )

            page_token = data.get("data", {}).get("page_token", "")
            if not data.get("data", {}).get("has_more", False):
                break

    async def _get_doc_content(self, doc_token: str, headers: dict) -> str:
        """获取单个文档的正文内容。"""
        assert self._client is not None
        resp = await self._client.get(
            f"/docx/v1/documents/{doc_token}/raw_content",
            headers=headers,
        )
        data = resp.json()
        return data.get("data", {}).get("content", "")

    # ── 健康检查 ─────────────────────────────────────

    async def health_check(self) -> bool:
        if self._mock_mode:
            return True
        try:
            assert self._client is not None
            resp = await self._client.get("/auth/v3/app_access_token/internal")
            return resp.status_code == 200
        except Exception:
            return False

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
