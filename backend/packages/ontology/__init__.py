"""M3 #1 双层本体演化（决策书 §5.3 D8/D9）。

L1 行业基础本体（平台预置稳定）+ L2 企业扩展本体（客户私有 LLM 提议 SME 审批）。

模块组成（M3 lite 范围）：
- ``base``                — OntologyRegistry + 注册函数
- ``store``               — OntologyStore 持久化 + 版本管理（批 2）
- ``evolution_proposer``  — LLM 演化提议器（批 3）
- ``builtin/``            — L1 内置本体（manufacturing / energy）

M4 后续：
- 全量重抽影子库
- 增量哈希
- as_of 历史回溯
- 灰度切换 + 7 天回滚
- 监测条件 2/3/4（自定义关系固化 / 语义漂移 / 标准升版）
"""

from packages.ontology.base import (
    OntologyRegistry,
    get_current_l1,
    get_current_l2,
    get_registry,
    register_l1,
    register_l2,
    reset_registry_for_test,
)
from packages.ontology.store import (
    OntologyStore,
    get_ontology_store,
    reset_store_for_test,
)

__all__ = [
    "OntologyRegistry",
    "OntologyStore",
    "get_current_l1",
    "get_current_l2",
    "get_ontology_store",
    "get_registry",
    "register_l1",
    "register_l2",
    "reset_registry_for_test",
    "reset_store_for_test",
]
