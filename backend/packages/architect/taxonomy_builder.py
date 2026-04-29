"""主树提议 + 简单 CRUD（PRD F1.3 lite）。

M2 lite 范围：
- ``propose_taxonomy``：从 IndustryTemplate 取基础主树 → LLM 评估每个一级业务域是否
  匹配客户样本 → 输出 keep/drop/highlight 决策（**只动 L2，不重写 L3/L4**）
- ``apply_user_command``：自然语言命令 → add/remove/rename L2 节点
  · 简单关键词匹配（"删除 X" / "重命名 X 为 Y" / "新增 X"）
  · M3 接 LLM 命令解析处理复杂场景（合并 / 拆分 / 协同）

设计原则（feedback memory · 轻量化）：
- 函数式实现，状态随 TaxonomyDraft 流转
- LLM 失败时降级到"全保留"（不删任何节点，避免误伤）
"""

from __future__ import annotations

import re

from packages.architect.prompts import (
    TAXONOMY_PROPOSE_SYSTEM,
    TAXONOMY_PROPOSE_USER,
)
from packages.common import get_logger
from packages.common.types import TaxonomyDraft
from packages.distillation.llm_client import acall_llm_json
from packages.templates.registry import INDUSTRY_REGISTRY, TaxonomyNode

log = get_logger("architect.taxonomy_builder")


# ════════════════════════════════════════════════════════════════════════
#  propose_taxonomy
# ════════════════════════════════════════════════════════════════════════


async def propose_taxonomy(
    industry_code: str,
    sample_texts: list[str],
) -> list[TaxonomyNode]:
    """基于行业模板提议主树（M2 lite：只裁剪 L2，不重写）。

    Args:
        industry_code: industry_recognizer 识别的行业 code
        sample_texts: 客户上传材料样本

    Returns:
        修订后的主树（只动 L2）；行业不在 INDUSTRY_REGISTRY 时返回空列表
    """
    template = INDUSTRY_REGISTRY.get(industry_code)
    if template is None:
        log.warning("propose_taxonomy_industry_not_found", industry_code=industry_code)
        return []

    # 基础主树深拷贝（防 LLM 失败时污染原 template）
    base_taxonomy = [TaxonomyNode.model_validate(n.model_dump()) for n in template.taxonomy]

    if not sample_texts:
        log.info("propose_taxonomy_no_samples_keep_all", industry_code=industry_code)
        return base_taxonomy

    # 让 LLM 评估每个 L2 节点
    base_text = "\n".join(
        f"- {n.id} ({n.name}): {n.description[:60]}"
        for n in base_taxonomy
    )
    samples_text = "\n".join(f"- {s[:200]}" for s in sample_texts[:8])
    user_prompt = TAXONOMY_PROPOSE_USER.format(
        base_taxonomy=base_text,
        sample_texts=samples_text,
    )

    try:
        data = await acall_llm_json(TAXONOMY_PROPOSE_SYSTEM, user_prompt)
    except Exception as e:
        log.warning("propose_taxonomy_llm_failed_keep_all", error=str(e))
        return base_taxonomy

    decisions = data.get("decisions", [])
    if not isinstance(decisions, list):
        return base_taxonomy

    # 应用决策
    decision_map: dict[str, str] = {}
    for d in decisions:
        if not isinstance(d, dict):
            continue
        nid = d.get("node_id")
        action = d.get("action", "keep")
        if isinstance(nid, str) and action in ("keep", "drop", "highlight"):
            decision_map[nid] = action

    revised: list[TaxonomyNode] = []
    for node in base_taxonomy:
        action = decision_map.get(node.id, "keep")
        if action == "drop":
            log.info("propose_taxonomy_dropped", node_id=node.id, name=node.name)
            continue
        if action == "highlight":
            # 在 description 前加 [推荐] 标记
            node.description = f"[推荐] {node.description}"
        revised.append(node)

    # 兜底：如果 LLM 把全部 drop 了，退化保全
    if not revised:
        log.warning("propose_taxonomy_all_dropped_fallback_to_base")
        return base_taxonomy

    return revised


# ════════════════════════════════════════════════════════════════════════
#  apply_user_command
# ════════════════════════════════════════════════════════════════════════

# M2 lite 命令模式（中文自然语言关键词匹配；M3 接 LLM 解析）
_CMD_REMOVE = re.compile(r"(?:删除|去掉|移除)[\s\:：]*([^\s,，。；]+)")
_CMD_RENAME = re.compile(
    r"(?:把|将)?\s*([^\s,，。；]+)\s*(?:重命名为|改名为|改成|改为)\s*([^\s,，。；]+)"
)
_CMD_ADD = re.compile(r"(?:新增|添加|加入)[\s\:：]*([^\s,，。；]+)")


def apply_user_command(draft: TaxonomyDraft, command: str) -> TaxonomyDraft:
    """对主树草稿应用用户的自然语言命令（M2 lite：add/remove/rename L2）。

    支持的命令模式（中文）：
    - "删除 仓储管理"
    - "把仓储管理重命名为物流"
    - "新增 海外业务"

    无法解析的命令静默忽略（M3 接 LLM 解析处理）。
    """
    if draft is None or not command.strip():
        return draft

    taxonomy = list(draft.taxonomy or [])

    # rename
    m = _CMD_RENAME.search(command)
    if m:
        old_name = m.group(1).strip()
        new_name = m.group(2).strip()
        for node in taxonomy:
            n = node if isinstance(node, TaxonomyNode) else TaxonomyNode.model_validate(node)
            if n.name == old_name or n.id == old_name:
                n.name = new_name
                log.info("user_cmd_rename", old=old_name, new=new_name)
                break
        draft.taxonomy = [n if isinstance(n, TaxonomyNode) else TaxonomyNode.model_validate(n)
                          for n in taxonomy]
        return draft

    # remove
    m = _CMD_REMOVE.search(command)
    if m:
        target = m.group(1).strip()
        before = len(taxonomy)
        taxonomy = [
            n for n in taxonomy
            if (n.name if isinstance(n, TaxonomyNode) else n.get("name")) != target
            and (n.id if isinstance(n, TaxonomyNode) else n.get("id")) != target
        ]
        if len(taxonomy) < before:
            log.info("user_cmd_remove", target=target)
        draft.taxonomy = taxonomy
        return draft

    # add
    m = _CMD_ADD.search(command)
    if m:
        new_name = m.group(1).strip()
        new_id = re.sub(r"[^a-zA-Z0-9_]", "_", new_name.lower())[:32] or "custom"
        # 去重
        existing_names = [
            (n.name if isinstance(n, TaxonomyNode) else n.get("name"))
            for n in taxonomy
        ]
        if new_name not in existing_names:
            taxonomy.append(TaxonomyNode(
                id=new_id,
                name=new_name,
                level=2,
                description="（用户自定义节点）",
            ))
            log.info("user_cmd_add", name=new_name, id=new_id)
        draft.taxonomy = taxonomy
        return draft

    log.info("user_cmd_unrecognized", command=command[:60])
    return draft


# ════════════════════════════════════════════════════════════════════════
#  M3 #3c 主树高级 CRUD（PRD F1.3.4 节点合并 / 拆分 / 撤销）
# ════════════════════════════════════════════════════════════════════════

# 撤销栈：session_id → list[snapshot]，每个 snapshot = list[dict]（taxonomy dump）
# M3 lite 内存模式（M4 接 PG 持久化）
_undo_stack: dict[str, list[list[dict]]] = {}
_UNDO_LIMIT = 20  # 每会话最多保留 20 个快照


def _snapshot_taxonomy(taxonomy: list) -> list[dict]:
    """把 taxonomy 列表深拷贝为 dict 形式（撤销栈用）。"""
    out: list[dict] = []
    for n in taxonomy:
        if isinstance(n, TaxonomyNode):
            out.append(n.model_dump())
        elif isinstance(n, dict):
            out.append(dict(n))
    return out


def _restore_taxonomy(snapshot: list[dict]) -> list[TaxonomyNode]:
    return [TaxonomyNode.model_validate(d) for d in snapshot]


def push_undo_snapshot(session_id: str, draft: TaxonomyDraft) -> None:
    """在 mutation 操作前调一次，把当前 taxonomy 入撤销栈。"""
    if not session_id:
        return
    stack = _undo_stack.setdefault(session_id, [])
    stack.append(_snapshot_taxonomy(draft.taxonomy or []))
    if len(stack) > _UNDO_LIMIT:
        stack.pop(0)  # FIFO 截断


def undo(session_id: str, draft: TaxonomyDraft) -> tuple[TaxonomyDraft, bool]:
    """撤销最近一次操作。

    Returns:
        (draft, did_undo) — did_undo=False 表示栈空无可撤销
    """
    stack = _undo_stack.get(session_id, [])
    if not stack:
        return draft, False
    snapshot = stack.pop()
    draft.taxonomy = _restore_taxonomy(snapshot)
    log.info("taxonomy_undo", session_id=session_id, remaining=len(stack))
    return draft, True


def reset_undo_for_test() -> None:
    _undo_stack.clear()


# ── merge ──


def merge_nodes(
    draft: TaxonomyDraft,
    *,
    source_ids: list[str],
    target_name: str,
    target_id: str = "",
    description: str = "",
) -> TaxonomyDraft:
    """合并多个节点为一个新节点（PRD F1.3.4）。

    Args:
        source_ids: 待合并的节点 id 列表（≥2）
        target_name: 合并后的新节点名
        target_id: 新节点 id（默认从 target_name 推导）
        description: 新节点描述（默认拼接源节点 name）

    Returns:
        修改后的 draft；source_ids 节点都不存在时静默不动
    """
    if not draft or len(source_ids) < 2:
        return draft

    src_set = set(source_ids)
    taxonomy: list[TaxonomyNode] = []
    matched: list[TaxonomyNode] = []

    for n in draft.taxonomy or []:
        node = n if isinstance(n, TaxonomyNode) else TaxonomyNode.model_validate(n)
        if node.id in src_set:
            matched.append(node)
        else:
            taxonomy.append(node)

    if len(matched) < 2:
        log.info("merge_skipped_too_few_matches",
                 source_ids=source_ids, matched=len(matched))
        return draft

    if not target_id:
        target_id = re.sub(r"[^a-zA-Z0-9_]", "_", target_name.lower())[:32] or "merged"

    desc = description or f"合并自 {' / '.join(m.name for m in matched)}"
    # 子节点合并去重（按 id）
    children: list[TaxonomyNode] = []
    seen_child_ids: set[str] = set()
    for m in matched:
        for c in m.children or []:
            cn = c if isinstance(c, TaxonomyNode) else TaxonomyNode.model_validate(c)
            if cn.id not in seen_child_ids:
                seen_child_ids.add(cn.id)
                children.append(cn)

    taxonomy.append(TaxonomyNode(
        id=target_id,
        name=target_name,
        level=matched[0].level,
        description=desc,
        children=children,
    ))
    draft.taxonomy = taxonomy
    log.info("merge_done", source_ids=source_ids, target_id=target_id,
             merged_count=len(matched))
    return draft


# ── split ──


def split_node(
    draft: TaxonomyDraft,
    *,
    source_id: str,
    new_nodes: list[dict],
) -> TaxonomyDraft:
    """把一个节点拆分为多个新节点（PRD F1.3.4）。

    Args:
        source_id: 待拆分的节点 id
        new_nodes: 新节点定义 [{"id": ..., "name": ..., "description": ...}, ...]

    Returns:
        修改后的 draft；source 不存在或 new_nodes 为空时不动
    """
    if not draft or not new_nodes or not source_id:
        return draft

    taxonomy: list[TaxonomyNode] = []
    matched: TaxonomyNode | None = None

    for n in draft.taxonomy or []:
        node = n if isinstance(n, TaxonomyNode) else TaxonomyNode.model_validate(n)
        if node.id == source_id:
            matched = node
        else:
            taxonomy.append(node)

    if matched is None:
        log.info("split_source_not_found", source_id=source_id)
        return draft

    # 创建新节点（保留原 level）
    for nd in new_nodes:
        if not isinstance(nd, dict):
            continue
        new_id = nd.get("id") or re.sub(
            r"[^a-zA-Z0-9_]", "_",
            (nd.get("name") or "").lower(),
        )[:32]
        if not new_id:
            continue
        taxonomy.append(TaxonomyNode(
            id=str(new_id)[:64],
            name=str(nd.get("name", new_id))[:60],
            level=matched.level,
            description=str(nd.get("description", f"由 {matched.name} 拆分而来"))[:200],
            children=[],
        ))

    draft.taxonomy = taxonomy
    log.info("split_done", source_id=source_id, new_count=len(new_nodes))
    return draft
