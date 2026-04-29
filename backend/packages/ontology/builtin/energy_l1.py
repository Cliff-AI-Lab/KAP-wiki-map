"""能源行业 L1 基础本体（决策书 §5.3 IEC CIM + KKS 编码体系简化版）。

来源：决策书 §5.3
> 能源 IEC CIM 公共信息模型 + KKS 编码体系
"""

from __future__ import annotations

from datetime import datetime

from packages.common.types import (
    OntologyEntityType,
    OntologyRelationType,
    OntologyVersion,
)

# ════════════════════════════════════════════════════════════════════════
#  实体类型（10 类，IEC CIM 简化）
# ════════════════════════════════════════════════════════════════════════

_ENTITY_TYPES: list[OntologyEntityType] = [
    OntologyEntityType(
        type_id="power_plant", type_name="电厂", layer="L1",
        description="发电厂（火电/水电/核电/风电/光伏）",
        required_properties=["plant_code"],
        examples=["华能 #1 电厂", "光伏一号", "海上风电场"],
    ),
    OntologyEntityType(
        type_id="generator", type_name="发电机", layer="L1",
        description="发电主设备（汽轮发电机/水轮发电机/风电机组）",
        required_properties=["kks_code"],
        examples=["#1 发电机", "汽轮发电机 G1"],
    ),
    OntologyEntityType(
        type_id="boiler", type_name="锅炉", layer="L1",
        description="蒸汽发生设备（火电场景）",
        required_properties=["kks_code"],
        examples=["#1 锅炉", "余热锅炉"],
    ),
    OntologyEntityType(
        type_id="turbine", type_name="汽轮机", layer="L1",
        description="蒸汽驱动旋转机械",
        required_properties=["kks_code"],
        examples=["#1 汽轮机", "高压缸", "低压缸"],
    ),
    OntologyEntityType(
        type_id="breaker", type_name="断路器", layer="L1",
        description="电力开关设备",
        required_properties=["kks_code"],
        examples=["220kV 断路器", "GIS 开关"],
    ),
    OntologyEntityType(
        type_id="line", type_name="线路", layer="L1",
        description="输配电线路",
        examples=["110kV 主送电线", "10kV 配电线"],
    ),
    OntologyEntityType(
        type_id="substation", type_name="变电站", layer="L1",
        description="变压、换相、汇流的电力枢纽",
        examples=["220kV 变电站", "110kV 变电站"],
    ),
    OntologyEntityType(
        type_id="hazard", type_name="隐患", layer="L1",
        description="安全风险点 / 潜在事故源",
        examples=["热水管泄漏", "母线接地", "可燃气体泄漏"],
    ),
    OntologyEntityType(
        type_id="standard", type_name="标准", layer="L1",
        description="电力行业标准（DL/T 系列、GB 系列、IEC 系列）",
        required_properties=["standard_code", "version"],
        examples=["DL/T 596-2021", "GB 26860-2011", "IEC 61850"],
    ),
    OntologyEntityType(
        type_id="role", type_name="角色", layer="L1",
        description="电力运行/检修岗位",
        examples=["调度员", "值长", "检修工程师", "热工班长"],
    ),
]


# ════════════════════════════════════════════════════════════════════════
#  关系类型（6 个核心关系）
# ════════════════════════════════════════════════════════════════════════

_RELATION_TYPES: list[OntologyRelationType] = [
    OntologyRelationType(
        type_id="connects_to", type_name="连接", layer="L1",
        description="设备/线路之间的拓扑连接",
        source_types=["generator", "breaker", "line", "substation", "turbine"],
        target_types=["generator", "breaker", "line", "substation", "boiler"],
        examples=["发电机 连接 升压变压器", "线路 连接 变电站"],
    ),
    OntologyRelationType(
        type_id="supplies", type_name="供应", layer="L1",
        description="电源 → 用户的供电关系",
        source_types=["power_plant", "substation"],
        target_types=["substation", "line"],
        examples=["#1 电厂 供应 220kV 变电站"],
    ),
    OntologyRelationType(
        type_id="monitors", type_name="监测", layer="L1",
        description="角色/系统监测设备状态",
        source_types=["role"],
        target_types=["generator", "boiler", "turbine", "breaker"],
        examples=["调度员 监测 发电机负荷"],
    ),
    OntologyRelationType(
        type_id="regulated_by", type_name="规范于", layer="L1",
        description="设备/工艺受标准约束",
        source_types=["generator", "boiler", "turbine", "breaker", "line", "substation"],
        target_types=["standard"],
        examples=["#1 锅炉 规范于 GB 26860"],
    ),
    OntologyRelationType(
        type_id="detected_at", type_name="发现于", layer="L1",
        description="隐患在设备/区域被发现",
        source_types=["hazard"],
        target_types=["generator", "boiler", "turbine", "substation", "line"],
        examples=["可燃气体泄漏 发现于 锅炉房"],
    ),
    OntologyRelationType(
        type_id="responds_to", type_name="处置", layer="L1",
        description="角色处置隐患/故障",
        source_types=["role"],
        target_types=["hazard"],
        examples=["检修工程师 处置 母线接地"],
    ),
]


# ════════════════════════════════════════════════════════════════════════
#  L1 v1.0.0 快照
# ════════════════════════════════════════════════════════════════════════

ENERGY_L1_V1 = OntologyVersion(
    version="ont-v1.0.0",
    layer="L1",
    industry_code="energy",
    project_id="",
    entity_types=_ENTITY_TYPES,
    relation_types=_RELATION_TYPES,
    created_at=datetime(2026, 4, 29),
    created_by="system",
    notes="能源 L1 基础本体（IEC CIM + KKS 简化版，10 实体类型 + 6 关系类型）",
)
