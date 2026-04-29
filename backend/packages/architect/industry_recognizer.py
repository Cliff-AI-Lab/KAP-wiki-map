"""行业识别（PRD F1.2，参考 SkillsRouter 两阶段思路）。

Stage 1 — 关键词初筛（无 LLM 调用）：
  对 INDUSTRY_REGISTRY 中每个 IndustryTemplate，计算 taxonomy 节点名 +
  业务域代码与样本文本的命中率。

Stage 2 — LLM 二轮判定（仅 Stage 1 max confidence < 0.7 时触发）：
  把 top 3 候选 + 命中证据 + 样本片段交给 LLM 选择最匹配的，
  返回带 reasoning 的最终结果。

设计原则（feedback memory · 轻量化）：
- 函数式实现（dataclass + async function），不上类层级
- Stage 1 命中率高时直接返回，省 LLM 调用成本
- LLM 失败时降级到 Stage 1 结果（不阻断 architect 流程）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from packages.architect.prompts import (
    INDUSTRY_RECOGNIZE_SYSTEM,
    INDUSTRY_RECOGNIZE_USER,
)
from packages.common import get_logger
from packages.common.types import IndustryCandidate
from packages.distillation.llm_client import acall_llm_json
from packages.templates.registry import INDUSTRY_REGISTRY, IndustryTemplate, TaxonomyNode

log = get_logger("architect.industry_recognizer")


@dataclass
class IndustryRecognitionResult:
    """行业识别结果。"""
    industry_code: str = ""
    industry_name: str = ""
    confidence: float = 0.0
    top_candidates: list[IndustryCandidate] = field(default_factory=list)
    recognized_signals: list[str] = field(default_factory=list)  # PRD F1.2.5 识别依据
    reasoning: str = ""
    stage_used: str = "stage1"  # stage1 | stage2


# ════════════════════════════════════════════════════════════════════════
#  Stage 1 — 关键词初筛
# ════════════════════════════════════════════════════════════════════════


def _collect_keywords(taxonomy: list[TaxonomyNode]) -> list[str]:
    """从模板 taxonomy 递归收集所有节点名（含中文 + L2 部门）。

    用于 Stage 1 关键词命中匹配。
    """
    out: list[str] = []
    for n in taxonomy:
        if n.name and len(n.name) >= 2:
            out.append(n.name)
        if n.children:
            out.extend(_collect_keywords(n.children))
    return out


def _stage1_keyword_match(
    sample_texts: list[str],
    template: IndustryTemplate,
) -> tuple[float, list[str]]:
    """单模板的关键词命中率 + 命中证据。

    Returns:
        (confidence, matched_keywords)
        confidence ∈ [0, 1]：命中关键词的样本覆盖率
    """
    keywords = _collect_keywords(template.taxonomy)
    if not keywords or not sample_texts:
        return 0.0, []

    joined = " ".join(sample_texts)
    matched: list[str] = []
    for kw in keywords:
        # 子串匹配（中文场景下分词成本高，子串足够）
        if kw in joined and kw not in matched:
            matched.append(kw)

    # 置信度：命中关键词数 / sqrt(模板关键词总数) — 防止小模板天然占优
    if not matched:
        return 0.0, []
    confidence = min(1.0, len(matched) / max(5, len(keywords) ** 0.5 * 2))
    return confidence, matched


def _stage1_rank(sample_texts: list[str]) -> list[IndustryCandidate]:
    """对 INDUSTRY_REGISTRY 全部模板做 Stage 1 排序。"""
    candidates: list[IndustryCandidate] = []
    for code, tpl in INDUSTRY_REGISTRY.items():
        conf, matched = _stage1_keyword_match(sample_texts, tpl)
        candidates.append(IndustryCandidate(
            industry_code=code,
            industry_name=tpl.name,
            confidence=conf,
            matched_keywords=matched[:8],  # top 8 命中关键词，避免 prompt 过长
        ))
    candidates.sort(key=lambda c: -c.confidence)
    return candidates


# ════════════════════════════════════════════════════════════════════════
#  Stage 2 — LLM 二轮判定
# ════════════════════════════════════════════════════════════════════════


async def _stage2_llm_judge(
    sample_texts: list[str],
    top_candidates: list[IndustryCandidate],
) -> IndustryRecognitionResult | None:
    """LLM 在 top 3 候选中选最匹配的。

    失败返回 None（让上层降级到 Stage 1 结果）。
    """
    candidates_text = "\n".join(
        f"- {c.industry_code} ({c.industry_name}): "
        f"Stage 1 conf={c.confidence:.2f}, 命中关键词={c.matched_keywords[:5]}"
        for c in top_candidates
    )
    samples_text = "\n".join(f"- {s[:200]}" for s in sample_texts[:10])
    stage1_summary = f"Stage 1 max confidence={top_candidates[0].confidence:.2f}（< 0.7，需 LLM 二轮判定）"

    user_prompt = INDUSTRY_RECOGNIZE_USER.format(
        candidates_text=candidates_text,
        sample_texts=samples_text,
        stage1_summary=stage1_summary,
    )

    try:
        data = await acall_llm_json(INDUSTRY_RECOGNIZE_SYSTEM, user_prompt)
    except Exception as e:
        log.warning("industry_recognize_stage2_failed", error=str(e))
        return None

    chosen_code = (data.get("industry_code") or "").strip()
    if not chosen_code:
        return None

    # 校验 LLM 返回的 code 必须在候选里（避免幻觉）
    chosen = next(
        (c for c in top_candidates if c.industry_code == chosen_code),
        None,
    )
    if chosen is None:
        log.warning(
            "industry_recognize_llm_invalid_code",
            llm_code=chosen_code,
            valid=[c.industry_code for c in top_candidates],
        )
        return None

    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    signals_raw = data.get("recognized_signals") or []
    signals = [str(s)[:80] for s in signals_raw[:8] if isinstance(s, (str, int, float))]
    if not signals:
        signals = chosen.matched_keywords[:5]

    return IndustryRecognitionResult(
        industry_code=chosen.industry_code,
        industry_name=chosen.industry_name,
        confidence=confidence,
        top_candidates=top_candidates,
        recognized_signals=signals,
        reasoning=str(data.get("reasoning", ""))[:200],
        stage_used="stage2",
    )


# ════════════════════════════════════════════════════════════════════════
#  入口
# ════════════════════════════════════════════════════════════════════════


# Stage 1 高置信度阈值 — 高于此值直接采纳，跳过 LLM 调用
_STAGE1_HIGH_CONFIDENCE = 0.7


async def recognize_industry(
    sample_texts: list[str],
    *,
    custom_industries: tuple[str, ...] = (),  # M3 客户共建机制（M2 lite 占位）
) -> IndustryRecognitionResult:
    """识别客户行业（PRD F1.2）。

    Args:
        sample_texts: 上传材料的标题 + 摘要片段
        custom_industries: M3 客户额外指定行业 code（M2 lite 暂未用）

    Returns:
        IndustryRecognitionResult — 含 industry_code / confidence / signals
    """
    if not sample_texts:
        return IndustryRecognitionResult()

    # Stage 1
    candidates = _stage1_rank(sample_texts)
    top = candidates[:3]
    if not top or top[0].confidence == 0.0:
        log.info("industry_recognize_no_match")
        return IndustryRecognitionResult(top_candidates=top)

    # Stage 1 高置信度 → 直接采纳
    if top[0].confidence >= _STAGE1_HIGH_CONFIDENCE:
        log.info(
            "industry_recognize_stage1_high",
            industry=top[0].industry_code,
            confidence=top[0].confidence,
        )
        return IndustryRecognitionResult(
            industry_code=top[0].industry_code,
            industry_name=top[0].industry_name,
            confidence=top[0].confidence,
            top_candidates=top,
            recognized_signals=top[0].matched_keywords[:5],
            reasoning="Stage 1 关键词命中率高，直接采纳",
            stage_used="stage1",
        )

    # Stage 2 LLM 二轮判定
    stage2 = await _stage2_llm_judge(sample_texts, top)
    if stage2 is not None:
        log.info(
            "industry_recognize_stage2_done",
            industry=stage2.industry_code,
            confidence=stage2.confidence,
        )
        return stage2

    # Stage 2 失败 → 降级到 Stage 1 top 1（confidence 已是 < 0.7）
    log.warning("industry_recognize_stage2_fallback_to_stage1")
    return IndustryRecognitionResult(
        industry_code=top[0].industry_code,
        industry_name=top[0].industry_name,
        confidence=top[0].confidence,
        top_candidates=top,
        recognized_signals=top[0].matched_keywords[:5],
        reasoning="Stage 2 LLM 调用失败，降级 Stage 1",
        stage_used="stage1_fallback",
    )
