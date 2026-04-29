"""制造行业 4 套 Facet schema（PRD §10.4 1129 行 / 决策书 §7）。

| 文档类型           | code                | 主审 | 用途                              |
|:-------------------|:--------------------|:----:|:----------------------------------|
| 设备故障           | equipment_fault     | SME  | 故障案例库，喂给 LLM 做 RCA 推荐   |
| 工艺标准           | process_standard    | SME  | 工艺参数 + 标准引用                |
| SOP 标准操作程序   | sop                 | SME  | 步骤化操作指南                     |
| 质量记录           | quality_record      | DG   | 批次检验数据，质量回溯             |

设计原则（feedback memory · 轻量化）：
- 每套 facet 字段数控制在 6-10 个，避免大而全
- 敏感字段标记 sensitive=True，触发 packages/sensitive 脱敏管线
- 引用类型字段保持 reference + ref_type，M3 双层本体演化批接图谱
"""

from __future__ import annotations

from packages.templates.registry import FacetField, FacetSchema


# ════════════════════════════════════════════════════════════════════════
#  设备故障（equipment_fault）
# ════════════════════════════════════════════════════════════════════════

EQUIPMENT_FAULT_SCHEMA = FacetSchema(
    doc_type="equipment_fault",
    name="设备故障",
    description="设备故障案例：现象 + 原因 + 处置 + 知识沉淀",
    primary_role="SME",
    fields=[
        FacetField(
            key="equipment_name", name="设备名称", type="str", required=True,
            description="发生故障的设备名称（如 '汽轮机1号'）",
        ),
        FacetField(
            key="equipment_code", name="设备编码", type="str", required=False,
            description="设备的 KKS / 资产编号",
        ),
        FacetField(
            key="fault_code", name="故障代码", type="str", required=False,
            description="厂家故障代码或公司分类编号",
        ),
        FacetField(
            key="fault_phenomenon", name="故障现象", type="str", required=True,
            description="可观测的异常现象描述",
        ),
        FacetField(
            key="root_cause", name="根本原因", type="str", required=False,
            description="RCA 分析得出的根本原因",
        ),
        FacetField(
            key="resolution", name="处置措施", type="str", required=True,
            description="实际采取的处置或维修动作",
        ),
        FacetField(
            key="occurred_at", name="发生时间", type="date", required=True,
        ),
        FacetField(
            key="repaired_by", name="维修人", type="str", required=False, sensitive=True,
            description="维修执行人（人名敏感，脱敏管线角色化替换）",
        ),
        FacetField(
            key="downtime_minutes", name="停机时长", type="numeric", unit="min",
            required=False, sensitive=True,
            description="故障导致的停机分钟数（敏感：影响产能可见性）",
        ),
    ],
)


# ════════════════════════════════════════════════════════════════════════
#  工艺标准（process_standard）
# ════════════════════════════════════════════════════════════════════════

PROCESS_STANDARD_SCHEMA = FacetSchema(
    doc_type="process_standard",
    name="工艺标准",
    description="工艺规程 / 操作标准：参数范围 + 标准引用",
    primary_role="SME",
    fields=[
        FacetField(
            key="standard_no", name="标准编号", type="str", required=True,
            description="内部标准编号（如 'PS-2024-001'）",
        ),
        FacetField(
            key="version", name="版本号", type="str", required=True,
            description="版本号（如 'v2.1'）",
        ),
        FacetField(
            key="applicable_product", name="适用产品", type="str", required=True,
            description="该工艺标准适用的产品 / 工序",
        ),
        FacetField(
            key="key_param_temp", name="关键温度", type="numeric", unit="℃",
            required=False, sensitive=True,
            description="关键工艺温度（敏感：泄露给竞品有商业风险）",
        ),
        FacetField(
            key="key_param_pressure", name="关键压力", type="numeric", unit="MPa",
            required=False, sensitive=True,
        ),
        FacetField(
            key="reference_standards", name="引用标准", type="str", required=False,
            description="国家/行业标准引用列表（如 'GB/T 6075-2012'）",
        ),
        FacetField(
            key="effective_date", name="生效日期", type="date", required=True,
        ),
        FacetField(
            key="owner_department", name="主管部门", type="reference", ref_type="Department",
            required=True,
            description="标准的主责部门",
        ),
    ],
)


# ════════════════════════════════════════════════════════════════════════
#  SOP 标准操作程序（sop）
# ════════════════════════════════════════════════════════════════════════

SOP_SCHEMA = FacetSchema(
    doc_type="sop",
    name="标准操作程序 (SOP)",
    description="岗位作业指导书 / 操作步骤",
    primary_role="SME",
    fields=[
        FacetField(
            key="sop_no", name="SOP 编号", type="str", required=True,
        ),
        FacetField(
            key="version", name="版本", type="str", required=True,
        ),
        FacetField(
            key="applicable_position", name="适用岗位", type="str", required=True,
            description="适用岗位（如 '机加工操作工'）",
        ),
        FacetField(
            key="step_count", name="步骤数", type="int", required=False,
        ),
        FacetField(
            key="critical_control_points", name="关键控制点", type="str", required=False,
            description="必须严格执行的关键步骤说明",
        ),
        FacetField(
            key="ppe_required", name="必备劳保", type="enum", required=False,
            enum_values=["安全帽", "护目镜", "防护手套", "防护鞋", "防护服", "其他"],
        ),
        FacetField(
            key="author", name="编写人", type="str", required=False, sensitive=True,
            description="SOP 编写人（敏感：人名脱敏）",
        ),
        FacetField(
            key="approver", name="审核人", type="str", required=True, sensitive=True,
        ),
        FacetField(
            key="effective_date", name="生效日期", type="date", required=True,
        ),
    ],
)


# ════════════════════════════════════════════════════════════════════════
#  质量记录（quality_record）— 主审 DG（决策书 §5.2 W3 切块/W5 入库 DG 主审）
# ════════════════════════════════════════════════════════════════════════

QUALITY_RECORD_SCHEMA = FacetSchema(
    doc_type="quality_record",
    name="质量记录",
    description="批次检验记录 / 检测报告",
    primary_role="DG",
    fields=[
        FacetField(
            key="batch_no", name="批次号", type="str", required=True,
        ),
        FacetField(
            key="product_code", name="产品编码", type="str", required=True,
        ),
        FacetField(
            key="inspection_item", name="检验项目", type="str", required=True,
        ),
        FacetField(
            key="standard_value", name="标准值", type="str", required=False,
            description="规格/标准值（含上下限或目标值）",
        ),
        FacetField(
            key="actual_value", name="实测值", type="str", required=True, sensitive=True,
            description="实际检测值（敏感：泄露给竞品有商业风险）",
        ),
        FacetField(
            key="judgment", name="判定结果", type="enum", required=True,
            enum_values=["合格", "不合格", "让步接收", "返工", "报废"],
        ),
        FacetField(
            key="inspector", name="检验员", type="str", required=False, sensitive=True,
        ),
        FacetField(
            key="inspected_at", name="检验日期", type="date", required=True,
        ),
        FacetField(
            key="aql_level", name="AQL 等级", type="str", required=False,
            description="抽样方案 AQL（如 'II级 AQL=1.5'）",
        ),
    ],
)


# ════════════════════════════════════════════════════════════════════════
#  导出 dict（用于 IndustryTemplate.facets）
# ════════════════════════════════════════════════════════════════════════

MANUFACTURING_FACETS: dict[str, FacetSchema] = {
    "equipment_fault": EQUIPMENT_FAULT_SCHEMA,
    "process_standard": PROCESS_STANDARD_SCHEMA,
    "sop": SOP_SCHEMA,
    "quality_record": QUALITY_RECORD_SCHEMA,
}
