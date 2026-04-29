"""M2 #4 块① 知识咨询智能体（决策书 §4 / PRD §3）。

对话式 AI 顾问，引导客户从无到有建立 4 级知识体系（主树 + Facet）。

模块组成（M2 lite 范围 — 增量交付）：
- 批 1 ``agent``                — ArchitectAgent 状态机骨架
- 批 2 ``industry_recognizer``  — 行业识别（关键词 + LLM 两阶段）
- 批 3 ``taxonomy_builder`` / ``exporter`` — 主树提议 + 导出
- 批 4 API endpoints
"""

from packages.architect.agent import ArchitectAgent, get_architect_agent
from packages.architect.industry_recognizer import (
    IndustryRecognitionResult,
    recognize_industry,
)

__all__ = [
    "ArchitectAgent",
    "IndustryRecognitionResult",
    "get_architect_agent",
    "recognize_industry",
]
