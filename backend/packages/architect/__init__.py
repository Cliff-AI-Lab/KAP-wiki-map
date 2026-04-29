"""M2 #4 块① 知识咨询智能体（决策书 §4 / PRD §3）。

对话式 AI 顾问，引导客户从无到有建立 4 级知识体系（主树 + Facet）。

模块组成（M2 lite 范围 — 增量交付）：
- 批 1 ``agent``                — ArchitectAgent 状态机骨架
- 批 2 ``industry_recognizer``  — 行业识别（关键词 + LLM 两阶段）
- 批 3 ``taxonomy_builder`` / ``exporter`` — 主树提议 + 导出
- 批 4 API endpoints
"""

from packages.architect.agent import ArchitectAgent, get_architect_agent
from packages.architect.conflict_detector import (
    DocSample,
    PreviewReport,
    classify_doc,
    detect_duplicates,
    preview_classification,
)
from packages.architect.exporter import (
    export_to_industry_template,
    to_json,
    to_yaml,
    write_to_file,
)
from packages.architect.facet_advisor import (
    propose_facets_for_doc_type,
    propose_facets_for_taxonomy,
)
from packages.architect.naming_convention import (
    apply_user_changes as apply_naming_changes,
    default_naming_convention,
    preview_filename,
    validate_filename,
)
from packages.architect.industry_recognizer import (
    IndustryRecognitionResult,
    recognize_industry,
)
from packages.architect.taxonomy_builder import (
    apply_user_command,
    merge_nodes,
    propose_taxonomy,
    push_undo_snapshot,
    reset_undo_for_test,
    split_node,
    undo,
)

__all__ = [
    "ArchitectAgent",
    "DocSample",
    "IndustryRecognitionResult",
    "PreviewReport",
    "apply_naming_changes",
    "apply_user_command",
    "classify_doc",
    "default_naming_convention",
    "detect_duplicates",
    "export_to_industry_template",
    "get_architect_agent",
    "merge_nodes",
    "preview_classification",
    "preview_filename",
    "propose_facets_for_doc_type",
    "propose_facets_for_taxonomy",
    "propose_taxonomy",
    "push_undo_snapshot",
    "recognize_industry",
    "reset_undo_for_test",
    "split_node",
    "to_json",
    "to_yaml",
    "undo",
    "validate_filename",
    "write_to_file",
]
