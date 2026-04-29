"""敏感实体识别（决策书 §5.4 三类敏感数据 NER）。

M1 lite：函数式 NER（正则 + 字典）。不上 LLM-NER（M3 LLM-Critic 6 维质疑批做）。

三类识别策略：

- **PERSON_NAME** 人名 — 中文姓氏 + 头衔后缀 / 显式角色称谓正则
- **PROCESS_PARAM** 工艺参数 — 数字 + 单位（℃ / MPa / kg / kV / r/min 等）
- **CLIENT_NAME** 客户名 — 白名单实体匹配（M1 用配置项；M3 接客户主数据系统）

返回 ``SensitiveSpan`` 列表，含字符 offset，**不修改原文**（决策书 §5.4 工位嵌入：
"W1 解析后 → 脱敏 Agent 标记敏感片段（不修改原文，仅打 span 标签）"）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from packages.common import get_logger

log = get_logger("sensitive.ner")


class SensitiveCategory(str, Enum):
    PERSON_NAME = "PERSON_NAME"      # 人名
    PROCESS_PARAM = "PROCESS_PARAM"  # 工艺参数（数值 + 单位）
    CLIENT_NAME = "CLIENT_NAME"      # 客户名


@dataclass(frozen=True)
class SensitiveSpan:
    """敏感片段：文档中的一段连续字符。"""
    category: SensitiveCategory
    start: int
    end: int
    text: str
    extra: dict | None = None  # 类别特定信息，如 PROCESS_PARAM 含 (value, unit)


# ════════════════════════════════════════════════════════════════════════
#  PERSON_NAME — 中文人名 + 头衔
# ════════════════════════════════════════════════════════════════════════

# 常见姓氏 + 1-2 字名 + 可选头衔（工 / 总 / 经理 / 主任 / 师 / 博士 / 教授）
# 例："张工" "李总" "王主任" "陈博士" "赵小华"
_COMMON_SURNAMES = (
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐"
    "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄"
)

_TITLE_SUFFIXES = ("工", "总", "经理", "主任", "师", "博士", "教授", "工程师", "研究员", "组长")
_TITLE_RE = "|".join(re.escape(t) for t in sorted(_TITLE_SUFFIXES, key=len, reverse=True))

# 姓 + 1-2 字名 + 头衔后缀
_PERSON_PATTERN = re.compile(
    rf"(?P<name>[{_COMMON_SURNAMES}][一-龥]{{0,2}})(?P<title>{_TITLE_RE})"
)


def _detect_person_names(text: str) -> list[SensitiveSpan]:
    spans = []
    for m in _PERSON_PATTERN.finditer(text):
        spans.append(SensitiveSpan(
            category=SensitiveCategory.PERSON_NAME,
            start=m.start(),
            end=m.end(),
            text=m.group(0),
            extra={"surname": m.group("name")[:1], "title": m.group("title")},
        ))
    return spans


# ════════════════════════════════════════════════════════════════════════
#  PROCESS_PARAM — 工艺参数（数字 + 单位）
# ════════════════════════════════════════════════════════════════════════

# 常见单位（按长度倒序，避免 km 误匹配 m）
_UNITS = (
    "MPa", "kPa", "Pa", "bar",
    "℃", "°C", "K",
    "kg/m³", "kg/m3", "g/L", "mol/L", "ppm", "ppb",
    "r/min", "rpm", "Hz", "kHz",
    "kV", "V", "kA", "A", "kW", "W", "MW",
    "kg", "g", "mg", "t",
    "m³", "m3", "L", "mL",
    "mm/s", "m/s", "km/h",
    "mm", "cm", "m", "km",
    "%", "‰",
)
_UNITS_RE = "|".join(re.escape(u) for u in sorted(_UNITS, key=len, reverse=True))

# 数字（含负号、小数、范围 a-b、千分位逗号、单位前空格可选）
_PROCESS_PARAM_PATTERN = re.compile(
    rf"(?P<value>-?\d{{1,4}}(?:,\d{{3}})*(?:\.\d+)?(?:\s*[-~～]\s*-?\d{{1,4}}(?:\.\d+)?)?)\s*"
    rf"(?P<unit>{_UNITS_RE})"
)


def _detect_process_params(text: str) -> list[SensitiveSpan]:
    spans = []
    for m in _PROCESS_PARAM_PATTERN.finditer(text):
        spans.append(SensitiveSpan(
            category=SensitiveCategory.PROCESS_PARAM,
            start=m.start(),
            end=m.end(),
            text=m.group(0),
            extra={"value": m.group("value").strip(), "unit": m.group("unit")},
        ))
    return spans


# ════════════════════════════════════════════════════════════════════════
#  CLIENT_NAME — 客户名白名单匹配
# ════════════════════════════════════════════════════════════════════════


def _detect_client_names(
    text: str, client_whitelist: tuple[str, ...]
) -> list[SensitiveSpan]:
    """从客户白名单中扫描出现位置（按长度倒序避免子串覆盖）。"""
    spans = []
    sorted_clients = sorted(client_whitelist, key=len, reverse=True)
    occupied: list[tuple[int, int]] = []

    def _overlaps(s: int, e: int) -> bool:
        return any(not (e <= os or s >= oe) for os, oe in occupied)

    for client in sorted_clients:
        if not client:
            continue
        start = 0
        while True:
            idx = text.find(client, start)
            if idx < 0:
                break
            end = idx + len(client)
            if not _overlaps(idx, end):
                spans.append(SensitiveSpan(
                    category=SensitiveCategory.CLIENT_NAME,
                    start=idx,
                    end=end,
                    text=client,
                    extra={"canonical": client},
                ))
                occupied.append((idx, end))
            start = end
    return spans


# ════════════════════════════════════════════════════════════════════════
#  入口
# ════════════════════════════════════════════════════════════════════════


def detect_sensitive_spans(
    text: str,
    *,
    client_whitelist: tuple[str, ...] = (),
    categories: tuple[SensitiveCategory, ...] | None = None,
) -> list[SensitiveSpan]:
    """检测文本中的所有敏感片段。

    Args:
        text: 待扫描的文本（W1 解析后的明文）
        client_whitelist: 客户名白名单元组（默认空，需要客户配置）
        categories: 限定要检测的类别；默认全部三类

    Returns:
        按 start offset 升序排列的 SensitiveSpan 列表
    """
    if not text:
        return []

    cats = categories or (
        SensitiveCategory.PERSON_NAME,
        SensitiveCategory.PROCESS_PARAM,
        SensitiveCategory.CLIENT_NAME,
    )

    spans: list[SensitiveSpan] = []
    if SensitiveCategory.PERSON_NAME in cats:
        spans.extend(_detect_person_names(text))
    if SensitiveCategory.PROCESS_PARAM in cats:
        spans.extend(_detect_process_params(text))
    if SensitiveCategory.CLIENT_NAME in cats and client_whitelist:
        spans.extend(_detect_client_names(text, client_whitelist))

    spans.sort(key=lambda s: (s.start, s.end))
    return spans
