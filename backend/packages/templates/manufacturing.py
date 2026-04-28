"""制造业知识体系模板。

定义离散制造与流程制造行业的四级知识体系架构。
包含6个L2部门分支：
  - production  生产管理（计划/工艺控制）
  - quality     质量管理（来料/过程/出厂质量）
  - equipment   设备管理（维护/计量校准）
  - warehouse   仓储管理（库存/物流配送）
  - rnd         研发管理（产品设计/新品导入）
  - safety      安全管理（职业健康/消防安全）

本模板在项目创建时由 registry.py 自动注册，通过 get_template("manufacturing") 获取。
"""

from packages.templates.registry import IndustryTemplate, TaxonomyNode

# _N 是 TaxonomyNode 的简写别名
_N = TaxonomyNode

MANUFACTURING_TEMPLATE = IndustryTemplate(
    code="manufacturing",
    name="制造业",
    name_en="Manufacturing",
    icon="Factory",
    description="离散制造与流程制造行业知识管理，涵盖生产质量、设备维护、仓储物流、研发创新和安全管理。",
    taxonomy=[
        _N(id="production", name="生产管理", level=2,
           description="生产计划执行、工艺控制和现场管理。",
           children=[
               _N(id="planning", name="生产计划", level=3,
                  description="产能规划与排产管理。",
                  children=[
                      _N(id="capacity", name="产能规划", level=4, description="产线产能分析与瓶颈识别。"),
                      _N(id="scheduling", name="排产管理", level=4, description="订单排产、插单管理与交期承诺。"),
                      _N(id="lean", name="精益生产", level=4, description="5S、看板、TPM等精益工具实施。"),
                  ]),
               _N(id="process", name="工艺控制", level=3,
                  description="制造工艺标准与过程控制。",
                  children=[
                      _N(id="routing", name="工艺路线", level=4, description="产品工艺路线与工步定义。"),
                      _N(id="spc", name="统计过程控制", level=4, description="SPC控制图与过程能力分析。"),
                  ]),
           ]),
        _N(id="quality", name="质量管理", level=2,
           description="全面质量管理体系，涵盖来料检验、过程控制和成品出厂。",
           children=[
               _N(id="incoming", name="来料质量", level=3,
                  description="原材料与外购件进货检验。",
                  children=[
                      _N(id="iqc", name="IQC检验标准", level=4, description="来料检验规程与AQL抽样方案。"),
                      _N(id="material_spec", name="材料规格书", level=4, description="原材料技术要求与验收标准。"),
                  ]),
               _N(id="process_qa", name="过程质量", level=3,
                  description="制造过程质量监控。",
                  children=[
                      _N(id="ipqc", name="IPQC检验", level=4, description="制程巡检项目与频率要求。"),
                      _N(id="nonconformance", name="不合格品控制", level=4, description="不合格品评审、隔离与处置流程。"),
                  ]),
               _N(id="outgoing", name="出厂质量", level=3,
                  description="成品检验与出货管理。",
                  children=[
                      _N(id="oqc", name="OQC检验标准", level=4, description="成品出厂检验与放行标准。"),
                      _N(id="complaint", name="客诉处理", level=4, description="客户质量投诉处理与8D报告。"),
                  ]),
           ]),
        _N(id="equipment", name="设备管理", level=2,
           description="设备全生命周期管理，从选型采购到维护保养和报废处置。",
           children=[
               _N(id="maintenance", name="设备维护", level=3,
                  description="预防性维护与维修管理。",
                  children=[
                      _N(id="preventive", name="预防性维护", level=4, description="设备保养计划与点检标准。"),
                      _N(id="repair", name="维修管理", level=4, description="故障报修、维修记录与备件管理。"),
                  ]),
               _N(id="calibration", name="计量校准", level=3,
                  description="测量设备与仪器校准。",
                  children=[
                      _N(id="instrument", name="仪器台账", level=4, description="计量器具清单与校准周期。"),
                      _N(id="standard", name="校准规程", level=4, description="各类仪器校准方法与判定标准。"),
                  ]),
           ]),
        _N(id="warehouse", name="仓储管理", level=2,
           description="原材料、半成品和成品的仓储与物流管理。",
           children=[
               _N(id="inventory", name="库存管理", level=3,
                  description="库存控制与盘点。",
                  children=[
                      _N(id="control", name="库存控制", level=4, description="安全库存设定与呆滞料管理。"),
                      _N(id="counting", name="盘点管理", level=4, description="周期盘点与差异处理流程。"),
                  ]),
               _N(id="logistics", name="物流配送", level=3,
                  description="厂内物流与外部配送。",
                  children=[
                      _N(id="internal", name="厂内物流", level=4, description="物料配送路线与AGV调度。"),
                      _N(id="shipping", name="成品发货", level=4, description="发货计划与物流跟踪。"),
                  ]),
           ]),
        _N(id="rnd", name="研发管理", level=2,
           description="产品研发与技术创新管理。",
           children=[
               _N(id="design", name="产品设计", level=3,
                  description="产品开发与设计验证。",
                  children=[
                      _N(id="requirement", name="需求规格", level=4, description="产品技术要求与设计输入。"),
                      _N(id="drawing", name="图纸管理", level=4, description="工程图纸版本控制与变更管理。"),
                      _N(id="validation", name="设计验证", level=4, description="DVP&R验证计划与报告。"),
                  ]),
               _N(id="npi", name="新品导入", level=3,
                  description="新产品试产与量产导入。",
                  children=[
                      _N(id="trial", name="试产管理", level=4, description="试产计划、问题跟踪与量产判定。"),
                      _N(id="ppap", name="PPAP文件", level=4, description="生产件批准程序文件包。"),
                  ]),
           ]),
        _N(id="safety", name="安全管理", level=2,
           description="生产安全与职业健康管理。",
           children=[
               _N(id="occupational", name="职业健康", level=3,
                  description="职业病危害防治与劳动保护。",
                  children=[
                      _N(id="hazard_factors", name="危害因素监测", level=4, description="工作场所职业病危害因素检测。"),
                      _N(id="ppe", name="劳保用品", level=4, description="个人防护用品配备与使用标准。"),
                  ]),
               _N(id="fire", name="消防安全", level=3,
                  description="消防设施管理与防火安全。",
                  children=[
                      _N(id="facility", name="消防设施", level=4, description="消防器材配置与定期检查。"),
                      _N(id="drill", name="消防演练", level=4, description="疏散演练与灭火演练。"),
                  ]),
           ]),
    ],
)
