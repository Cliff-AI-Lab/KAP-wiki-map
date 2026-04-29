"""M1 敏感实体识别 + 脱敏管线（决策书 §5.4 D10 / D11）。

三类敏感数据各自方案（决策书 §5.4 表）：

| 类别       | 识别                | 脱敏策略                       |
|:-----------|:--------------------|:-------------------------------|
| 人名       | 正则 + 角色字典      | 角色化替换 "张工" → "研发员A"   |
| 工艺参数   | 数字+单位正则        | 三级降精度（精确 / 区间 / 等级）|
| 客户名     | 实体白名单匹配       | 代码化 "客户A001"               |

模块组成（M1 lite — 离线工具集）：
- ``ner``: 函数式 NER 检测三类敏感实体
- ``redactor``: 三策略脱敏函数 + 完整文档脱敏 pipeline
- ``mapping_store``: Redis + AES-256-GCM 加密 KV（dev 内存 fallback）

W1/W4/W5 hook 集成 + 双向量 vec_redacted/vec_original 路由 → M2 批
"""

from packages.sensitive.mapping_store import (
    MappingStoreError,
    SensitiveMappingStore,
    get_mapping_store,
)
from packages.sensitive.ner import (
    SensitiveCategory,
    SensitiveSpan,
    detect_sensitive_spans,
)
from packages.sensitive.redactor import (
    PrecisionLevel,
    RedactResult,
    redact_document,
)

__all__ = [
    "MappingStoreError",
    "PrecisionLevel",
    "RedactResult",
    "SensitiveCategory",
    "SensitiveMappingStore",
    "SensitiveSpan",
    "detect_sensitive_spans",
    "get_mapping_store",
    "redact_document",
]
