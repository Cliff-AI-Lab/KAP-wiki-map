"""能源行业知识体系模板。

定义石油、天然气、电力、新能源等能源行业的四级知识体系架构。
包含6个L2部门分支：
  - production  生产管理（工艺/设备/调度）
  - safety      安全管理（隐患排查/安全培训/作业许可）
  - environmental 环保管理（排放/监测）
  - emergency   应急管理（预案/演练）
  - logistics   物流管理（运输/仓储）
  - procurement 采购管理（供应商/合同）

本模板在项目创建时由 registry.py 自动注册，通过 get_template("energy") 获取。
SkillsRouter 在检索时依据此体系定位知识分支，实现按需激活检索。
"""

from packages.templates.registry import IndustryTemplate, TaxonomyNode

# _N 是 TaxonomyNode 的简写别名，减少模板定义中的代码冗余
_N = TaxonomyNode

ENERGY_TEMPLATE = IndustryTemplate(
    code="energy",
    name="能源",
    name_en="Energy",
    icon="Zap",
    description="石油、天然气、电力、新能源等能源行业知识管理，涵盖生产运营、安全环保、应急物流等核心业务领域。",
    taxonomy=[
        _N(id="production", name="生产管理", level=2,
           description="生产运营全流程管理，包括工艺、设备、调度和计量。",
           children=[
               _N(id="process", name="工艺管理", level=3,
                  description="生产工艺标准与操作规范。",
                  children=[
                      _N(id="sop", name="标准操作规程", level=4, description="各工序标准化作业指导书。"),
                      _N(id="params", name="工艺参数标准", level=4, description="关键工艺参数范围与控制要求。"),
                      _N(id="optimization", name="工艺优化记录", level=4, description="工艺改进方案与实施效果。"),
                  ]),
               _N(id="equipment", name="设备管理", level=3,
                  description="设备全生命周期管理。",
                  children=[
                      _N(id="maintenance", name="检维修规程", level=4, description="设备维护保养与检修标准。"),
                      _N(id="inspection", name="巡检标准", level=4, description="日常巡检路线、项目与判定标准。"),
                      _N(id="fault", name="故障处理手册", level=4, description="常见故障诊断与应急处理方案。"),
                  ]),
               _N(id="scheduling", name="生产调度", level=3,
                  description="生产计划与调度协调。",
                  children=[
                      _N(id="plan", name="生产计划", level=4, description="年度/月度/周生产计划编制与调整。"),
                      _N(id="handover", name="交接班制度", level=4, description="班组交接班流程与记录要求。"),
                  ]),
           ]),
        _N(id="safety", name="安全管理", level=2,
           description="安全生产责任体系、隐患排查治理、安全培训与特种作业管理。",
           children=[
               _N(id="hazard", name="隐患排查", level=3,
                  description="安全隐患的辨识、评估与治理。",
                  children=[
                      _N(id="identification", name="隐患辨识标准", level=4, description="各类安全隐患辨识方法与分级标准。"),
                      _N(id="rectification", name="整改管理规范", level=4, description="隐患整改流程、验收与闭环管理。"),
                  ]),
               _N(id="training", name="安全培训", level=3,
                  description="全员安全教育与专项培训。",
                  children=[
                      _N(id="induction", name="入职安全培训", level=4, description="三级安全教育内容与考核标准。"),
                      _N(id="special", name="特种作业培训", level=4, description="特种作业人员资质与复训要求。"),
                  ]),
               _N(id="permit", name="作业许可", level=3,
                  description="危险作业审批与安全措施。",
                  children=[
                      _N(id="hot_work", name="动火作业", level=4, description="动火作业审批、监护与安全措施。"),
                      _N(id="confined", name="受限空间", level=4, description="受限空间作业安全管理规程。"),
                  ]),
           ]),
        _N(id="environmental", name="环保管理", level=2,
           description="环境保护与污染防治，废气废水废渣处理与排放管理。",
           children=[
               _N(id="emission", name="排放管理", level=3,
                  description="污染物排放监测与达标管理。",
                  children=[
                      _N(id="gas", name="废气排放标准", level=4, description="大气污染物排放限值与监测要求。"),
                      _N(id="water", name="废水排放标准", level=4, description="废水处理工艺与排放指标。"),
                      _N(id="solid", name="固废处置规范", level=4, description="危废与一般固废分类处置标准。"),
                  ]),
               _N(id="monitoring", name="环境监测", level=3,
                  description="环境质量监测体系。",
                  children=[
                      _N(id="online", name="在线监测", level=4, description="自动监测设备运维与数据管理。"),
                      _N(id="report", name="环保报告", level=4, description="环境影响评价与定期报告。"),
                  ]),
           ]),
        _N(id="emergency", name="应急管理", level=2,
           description="突发事件应急预案、演练与响应机制。",
           children=[
               _N(id="plan", name="应急预案", level=3,
                  description="各类突发事件应急处置方案。",
                  children=[
                      _N(id="comprehensive", name="综合应急预案", level=4, description="公司级综合应急预案与组织架构。"),
                      _N(id="special", name="专项应急预案", level=4, description="火灾、泄漏、中毒等专项应急方案。"),
                      _N(id="onsite", name="现场处置方案", level=4, description="岗位级现场紧急处置卡。"),
                  ]),
               _N(id="drill", name="应急演练", level=3,
                  description="应急演练组织与评估。",
                  children=[
                      _N(id="plan_drill", name="演练计划", level=4, description="年度演练计划与情景设计。"),
                      _N(id="evaluation", name="演练评估", level=4, description="演练效果评估与改进措施。"),
                  ]),
           ]),
        _N(id="logistics", name="物流管理", level=2,
           description="物料运输、仓储管理与供应链调度。",
           children=[
               _N(id="transport", name="运输管理", level=3,
                  description="物料运输安全与调度。",
                  children=[
                      _N(id="hazmat", name="危化品运输", level=4, description="危险化学品运输安全规程。"),
                      _N(id="scheduling", name="运输调度", level=4, description="车辆调度与路线管理。"),
                  ]),
               _N(id="warehouse", name="仓储管理", level=3,
                  description="物料出入库与库存管理。",
                  children=[
                      _N(id="inventory", name="库存管理", level=4, description="物料出入库流程与盘点标准。"),
                      _N(id="hazmat_storage", name="危化品存储", level=4, description="危险化学品储存安全管理。"),
                  ]),
           ]),
        _N(id="procurement", name="采购管理", level=2,
           description="物资采购、供应商管理与合同管理。",
           children=[
               _N(id="supplier", name="供应商管理", level=3,
                  description="供应商准入、评价与退出机制。",
                  children=[
                      _N(id="qualification", name="资质审核", level=4, description="供应商资质审核与准入标准。"),
                      _N(id="evaluation", name="绩效评价", level=4, description="供应商年度绩效考核与分级。"),
                  ]),
               _N(id="contract", name="合同管理", level=3,
                  description="采购合同签订与履行管理。",
                  children=[
                      _N(id="template", name="合同范本", level=4, description="标准采购合同模板与条款。"),
                      _N(id="execution", name="履约管理", level=4, description="合同执行跟踪与付款审批。"),
                  ]),
           ]),
    ],
)
