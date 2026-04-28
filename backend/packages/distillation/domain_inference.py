"""Domain ID 推断（坑 4b 改造产物）。

把原本散落在 ``llm_client._mock_infer_domain_id``（硬编码关键词）和
``refiner._clean_domain_id``（防御性清洗）里的 domain 推断逻辑，
统一到本模块：

- **关键词字典外置**：从 ``templates/<industry>/domain-keywords.yaml`` 加载
- **优先级匹配**：rules 列表按优先级降序匹配，命中即返回
- **路径净化**：兼容 LLM 的多种异常输出格式（带方括号、L1 前缀、引号、逗号等）
- **兜底改 routing_pending**：未识别的不再硬编码到 ``regulation``，
  而是返回 ``ROUTING_PENDING_DOMAIN_ID`` 触发 W2 工位 DG 主审（决策书 §5.2）

YAML schema 示例（见 ``templates/energy/domain-keywords.yaml``）::

    rules:
      - domain_id: "energy/safety/hazard"
        priority: 100
        keywords: ["隐患", "安全检查", "安全隐患"]
      - domain_id: "energy/safety"
        priority: 50
        keywords: ["安全", "安全生产"]

匹配规则：

- 同一文档可能命中多条 rule → 取 ``priority`` 最高（数值最大）的
- ``priority`` 相同时，取 keyword 命中数最多的
- 仍并列时，取 ``domain_id`` 字典序较前的（保证确定性）
- 全部 miss → 返回 ``DomainInferenceResult(domain_id=ROUTING_PENDING_DOMAIN_ID, ...)``
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from packages.common import get_logger
from packages.distillation.templates_loader import load_yaml

log = get_logger("domain_inference")

# 兜底 domain：未识别时返回，由上游路由到 W2 DG 主审队列
ROUTING_PENDING_DOMAIN_ID = "routing_pending"


@dataclass(frozen=True, slots=True)
class DomainKeywordRule:
    """单条关键词匹配规则。"""

    domain_id: str
    priority: int          # 越高越优先
    keywords: tuple[str, ...]  # tuple 而非 list 以便 hash & frozen


@dataclass(frozen=True, slots=True)
class DomainInferenceResult:
    """推断结果。"""

    domain_id: str
    confidence: float           # 0-1，命中关键词数 / 总关键词数 的近似
    matched_keywords: tuple[str, ...]
    rule_priority: int          # 命中规则的 priority；未命中为 0
    source: str                 # YAML 来源标识或 "code-fallback"


@lru_cache(maxsize=32)
def load_rules(industry: str | None = None) -> tuple[tuple[DomainKeywordRule, ...], str]:
    """加载行业的 domain 关键词规则。返回 (rules, source)。

    失败时返回 (空 tuple, "code-fallback")，调用方应做好"全部不匹配"的预案。
    """
    target = (industry or "_default").strip().lower()
    loaded = load_yaml(target, "domain-keywords.yaml")
    if loaded is None:
        log.warning("domain_keywords_missing", industry=target)
        return (), "code-fallback"

    data, source = loaded
    raw_rules = data.get("rules", [])
    rules: list[DomainKeywordRule] = []
    for entry in raw_rules:
        if not isinstance(entry, dict):
            continue
        domain_id = entry.get("domain_id")
        keywords = entry.get("keywords")
        if not domain_id or not keywords:
            log.warning("domain_keywords_skip_invalid", entry=entry, source=source)
            continue
        try:
            rule = DomainKeywordRule(
                domain_id=str(domain_id),
                priority=int(entry.get("priority", 0)),
                keywords=tuple(str(k) for k in keywords),
            )
        except (ValueError, TypeError) as e:
            log.warning("domain_keywords_skip_malformed", error=str(e), entry=entry)
            continue
        rules.append(rule)

    # 按 priority 降序排，方便后续短路
    rules.sort(key=lambda r: -r.priority)
    log.info("domain_rules_loaded", industry=target, rule_count=len(rules), source=source)
    return tuple(rules), source


# ──────── 路径净化（合并自原 refiner._clean_domain_id）────────


def clean_domain_id(raw: str) -> str:
    """清洗 LLM 返回的 domain_id，提取纯净路径。

    LLM 可能返回：

      - 正确：``"tech/architecture"``
      - 带标注：``"L1 [tech]: 技术文档 — ..."``
      - 多级拼接：``"L1 [product]/L2 [product/roadmap]"``
      - 带引号：``"'L1 [quality]'"``

    统一提取方括号中最具体（最长）的 domain_id。无方括号时退化为字符串清洗。
    """
    if not raw:
        return ""
    raw = raw.strip().strip("'\"")

    # 提取所有 [xxx] 中的内容；取最长（最具体）
    brackets = re.findall(r"\[([^\]]+)\]", raw)
    if brackets:
        return max(brackets, key=len)

    cleaned = re.sub(r"^L\d+\s*", "", raw)
    cleaned = re.sub(r"^L\d+/", "", cleaned)
    if ":" in cleaned:
        cleaned = cleaned.split(":")[0].strip()
    if "," in cleaned:
        cleaned = cleaned.split(",")[0].strip()
    return cleaned.lstrip("/")


# ──────── 关键词推断 ────────


def infer_domain_id(
    text: str,
    industry: str | None = None,
    *,
    title: str = "",
) -> DomainInferenceResult:
    """根据文本内容推断 domain_id（基于 YAML 关键词字典）。

    Args:
        text: 文档内容（可只传前几百字，节省匹配开销）
        industry: 行业模板名；为 None 时走 ``_default``
        title: 文档标题（与 text 拼接后参与匹配，权重相同）

    Returns:
        ``DomainInferenceResult``。未识别时 ``domain_id`` 为
        ``ROUTING_PENDING_DOMAIN_ID``，置信度为 0。

    Notes:
        - 无 IO，无副作用，可单测
        - 关键词匹配是 substring 包含（``in``），不是分词
        - 性能：rules 已按 priority 降序，命中第一条最高优先级即可短路
        - "matched_keywords" 字段对调试 / SME 复核非常有用
    """
    rules, source = load_rules(industry)
    if not rules:
        return DomainInferenceResult(
            domain_id=ROUTING_PENDING_DOMAIN_ID,
            confidence=0.0,
            matched_keywords=(),
            rule_priority=0,
            source=source,
        )

    haystack = (title + " " + text)[:4000]  # 限制长度避免长文档低效匹配

    # 找出所有命中的 rule + 命中关键词数；按 priority 降序、命中数降序、domain_id 字典序选
    candidates: list[tuple[DomainKeywordRule, list[str]]] = []
    for rule in rules:
        hit_words = [kw for kw in rule.keywords if kw in haystack]
        if hit_words:
            candidates.append((rule, hit_words))
            # priority 最高的一组中如果第一个就命中且仅看 priority，可短路；
            # 但需要"同 priority 取最多匹配"，所以先收集全部同 priority 的

    if not candidates:
        return DomainInferenceResult(
            domain_id=ROUTING_PENDING_DOMAIN_ID,
            confidence=0.0,
            matched_keywords=(),
            rule_priority=0,
            source=source,
        )

    # 排序键：priority 降序 → 命中关键词数降序 → domain_id 字典序升序
    candidates.sort(key=lambda c: (-c[0].priority, -len(c[1]), c[0].domain_id))
    best_rule, best_hits = candidates[0]

    # 置信度：命中数 / 该 rule 总关键词数（封顶 1.0）
    confidence = min(len(best_hits) / max(len(best_rule.keywords), 1), 1.0)

    return DomainInferenceResult(
        domain_id=best_rule.domain_id,
        confidence=round(confidence, 3),
        matched_keywords=tuple(best_hits),
        rule_priority=best_rule.priority,
        source=source,
    )
