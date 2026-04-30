"""LLM 自学习闭环 lite（M11 #4 · 决策书 §5.3 prompt 调优追踪）。

M10 #2 仅给"调优建议"。M11 #4 让 SME 真正切换 prompt 后，能量化对比新旧
prompt 的 SME 接受率，形成自学习反馈闭环。

设计（feedback memory · 轻量化）：
- 不替换 evolution_proposer 实际硬编码 prompt（prompts.py）
- 仅追踪 prompt_text_excerpt 元数据（200 字摘要） + 激活时间窗
- 4 监测条件每个同时最多一个 active 版本
- 切换 active 时关闭旧版本（deactivated_at = now）
- AB 比较：把 proposals 按 created_at 落到对应版本的 [activated_at, deactivated_at) 区间，
  按 condition_type + version_id 算 approve_rate

不做（M12+）：
- 真改 evolution_proposer 在调 LLM 时按 active 版本动态拼 prompt
- prompt 多级 A/B 灰度切换
- 自动 promote 高分 prompt
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Awaitable, Callable, Literal

from pydantic import BaseModel, Field

from packages.common import get_logger
from packages.common.types import OntologyEvolutionProposal
from packages.observability.condition_health import (
    ConditionType, classify_condition,
)

log = get_logger("observability.prompt_versions")


class PromptVersion(BaseModel):
    """监测条件 prompt 版本元数据（M11 #4 + M12 #1）。

    M11 #4：仅元数据 + 时间窗 AB 比较；不改实际 prompt。
    M12 #1：增加 ``system_prompt`` 全文字段，evolution_proposer 在调 LLM 时
    按 active 版本动态选用（非空时覆盖硬编码，空则 fallback）。
    """
    version_id: str
    condition_type: ConditionType
    prompt_text_excerpt: str = ""              # 200 字摘要（兼容 M11 #4 老字段）
    system_prompt: str = ""                     # M12 #1：完整 system prompt 覆盖
    created_by: str = ""                        # SME user_id
    activated_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))
    deactivated_at: datetime | None = None     # None = 当前 active
    note: str = ""


class PromptABScore(BaseModel):
    """单 prompt 版本在其活跃期间的接受率（M11 #4 AB 比较单元）。"""
    version_id: str
    condition_type: ConditionType
    activated_at: datetime
    deactivated_at: datetime | None
    is_active: bool
    sample_size: int = 0
    approved: int = 0
    rejected: int = 0
    pending: int = 0
    approve_rate: float = 0.0


# ════════════════════════════════════════════════════════════════════════
#  内存存储（M11 lite，M12 PG 持久化）
# ════════════════════════════════════════════════════════════════════════

_versions: dict[str, PromptVersion] = {}

# M12 #2 PG sinks
_upsert_sink: Callable[[PromptVersion], Awaitable[None]] | None = None
_deactivate_sink: Callable[[str, datetime], Awaitable[None]] | None = None


def reset_prompt_versions_for_test() -> None:
    global _upsert_sink, _deactivate_sink
    _versions.clear()
    _upsert_sink = None
    _deactivate_sink = None


def set_prompt_version_pg_sinks(
    *,
    upsert_sink: Callable[[PromptVersion], Awaitable[None]] | None = None,
    deactivate_sink: Callable[[str, datetime], Awaitable[None]] | None = None,
) -> None:
    """注入 PG sinks（pg_prompt_versions.initialize 调用）。"""
    global _upsert_sink, _deactivate_sink
    _upsert_sink = upsert_sink
    _deactivate_sink = deactivate_sink


def _fire_and_forget(coro_factory) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro_factory())
    except RuntimeError:
        pass


def list_prompt_versions(
    *,
    condition_type: ConditionType | None = None,
    only_active: bool = False,
) -> list[PromptVersion]:
    out = list(_versions.values())
    if condition_type is not None:
        out = [v for v in out if v.condition_type == condition_type]
    if only_active:
        out = [v for v in out if v.deactivated_at is None]
    out.sort(key=lambda v: v.activated_at, reverse=True)
    return out


def get_active_version(
    condition_type: ConditionType,
) -> PromptVersion | None:
    for v in _versions.values():
        if v.condition_type == condition_type and v.deactivated_at is None:
            return v
    return None


def get_version(version_id: str) -> PromptVersion | None:
    return _versions.get(version_id)


def create_prompt_version(
    *,
    condition_type: ConditionType,
    prompt_text_excerpt: str = "",
    system_prompt: str = "",
    created_by: str = "",
    note: str = "",
) -> PromptVersion:
    """创建新 prompt 版本并激活（自动停用同 condition_type 的旧 active）。

    Args:
        prompt_text_excerpt: 200 字摘要（M11 #4 兼容）
        system_prompt: M12 #1 完整 system prompt（非空 → evolution_proposer
                       在调 LLM 时优先使用此值；为空则 fallback 硬编码）
    """
    now = datetime.now(tz=None)

    # 自动停用同 condition_type 的当前 active
    old = get_active_version(condition_type)
    if old is not None:
        old.deactivated_at = now
        log.info(
            "prompt_version_auto_deactivated",
            old_id=old.version_id, condition_type=condition_type,
        )
        if _upsert_sink is not None:
            _fire_and_forget(lambda: _upsert_sink(old))

    new = PromptVersion(
        version_id=f"pver_{uuid.uuid4().hex[:10]}",
        condition_type=condition_type,
        prompt_text_excerpt=prompt_text_excerpt[:200],
        system_prompt=system_prompt,                # 不截断，完整存
        created_by=created_by,
        activated_at=now,
        note=note[:200],
    )
    _versions[new.version_id] = new
    log.info(
        "prompt_version_created",
        version_id=new.version_id,
        condition_type=condition_type,
        created_by=created_by or "system",
        has_system_prompt=bool(system_prompt),
    )
    if _upsert_sink is not None:
        _fire_and_forget(lambda: _upsert_sink(new))
    return new


def resolve_active_system_prompt(
    condition_type: ConditionType, fallback: str,
) -> str:
    """供 evolution_proposer 使用：取 active 版本的 system_prompt（非空时），否则 fallback。"""
    active = get_active_version(condition_type)
    if active is not None and active.system_prompt:
        return active.system_prompt
    return fallback


def deactivate_prompt_version(version_id: str) -> bool:
    """手动停用某个版本（已停用则返回 False）。"""
    v = _versions.get(version_id)
    if v is None or v.deactivated_at is not None:
        return False
    v.deactivated_at = datetime.now(tz=None)
    log.info(
        "prompt_version_deactivated",
        version_id=version_id, condition_type=v.condition_type,
    )
    if _deactivate_sink is not None:
        _fire_and_forget(lambda: _deactivate_sink(version_id, v.deactivated_at))
    return True


# ════════════════════════════════════════════════════════════════════════
#  AB 比较
# ════════════════════════════════════════════════════════════════════════


def _proposal_in_window(
    proposal: OntologyEvolutionProposal,
    activated_at: datetime,
    deactivated_at: datetime | None,
) -> bool:
    created = proposal.created_at
    if created < activated_at:
        return False
    if deactivated_at is not None and created >= deactivated_at:
        return False
    return True


def compute_prompt_ab_score(
    proposals: list[OntologyEvolutionProposal],
    *,
    condition_type: ConditionType | None = None,
) -> list[PromptABScore]:
    """按 prompt 版本 AB 比较 SME 接受率。

    Args:
        proposals: 全部 proposals（status pending/approved/rejected）
        condition_type: None = 全部条件；指定时只看该条件的版本

    Returns:
        每个 PromptVersion 一行评分（按 activated_at 倒序，最新优先）
    """
    versions = list_prompt_versions(condition_type=condition_type)
    out: list[PromptABScore] = []
    for v in versions:
        # 过滤匹配 condition_type 的 proposals
        in_scope = [
            p for p in proposals
            if classify_condition(p) == v.condition_type
            and _proposal_in_window(p, v.activated_at, v.deactivated_at)
        ]
        approved = sum(1 for p in in_scope if p.status == "approved")
        rejected = sum(1 for p in in_scope if p.status == "rejected")
        pending = sum(1 for p in in_scope if p.status == "pending")
        decided = approved + rejected
        approve_rate = round(
            approved / decided, 4,
        ) if decided > 0 else 0.0

        out.append(PromptABScore(
            version_id=v.version_id,
            condition_type=v.condition_type,
            activated_at=v.activated_at,
            deactivated_at=v.deactivated_at,
            is_active=v.deactivated_at is None,
            sample_size=len(in_scope),
            approved=approved,
            rejected=rejected,
            pending=pending,
            approve_rate=approve_rate,
        ))
    return out
