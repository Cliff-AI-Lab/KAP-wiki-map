"""M3 #4 W4 实体抽取（决策书 §5.2 W4 工位）。

KAP 当前蒸馏管线 Librarian 阶段顺带提取了 mentioned_entities，但没有：
- 类型严格约束（不挂 OntologyEntityType.type_id）
- 关系抽取
- 敏感实体标记
- 置信度

本模块补一个**专用 W4 entity_extractor**：
- 输入：文档原文 + 当前生效 L1+L2 本体
- 输出：ExtractionResult（含实体 + 关系 + 敏感标记 + 置信度）
- LLM-driven，prompt 强制 type_id 在本体注册集合内
- W4 后置：批 1 已有 governance W4 hook，本批不重复接入
"""

from packages.extraction.entity_extractor import (
    extract_entities_and_relations,
)

__all__ = [
    "extract_entities_and_relations",
]
