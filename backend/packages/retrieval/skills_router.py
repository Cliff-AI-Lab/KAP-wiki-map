"""V8 SkillsRouter — 体系路径匹配器。

核心理念（对齐 §三 Skills 技术的真正用途）：
  "用户提问 → 匹配到体系中的某条线路（如：能源 → 安全部门 → 隐患排查）
   → 只调用该线路下的向量索引 → 大幅降低检索范围和 Token 消耗"

两阶段路由设计：
  Stage 1: 快速匹配（规则 + 关键词，无 LLM 调用）
  Stage 2: LLM 精确定位（仅在 Stage 1 置信度 < 0.8 时触发）

替代 V7 的 LLMRouter 在检索链中的角色：
  V7: IntentRouter → LLMRouter → Milvus
  V8: IntentRouter → SkillsRouter → 分支激活 Milvus
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from packages.common import get_logger
from packages.common.types import KnowledgeDomain
from packages.distillation.llm_client import call_llm_json

log = get_logger("retrieval.skills_router")

# Stage 2 LLM prompt
SKILLS_ROUTER_SYSTEM = """你是一名知识体系路由专家。你的任务是将用户的问题精确匹配到知识体系目录中的某条路径。

规则：
1. 从候选路径中选择最匹配的一条
2. 优先选择更具体的路径（L3 优于 L2 优于 L1）
3. 如果候选路径都不合适，返回空字符串
4. 必须严格输出 JSON 格式"""

SKILLS_ROUTER_USER = """## 知识体系目录
{catalog_text}

## 用户问题
{query}

## 候选路径（Stage 1 初筛结果）
{candidates_text}

## 请选择最匹配的路径，以 JSON 格式输出：
{{
  "domain_path": "选中的 domain_id 路径（如 energy/safety/hazard），如果都不合适则为空字符串",
  "reasoning": "选择理由（一句话）"
}}"""


@dataclass
class SkillsRoute:
    """SkillsRouter 的输出结果。"""
    domain_path: str = ""                          # "energy/safety/hazard"
    domain_name_chain: list[str] = field(default_factory=list)  # ["能源", "安全管理", "隐患排查"]
    confidence: float = 0.0                        # 0.0-1.0
    fallback_paths: list[str] = field(default_factory=list)     # 备选路径
    reasoning: str = ""                            # 路由推理


async def route_by_skills(
    query: str,
    project_id: str,
    domains: list[KnowledgeDomain],
    catalog_text: str,
) -> SkillsRoute:
    """V8 体系路径匹配器入口。

    按知识体系逐层定位：先快速匹配，不确定时再用 LLM 精确定位。
    """
    if not domains or not query.strip():
        return SkillsRoute()

    # 构建 domain_id → domain 映射
    domain_map = {d.domain_id: d for d in domains}

    # ── Stage 1: 快速匹配（关键词） ──
    candidates = _stage1_keyword_match(query, domains)

    if not candidates:
        log.info("skills_router_no_match", query=query[:60])
        return SkillsRoute(reasoning="无匹配路径")

    top_path, top_score = candidates[0]

    log.info(
        "skills_router_stage1",
        query=query[:60],
        top_path=top_path,
        top_score=round(top_score, 3),
        candidates=len(candidates),
    )

    # 高置信度 → 直接返回
    if top_score >= 0.8:
        name_chain = _build_name_chain(top_path, domain_map)
        return SkillsRoute(
            domain_path=top_path,
            domain_name_chain=name_chain,
            confidence=min(top_score, 1.0),
            fallback_paths=[c[0] for c in candidates[1:3]],
            reasoning=f"Stage 1 关键词高置信匹配: {top_path}",
        )

    # ── Stage 2: LLM 精确定位 ──
    try:
        candidates_text = "\n".join(
            f"- [{path}] (匹配度: {score:.2f})"
            for path, score in candidates[:5]
        )
        user_prompt = SKILLS_ROUTER_USER.format(
            catalog_text=catalog_text[:3000],  # 控制 token
            query=query,
            candidates_text=candidates_text,
        )
        data = call_llm_json(SKILLS_ROUTER_SYSTEM, user_prompt)
        llm_path = data.get("domain_path", "")
        llm_reasoning = data.get("reasoning", "")

        if llm_path and llm_path in domain_map:
            name_chain = _build_name_chain(llm_path, domain_map)
            log.info("skills_router_stage2_ok", path=llm_path, reasoning=llm_reasoning[:80])
            return SkillsRoute(
                domain_path=llm_path,
                domain_name_chain=name_chain,
                confidence=0.85,
                fallback_paths=[c[0] for c in candidates[:3] if c[0] != llm_path],
                reasoning=f"Stage 2 LLM: {llm_reasoning}",
            )
    except Exception as e:
        log.warning("skills_router_stage2_failed", error=str(e))

    # Stage 2 失败 → 用 Stage 1 结果
    name_chain = _build_name_chain(top_path, domain_map)
    return SkillsRoute(
        domain_path=top_path,
        domain_name_chain=name_chain,
        confidence=top_score,
        fallback_paths=[c[0] for c in candidates[1:3]],
        reasoning=f"Stage 1 fallback: {top_path}",
    )


def _stage1_keyword_match(
    query: str,
    domains: list[KnowledgeDomain],
) -> list[tuple[str, float]]:
    """Stage 1: 关键词匹配 — 将 query 中的词与知识体系节点匹配。

    对齐核心理念：按体系逐层打开，先定位分支。
    """
    # 分词（简单切分 + 滑动窗口）
    tokens = set()
    segments = re.split(r"[，。？！、\s,.\?!\n]+", query)
    for seg in segments:
        seg = seg.strip()
        if len(seg) >= 2:
            tokens.add(seg)
            # 2-4 字滑动窗口补充短词
            for width in (2, 3, 4):
                for i in range(len(seg) - width + 1):
                    tokens.add(seg[i:i + width])

    if not tokens:
        return []

    scores: list[tuple[str, float]] = []
    for domain in domains:
        # 构建域的关键词集合（名称 + 描述词）
        domain_words = set()
        domain_words.add(domain.name)
        # 从名称中提取子词
        if len(domain.name) > 2:
            for width in (2, 3, 4):
                for i in range(len(domain.name) - width + 1):
                    domain_words.add(domain.name[i:i + width])
        # 从描述中提取词
        if domain.description:
            for word in re.split(r"[，。、\s,./]+", domain.description):
                word = word.strip()
                if len(word) >= 2:
                    domain_words.add(word)

        # 计算匹配度
        overlap = tokens & domain_words
        if overlap:
            # 域名直接命中（权重最高）
            name_hit = 0.0
            if domain.name in tokens:
                name_hit = 1.0
            elif any(domain.name in t for t in tokens):
                name_hit = 0.8
            elif any(t in domain.name for t in tokens if len(t) >= 2):
                name_hit = 0.6
            overlap_score = len(overlap) / max(len(domain_words), 1)
            score = name_hit * 0.6 + overlap_score * 0.4
            scores.append((domain.domain_id, score))

    # 按分数排序，优先返回更具体的路径（L3 > L2 > L1）
    scores.sort(key=lambda x: (-x[1], -x[0].count("/")))
    return scores[:5]


def _build_name_chain(
    domain_path: str,
    domain_map: dict[str, KnowledgeDomain],
) -> list[str]:
    """构建域名称链。如 energy/safety/hazard → ["能源", "安全管理", "隐患排查"]。"""
    parts = domain_path.split("/")
    chain = []
    for i in range(len(parts)):
        path = "/".join(parts[: i + 1])
        d = domain_map.get(path)
        if d:
            chain.append(d.name)
    return chain
