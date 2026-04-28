"""LLM 知识路由器 — Skills 模式的核心：LLM 读目录树后定位知识域和具体文档。

本模块是书虫智能体检索链路中的关键环节，负责将用户查询精准路由到
相关知识域和文档，从而缩小后续向量检索的范围，提升检索精度。

工作流程：
1. DomainStore 生成完整目录树文本（含每篇文档的描述）
2. LLM 读目录树 + 用户问题
3. LLM 推理选择：最相关的知识域 + 最相关的具体文档
4. 后续检索仅在命中的文档/域内进行

依赖：
- packages.distillation.llm_client: 提供 LLM JSON 格式调用能力
- packages.common.logger: 结构化日志
"""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.common import get_logger
from packages.distillation.llm_client import call_llm_json

log = get_logger("retrieval.router")


@dataclass
class RouteResult:
    """LLM 路由结果数据类。

    Attributes:
        selected_domains: LLM 选出的最相关知识域 ID 列表（最多3个）
        selected_doc_ids: LLM 选出的最相关文档 ID 列表（最多5个）
        reasoning: LLM 给出的选择理由说明
    """
    selected_domains: list[str] = field(default_factory=list)
    selected_doc_ids: list[str] = field(default_factory=list)
    reasoning: str = ""


# ── LLM 提示词模板 ──────────────────────────────────────────────

# 系统提示词：指导 LLM 作为路由专家，从目录树中选择最相关的知识域和文档
ROUTER_SYSTEM = """你是企业知识库的路由专家。你的任务是根据用户的问题，从知识目录中选择最相关的知识域和具体文档。

规则：
1. 仔细阅读目录树中每个分类的描述和文档描述
2. 如果能定位到具体文档（目录中列出了 [doc_id]），优先选择具体文档
3. 如果无法确定具体文档，选择最相关的知识域（1~3个）
4. 优先选择更精确的子分类，而非宽泛的父分类
5. selected_doc_ids 中填写目录中 [方括号] 内的文档ID

请严格按照 JSON 格式输出。"""

# 用户提示词模板：将目录树和用户问题填入，引导 LLM 输出结构化 JSON
ROUTER_USER = """{catalog}

## 用户问题
{query}

## 请选择最相关的知识域和文档，以 JSON 格式输出：
{{
  "selected_domains": ["最相关的知识域domain_id"],
  "selected_doc_ids": ["如果能定位到具体文档，填写doc_id"],
  "reasoning": "选择理由（一句话）"
}}"""


async def route_query(query: str, domain_catalog_text: str) -> RouteResult:
    """调用 LLM 读取知识目录树，为用户查询选择最相关的知识域和文档。

    这是检索链路的第一步：通过 LLM 理解用户意图并在目录树中定位，
    将后续向量检索的范围从全库缩小到特定域/文档。

    Args:
        query: 用户的原始查询文本
        domain_catalog_text: DomainStore 生成的完整目录树文本，
            包含各知识域描述及其下文档列表

    Returns:
        RouteResult: 路由结果，包含选中的知识域ID列表、文档ID列表及推理说明。
            若 LLM 调用失败则返回空的 RouteResult（全量检索兜底）。
    """
    # 将目录树和用户问题组装为用户提示词
    user_prompt = ROUTER_USER.format(catalog=domain_catalog_text, query=query)

    try:
        # 调用 LLM 获取 JSON 格式的路由决策
        data = call_llm_json(ROUTER_SYSTEM, user_prompt)

        # 解析 LLM 返回结果，过滤无效值并限制数量上限
        result = RouteResult(
            selected_domains=[d for d in data.get("selected_domains", []) if isinstance(d, str) and d.strip()][:3],
            selected_doc_ids=[d for d in data.get("selected_doc_ids", []) if isinstance(d, str) and d.strip()][:5],
            reasoning=data.get("reasoning", ""),
        )

        log.info(
            "llm_router_done",
            query=query[:80],
            selected_domains=result.selected_domains,
            selected_doc_ids=result.selected_doc_ids,
            reasoning=result.reasoning[:100],
        )
        return result

    except Exception as e:
        # LLM 调用失败时降级：返回空结果，后续检索将走全量兜底逻辑
        log.warning("llm_router_failed", error=str(e), query=query[:80])
        return RouteResult()
