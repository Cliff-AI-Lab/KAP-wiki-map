"""W1 脱敏 hook — 文档入库前调脱敏 + 映射持久化（决策书 §5.4 工位嵌入）。

调用流程（与决策书 §5.4 W1 解析后挂脱敏对齐）：

1. ingest endpoint 收到 RawDocument
2. 本 hook 调 ``redact_document`` 三类敏感识别 + 三策略脱敏
3. 把映射 (mapping_id → 原文) 持久化到加密 KV
4. 修改 doc.content 为脱敏文（pipeline 后续基于脱敏文做嵌入 + 入库）
5. doc.metadata 存 ``redaction_token_ids`` 用于审计追溯

M2 lite 范围：
- 单向量入库（vec_redacted），原文不入向量库（决策书双向量留 M3 双层入库批）
- 高密级用户访问原文走解码 endpoint（GET /sensitive/decode/{mapping_id}）
"""

from __future__ import annotations

from packages.common import get_logger
from packages.common.types import RawDocument
from packages.sensitive.mapping_store import SensitiveMappingStore
from packages.sensitive.redactor import (
    PrecisionLevel,
    RedactedToken,
    RedactResult,
    redact_document,
)

log = get_logger("sensitive.ingest_hook")


async def redact_and_persist_doc(
    doc: RawDocument,
    *,
    mapping_store: SensitiveMappingStore,
    client_whitelist: tuple[str, ...] = (),
    precision: PrecisionLevel = PrecisionLevel.INTERVAL,
    persist_mapping: bool = True,
) -> RedactResult:
    """对 RawDocument 做脱敏 + 持久化映射，**就地修改** doc.content 为脱敏文。

    Args:
        doc: 待脱敏文档（content 会被原地替换为脱敏文）
        mapping_store: 加密 KV 实例（已 initialize）
        client_whitelist: 客户名白名单
        precision: 工艺参数降精度级别
        persist_mapping: False 时只脱敏不存映射（dev / 测试 / 不可逆场景用）

    Returns:
        RedactResult — tokens 已写入 mapping_store（如启用）
    """
    if not doc.content:
        return RedactResult(redacted_text=doc.content)

    result = redact_document(
        doc.content,
        client_whitelist=client_whitelist,
        precision=precision,
    )

    if not result.tokens:
        # 无敏感片段，原文不变
        return result

    # 持久化映射（同 mapping_id 跨文档复用，幂等覆盖）
    if persist_mapping:
        seen: set[str] = set()
        for tok in result.tokens:
            if tok.mapping_id in seen:
                continue
            seen.add(tok.mapping_id)
            try:
                await mapping_store.put(
                    tok.mapping_id,
                    tok.original,
                    meta={
                        "category": tok.category.value,
                        "doc_id": doc.doc_id,
                        "extra": tok.extra or {},
                    },
                )
            except Exception as e:
                # 单条映射写入失败不阻断 ingest（脱敏文已生成）
                log.warning(
                    "sensitive_mapping_persist_failed",
                    mapping_id=tok.mapping_id, doc_id=doc.doc_id, error=str(e),
                )

    # 就地替换原文为脱敏文
    doc.content = result.redacted_text

    # 元数据记录被替换的 mapping_id 列表（供后续审计 + 解码 endpoint 反查）
    doc.metadata = {
        **doc.metadata,
        "redaction_token_ids": [tok.mapping_id for tok in result.tokens],
        "redaction_count": len(result.tokens),
    }

    log.info(
        "doc_redacted",
        doc_id=doc.doc_id,
        token_count=len(result.tokens),
        spans=len(result.spans),
    )
    return result


def collect_token_summary(tokens: list[RedactedToken]) -> dict:
    """辅助：把 token 列表归类计数（审计 / 监控用）。"""
    summary: dict[str, int] = {}
    for tok in tokens:
        cat = tok.category.value
        summary[cat] = summary.get(cat, 0) + 1
    return {"total": len(tokens), "by_category": summary}
