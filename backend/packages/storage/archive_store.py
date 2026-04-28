"""影子归档存储 — DISCARD 文档的 MinIO 归档与恢复。

DISCARD 文档进入影子归档，保留 30 天，期间可人工恢复。
PoC 阶段使用本地目录作为 fallback，无需强依赖 MinIO。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from packages.common import get_logger, settings

log = get_logger("storage.archive")

# 影子归档默认保留天数
ARCHIVE_RETENTION_DAYS = 30


class ArchiveStore:
    """影子归档存储，支持 MinIO 和本地目录模式。"""

    def __init__(self, use_local: bool = False):
        self._use_local = use_local
        self._client = None
        self._bucket = settings.minio_bucket
        self._local_dir = Path("data/archive")

    async def initialize(self) -> None:
        if self._use_local:
            self._local_dir.mkdir(parents=True, exist_ok=True)
            log.info("archive_store_local_mode", path=str(self._local_dir))
            return

        try:
            from minio import Minio

            self._client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=False,
            )

            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                log.info("archive_bucket_created", bucket=self._bucket)

            # 设置生命周期策略：自动删除超过保留期的归档
            self._set_lifecycle_policy()
            log.info("archive_store_minio_connected", bucket=self._bucket)

        except Exception as e:
            log.warning("archive_store_fallback_to_local", error=str(e))
            self._use_local = True
            self._local_dir.mkdir(parents=True, exist_ok=True)

    def _set_lifecycle_policy(self) -> None:
        """设置 MinIO 生命周期策略，自动清理过期归档。"""
        try:
            from minio.lifecycleconfig import LifecycleConfig, Rule, Expiration

            config = LifecycleConfig(
                [Rule(
                    rule_id="auto-expire-archive",
                    status="Enabled",
                    expiration=Expiration(days=ARCHIVE_RETENTION_DAYS),
                )],
            )
            self._client.set_bucket_lifecycle(self._bucket, config)
        except Exception as e:
            log.warning("lifecycle_policy_set_failed", error=str(e))

    async def archive_document(
        self,
        doc_id: str,
        content: str,
        metadata: dict,
    ) -> str:
        """归档一篇 DISCARD 文档，返回归档 key。"""
        archive_key = f"discard/{doc_id}.json"
        archive_data = {
            "doc_id": doc_id,
            "content": content,
            "metadata": metadata,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "expires_at_days": ARCHIVE_RETENTION_DAYS,
        }
        payload = json.dumps(archive_data, ensure_ascii=False, default=str)

        if self._use_local:
            file_path = self._local_dir / f"{doc_id}.json"
            file_path.write_text(payload, encoding="utf-8")
            log.info("archive_local_saved", doc_id=doc_id, path=str(file_path))
            return archive_key

        from io import BytesIO

        data_bytes = payload.encode("utf-8")
        self._client.put_object(
            self._bucket,
            archive_key,
            BytesIO(data_bytes),
            length=len(data_bytes),
            content_type="application/json",
        )
        log.info("archive_minio_saved", doc_id=doc_id, key=archive_key)
        return archive_key

    async def restore_document(self, doc_id: str) -> Optional[dict]:
        """从归档恢复一篇文档，返回原始数据。"""
        if self._use_local:
            file_path = self._local_dir / f"{doc_id}.json"
            if not file_path.exists():
                log.warning("archive_local_not_found", doc_id=doc_id)
                return None
            data = json.loads(file_path.read_text(encoding="utf-8"))
            log.info("archive_local_restored", doc_id=doc_id)
            return data

        archive_key = f"discard/{doc_id}.json"
        try:
            response = self._client.get_object(self._bucket, archive_key)
            data = json.loads(response.read().decode("utf-8"))
            response.close()
            response.release_conn()
            log.info("archive_minio_restored", doc_id=doc_id, key=archive_key)
            return data
        except Exception as e:
            log.warning("archive_restore_failed", doc_id=doc_id, error=str(e))
            return None

    async def delete_archive(self, doc_id: str) -> bool:
        """删除归档记录（恢复成功后清理）。"""
        if self._use_local:
            file_path = self._local_dir / f"{doc_id}.json"
            if file_path.exists():
                file_path.unlink()
                return True
            return False

        archive_key = f"discard/{doc_id}.json"
        try:
            self._client.remove_object(self._bucket, archive_key)
            log.info("archive_deleted", doc_id=doc_id)
            return True
        except Exception as e:
            log.warning("archive_delete_failed", doc_id=doc_id, error=str(e))
            return False

    async def list_archived(self) -> list[dict]:
        """列出所有归档文档的摘要信息。"""
        items: list[dict] = []

        if self._use_local:
            for f in self._local_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    items.append({
                        "doc_id": data["doc_id"],
                        "archived_at": data.get("archived_at", ""),
                        "metadata": data.get("metadata", {}),
                    })
                except Exception:
                    continue
            return items

        try:
            objects = self._client.list_objects(self._bucket, prefix="discard/")
            for obj in objects:
                doc_id = obj.object_name.replace("discard/", "").replace(".json", "")
                items.append({
                    "doc_id": doc_id,
                    "archived_at": obj.last_modified.isoformat() if obj.last_modified else "",
                    "size": obj.size,
                })
        except Exception as e:
            log.warning("archive_list_failed", error=str(e))

        return items

    async def close(self) -> None:
        """清理资源。"""
        self._client = None
