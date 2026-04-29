"""制造业 L1 基础本体（决策书 §5.3 锁定 9 类核心概念）。

来源：决策书 §5.3
> 制造业基础概念（产品/工艺/物料/设备/工序/缺陷/标准/人员/组织）
"""

from __future__ import annotations

from datetime import datetime

from packages.common.types import (
    OntologyEntityType,
    OntologyRelationType,
    OntologyVersion,
)

# ════════════════════════════════════════════════════════════════════════
#  实体类型（9 类）
# ════════════════════════════════════════════════════════════════════════

_ENTITY_TYPES: list[OntologyEntityType] = [
    OntologyEntityType(
        type_id="product", type_name="产品", layer="L1",
        description="制造的最终成品、半成品、零部件",
        required_properties=["product_code", "version"],
        examples=["A 型电机", "齿轮箱 GB-100", "轴承 6204"],
    ),
    OntologyEntityType(
        type_id="process", type_name="工艺", layer="L1",
        description="将物料转化为产品的步骤集合",
        required_properties=["process_code"],
        examples=["车削工艺", "热处理", "表面喷涂"],
    ),
    OntologyEntityType(
        type_id="material", type_name="物料", layer="L1",
        description="原材料、辅料、外购件",
        required_properties=["material_code"],
        examples=["45# 钢", "环氧树脂", "电池正极材料"],
    ),
    OntologyEntityType(
        type_id="equipment", type_name="设备", layer="L1",
        description="生产线上的机器、装备、仪器",
        required_properties=["equipment_code"],
        examples=["数控车床 CK6140", "注塑机 JP200", "检测设备 CMM"],
    ),
    OntologyEntityType(
        type_id="operation", type_name="工序", layer="L1",
        description="工艺中的单一作业步骤",
        examples=["粗车", "精磨", "装配", "包装"],
    ),
    OntologyEntityType(
        type_id="defect", type_name="缺陷", layer="L1",
        description="质量异常 / 不合格品类型",
        examples=["划伤", "气孔", "尺寸超差", "毛刺"],
    ),
    OntologyEntityType(
        type_id="standard", type_name="标准", layer="L1",
        description="国家/行业/企业标准、规程、规范",
        required_properties=["standard_code", "version"],
        examples=["GB/T 6075-2012", "ISO 9001", "JB/T 6932"],
    ),
    OntologyEntityType(
        type_id="personnel", type_name="人员", layer="L1",
        description="工人、工程师、管理者等岗位角色",
        examples=["操作工", "工艺工程师", "质检员", "车间主任"],
    ),
    OntologyEntityType(
        type_id="organization", type_name="组织", layer="L1",
        description="部门、车间、班组、公司",
        examples=["生产部", "总装车间", "质量管理部", "研发中心"],
    ),
]


# ════════════════════════════════════════════════════════════════════════
#  关系类型（8 个核心关系，决策书 §5.3 + §5.6 关系类型示例）
# ════════════════════════════════════════════════════════════════════════

_RELATION_TYPES: list[OntologyRelationType] = [
    OntologyRelationType(
        type_id="includes", type_name="包含", layer="L1",
        description="组合/包含关系（系统包含部件）",
        source_types=["product", "equipment", "process"],
        target_types=["product", "material", "operation"],
        examples=["齿轮箱 包含 轴承", "总装工艺 包含 装配工序"],
    ),
    OntologyRelationType(
        type_id="produces", type_name="产出", layer="L1",
        description="工艺产出产品",
        source_types=["process", "operation", "equipment"],
        target_types=["product"],
        examples=["车削工艺 产出 轴", "数控机床 产出 零件"],
    ),
    OntologyRelationType(
        type_id="uses", type_name="使用", layer="L1",
        description="工艺/工序使用设备/物料",
        source_types=["process", "operation"],
        target_types=["equipment", "material"],
        examples=["热处理 使用 加热炉", "装配工序 使用 螺栓"],
    ),
    OntologyRelationType(
        type_id="detected_in", type_name="发现于", layer="L1",
        description="缺陷在工序/产品中被发现",
        source_types=["defect"],
        target_types=["product", "operation"],
        examples=["划伤 发现于 总装工序", "气孔 发现于 铸件"],
    ),
    OntologyRelationType(
        type_id="executed_by", type_name="执行人", layer="L1",
        description="工序由人员执行",
        source_types=["operation", "process"],
        target_types=["personnel"],
        examples=["精磨 执行人 高级技工", "工艺审核 执行人 工艺工程师"],
    ),
    OntologyRelationType(
        type_id="governs", type_name="规范", layer="L1",
        description="标准规范工艺/产品/设备",
        source_types=["standard"],
        target_types=["process", "product", "equipment", "operation"],
        examples=["GB/T 6075 规范 振动检测", "ISO 9001 规范 质量管理"],
    ),
    OntologyRelationType(
        type_id="belongs_to", type_name="归属", layer="L1",
        description="人员/设备归属组织",
        source_types=["personnel", "equipment"],
        target_types=["organization"],
        examples=["操作工 归属 总装车间", "数控机床 归属 加工车间"],
    ),
    OntologyRelationType(
        type_id="referenced_by", type_name="引用", layer="L1",
        description="文档引用标准（决策书 §5.6『证据于』派生）",
        source_types=["standard", "process", "product"],
        target_types=["standard"],
        examples=["A 工艺 引用 GB/T 6075", "ISO 9001 引用 ISO 9000"],
    ),
]


# ════════════════════════════════════════════════════════════════════════
#  L1 v1.0.0 快照
# ════════════════════════════════════════════════════════════════════════

MANUFACTURING_L1_V1 = OntologyVersion(
    version="ont-v1.0.0",
    layer="L1",
    industry_code="manufacturing",
    project_id="",
    entity_types=_ENTITY_TYPES,
    relation_types=_RELATION_TYPES,
    created_at=datetime(2026, 4, 29),
    created_by="system",
    notes="制造业 L1 基础本体（决策书 §5.3 锁定 9 实体类型 + 8 关系类型）",
)
