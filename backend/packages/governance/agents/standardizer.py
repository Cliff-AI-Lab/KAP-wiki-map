"""Standardizer Agent — 实体归一化（借鉴 ai-knowledge-graph Entity Standardization）.

扫 GraphStore 实体名, LLM 识别 "同一概念的多个别名" (如 '李总'='李先生'='李四'),
对每组 variants ≥ 2 的产 standardize_suggest 工单.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from packages.common import get_logger
from packages.common.types import GovernanceQueueItem
from packages.distillation.llm_client import call_llm_json
from packages.governance.agents.base import BaseGovernanceAgent, AgentRunResult
from packages.storage.governance_queue_store import GovernanceQueueStore

log = get_logger("governance.standardizer")


STANDARDIZE_SYSTEM = """你是实体归一化专家 (Entity Resolution)。
给你一个项目的实体名列表，请识别指向同一概念的实体群。

示例:
- "李总" / "李先生" / "李四"  → 同一人
- "AI" / "人工智能" / "Artificial Intelligence" → 同一概念
- "安全生产部" / "安全部门" / "安环部" → 可能同一部门

硬约束:
- 只返回 JSON, 不要额外文字
- Schema:
  {
    "standardized": {
      "标准名1": ["别名A", "别名B", "别名C"],
      "标准名2": ["别名D", "别名E"],
      ...
    }
  }
- 标准名选最完整/最正式的那个 (优先含完整机构名/全称)
- 只返回有 ≥2 个别名的群 (单独实体不用返回)
- 不确定的实体不要强行归一 (宁缺毋滥)
"""

STANDARDIZE_USER_TEMPLATE = """下面是项目的实体名列表 (共 {count} 个):
{entities}

请识别同一概念的实体群并返回 JSON。"""

# 单批最多送多少实体进 LLM（避免超长）
BATCH_SIZE = 40


class StandardizerAgent(BaseGovernanceAgent):
    name = "standardizer"

    async def run(
        self,
        project_id: str,
        queue_store: GovernanceQueueStore,
        graph_store: Any = None,
        **_: Any,
    ) -> AgentRunResult:
        result = AgentRunResult(agent=self.name, ok=True)

        if graph_store is None:
            result.ok = False
            result.errors.append("缺少 graph_store 依赖")
            return result

        # 从 _nodes 拿实体名（memory mode 内部 dict）
        try:
            nodes_dict = getattr(graph_store, "_nodes", {}) or {}
            entity_names = [
                name for name, info in nodes_dict.items()
                if isinstance(info, dict)
                and (not project_id or info.get("domain_id", "").startswith(f"{project_id}/") or True)
                # TODO: project_id 隔离: 当前 GraphStore memory 模式不存 project_id, 暂跨项目归一
            ]
        except Exception as e:
            result.ok = False
            result.errors.append(f"读 graph_store._nodes 失败: {e}")
            return result

        result.scanned = len(entity_names)
        if result.scanned < 3:
            result.detail["note"] = "实体数 < 3, 无需归一化"
            return result

        # 分批送 LLM
        for batch_start in range(0, len(entity_names), BATCH_SIZE):
            batch = entity_names[batch_start:batch_start + BATCH_SIZE]
            entities_text = "\n".join(f"  - {e}" for e in batch)
            try:
                judgment = call_llm_json(
                    system_prompt=STANDARDIZE_SYSTEM,
                    user_prompt=STANDARDIZE_USER_TEMPLATE.format(
                        count=len(batch),
                        entities=entities_text,
                    ),
                    temperature=0.0,
                    max_tokens=1024,
                )
            except Exception as e:
                log.warning("standardizer_llm_batch_failed",
                            batch_start=batch_start, error=str(e))
                result.errors.append(f"batch {batch_start}: {e}")
                continue

            standardized = judgment.get("standardized") or {}
            if not isinstance(standardized, dict):
                continue

            for std_name, variants in standardized.items():
                if not isinstance(variants, list) or len(variants) < 2:
                    continue
                # 产一条 standardize_suggest 工单
                std_name_s = str(std_name)[:80]
                variants_s = [str(v) for v in variants[:8]]
                await self._push(queue_store, GovernanceQueueItem(
                    id=f"gq_{uuid.uuid4().hex[:10]}",
                    project_id=project_id,
                    agent="standardizer",
                    kind="standardize_suggest",
                    title=f"[归一化] {std_name_s} 疑似有 {len(variants_s)} 别名",
                    description=f"建议合并为 '{std_name_s}': " + ", ".join(variants_s[:5]),
                    target_ref=f"entities/{std_name_s}",
                    priority=60,
                    status="pending",
                    created_at=datetime.now(timezone.utc),
                ))
                result.produced += 1

        result.detail["batches"] = (len(entity_names) + BATCH_SIZE - 1) // BATCH_SIZE
        log.info("standardizer_run_done", project=project_id,
                 scanned=result.scanned, produced=result.produced,
                 errors=len(result.errors))
        return result
