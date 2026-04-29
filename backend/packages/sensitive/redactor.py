"""敏感片段三策略脱敏器（决策书 §5.4 D10 锁定）。

| 类别        | 策略             | 示例                              |
|:------------|:-----------------|:----------------------------------|
| 人名        | 角色化替换        | "张工" → "研发员A"                |
| 工艺参数    | 三级降精度        | "120.5℃" → "[120-130℃]"（区间） |
| 客户名      | 代码化            | "上海某电厂" → "客户A001"         |

一致性关键（§5.4 表）：
- 全局映射表保证**跨文档同人名同 ID**（避免图谱断链）— 由 mapping_store 承担
- 数值区间宽度由 SME 按知识价值定，不一刀切（M1 默认 10% 区间）
- 客户编码与客户主数据系统对接（M1 用本地白名单顺序编号；M3 接 ISS 主数据）

输出 ``RedactResult`` 含脱敏后文本 + 替换映射 token 列表（写入 mapping_store）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum

from packages.sensitive.ner import SensitiveCategory, SensitiveSpan, detect_sensitive_spans


class PrecisionLevel(str, Enum):
    """工艺参数三级降精度（§5.4 行 430）。"""
    EXACT = "EXACT"        # 精确值（不脱敏）
    INTERVAL = "INTERVAL"  # 区间值（默认）
    LEVEL = "LEVEL"        # 等级标签（最低精度，仅高/中/低）


@dataclass
class RedactedToken:
    """单个被替换的 token：原文 + 占位符 + 类别。"""
    category: SensitiveCategory
    original: str
    placeholder: str  # 替换用的 token，如 "{P:研发员A}"
    mapping_id: str   # 加密 KV 中的 stable id（用于跨文档一致性）
    extra: dict | None = None


@dataclass
class RedactResult:
    """脱敏结果：脱敏后文本 + 替换 token 列表 + 原始 spans。"""
    redacted_text: str
    tokens: list[RedactedToken] = field(default_factory=list)
    spans: list[SensitiveSpan] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════════
#  内置角色字典（决策书 §5.4 "角色化替换"）
# ════════════════════════════════════════════════════════════════════════

# 头衔 → 标准角色名（M1 默认；客户可通过 sensitive_role_dict_path 覆盖）
_DEFAULT_TITLE_TO_ROLE: dict[str, str] = {
    "工": "工程师",
    "工程师": "工程师",
    "总": "管理者",
    "经理": "管理者",
    "主任": "管理者",
    "组长": "管理者",
    "师": "工程师",
    "博士": "研究员",
    "教授": "研究员",
    "研究员": "研究员",
}


def _role_for_title(title: str) -> str:
    return _DEFAULT_TITLE_TO_ROLE.get(title, "员工")


# ════════════════════════════════════════════════════════════════════════
#  Mapping ID — stable hash 保障跨文档一致性
# ════════════════════════════════════════════════════════════════════════


def _stable_id(category: SensitiveCategory, key: str) -> str:
    """同一原文 → 同一 mapping_id，跨文档一致（§5.4 一致性关键）。

    避免简单 uuid 导致同一人在两份文档里编号不同。
    """
    h = hashlib.sha256(f"{category.value}:{key}".encode("utf-8")).hexdigest()[:12]
    return f"{category.value[0].lower()}{h}"


# ════════════════════════════════════════════════════════════════════════
#  人名角色化
# ════════════════════════════════════════════════════════════════════════


def _redact_person(span: SensitiveSpan, counter: dict[str, int]) -> RedactedToken:
    title = (span.extra or {}).get("title", "")
    role = _role_for_title(title)
    mapping_id = _stable_id(SensitiveCategory.PERSON_NAME, span.text)
    # 序号化：研发员A / 研发员B / 工程师A...（跨文档稳定通过 mapping_id 第一次见到的顺序）
    counter.setdefault(role, 0)
    counter[role] += 1
    serial = chr(ord("A") + (counter[role] - 1) % 26)
    placeholder = f"{role}{serial}"
    return RedactedToken(
        category=SensitiveCategory.PERSON_NAME,
        original=span.text,
        placeholder=placeholder,
        mapping_id=mapping_id,
        extra={"role": role, "title": title},
    )


# ════════════════════════════════════════════════════════════════════════
#  工艺参数降精度
# ════════════════════════════════════════════════════════════════════════


def _redact_process_param(
    span: SensitiveSpan, level: PrecisionLevel
) -> RedactedToken:
    extra = span.extra or {}
    raw_value = extra.get("value", span.text)
    unit = extra.get("unit", "")
    mapping_id = _stable_id(SensitiveCategory.PROCESS_PARAM, span.text)

    if level == PrecisionLevel.EXACT:
        placeholder = span.text
    elif level == PrecisionLevel.LEVEL:
        # 简化等级判断：只看正负
        try:
            num = float(raw_value.split("-")[0].split("~")[0].replace(",", ""))
            grade = "高" if num >= 100 else ("中" if num >= 1 else "低")
        except (ValueError, AttributeError):
            grade = "中"
        placeholder = f"[{grade}{unit}]"
    else:  # INTERVAL（默认）
        try:
            # 已经是范围：保持
            if "-" in raw_value or "~" in raw_value or "～" in raw_value:
                placeholder = f"[{raw_value}{unit}]"
            else:
                num = float(raw_value.replace(",", ""))
                # ±10% 区间，保留 2 位小数
                lo = round(num * 0.9, 2)
                hi = round(num * 1.1, 2)
                placeholder = f"[{lo}-{hi}{unit}]"
        except ValueError:
            placeholder = f"[{raw_value}{unit}]"

    return RedactedToken(
        category=SensitiveCategory.PROCESS_PARAM,
        original=span.text,
        placeholder=placeholder,
        mapping_id=mapping_id,
        extra={"value": raw_value, "unit": unit, "precision": level.value},
    )


# ════════════════════════════════════════════════════════════════════════
#  客户名代码化
# ════════════════════════════════════════════════════════════════════════


def _redact_client(
    span: SensitiveSpan, counter: dict[str, int],
) -> RedactedToken:
    canonical = (span.extra or {}).get("canonical", span.text)
    mapping_id = _stable_id(SensitiveCategory.CLIENT_NAME, canonical)
    counter.setdefault("__client__", 0)
    counter["__client__"] += 1
    placeholder = f"客户A{counter['__client__']:03d}"
    return RedactedToken(
        category=SensitiveCategory.CLIENT_NAME,
        original=span.text,
        placeholder=placeholder,
        mapping_id=mapping_id,
        extra={"canonical": canonical},
    )


# ════════════════════════════════════════════════════════════════════════
#  完整文档脱敏
# ════════════════════════════════════════════════════════════════════════


def redact_document(
    text: str,
    *,
    client_whitelist: tuple[str, ...] = (),
    precision: PrecisionLevel = PrecisionLevel.INTERVAL,
) -> RedactResult:
    """对整段文本做脱敏。

    Args:
        text: 待脱敏明文
        client_whitelist: 客户白名单元组
        precision: 工艺参数降精度级别（默认 INTERVAL）

    Returns:
        RedactResult 含脱敏后文本 + 替换 token 列表
    """
    if not text:
        return RedactResult(redacted_text=text)

    spans = detect_sensitive_spans(text, client_whitelist=client_whitelist)
    if not spans:
        return RedactResult(redacted_text=text, spans=[])

    # 已见过的 mapping_id → placeholder（同一原文用同一替换 token）
    seen: dict[str, str] = {}
    counter: dict[str, int] = {}
    tokens: list[RedactedToken] = []

    # 从后往前替换避免 offset 漂移
    parts = list(text)
    for span in sorted(spans, key=lambda s: -s.start):
        if span.category == SensitiveCategory.PERSON_NAME:
            tok = _redact_person(span, counter)
        elif span.category == SensitiveCategory.PROCESS_PARAM:
            tok = _redact_process_param(span, precision)
        else:  # CLIENT_NAME
            tok = _redact_client(span, counter)

        # 一致性：跨 span 用 mapping_id 复用 placeholder
        if tok.mapping_id in seen:
            tok = RedactedToken(
                category=tok.category,
                original=tok.original,
                placeholder=seen[tok.mapping_id],
                mapping_id=tok.mapping_id,
                extra=tok.extra,
            )
        else:
            seen[tok.mapping_id] = tok.placeholder

        parts[span.start:span.end] = list(tok.placeholder)
        tokens.append(tok)

    tokens.reverse()  # 恢复正序便于审计
    return RedactResult(
        redacted_text="".join(parts),
        tokens=tokens,
        spans=spans,
    )
