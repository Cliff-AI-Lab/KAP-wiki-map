"""医疗健康行业知识体系模板。

定义医院、诊所与健康服务行业的四级知识体系架构。
包含5个L2部门分支：
  - clinical      临床医疗（诊疗规范/病历管理/医疗质量）
  - pharmacy      药学服务（药品管理/临床药学）
  - nursing       护理管理（护理质量/护理培训）
  - public_health 公共卫生（疾病预防/健康教育）
  - admin         行政管理（人力资源/财务/后勤）

本模板在项目创建时由 registry.py 自动注册，通过 get_template("healthcare") 获取。
"""

from packages.templates.registry import IndustryTemplate, TaxonomyNode

# _N 是 TaxonomyNode 的简写别名
_N = TaxonomyNode

HEALTHCARE_TEMPLATE = IndustryTemplate(
    code="healthcare",
    name="医疗健康",
    name_en="Healthcare",
    icon="Heart",
    description="医院、诊所与健康服务行业知识管理，涵盖临床医疗、药学服务、护理管理、公共卫生和行政管理。",
    taxonomy=[
        _N(id="clinical", name="临床医疗", level=2,
           description="临床诊疗规范、病历管理与医疗质量控制。",
           children=[
               _N(id="diagnosis", name="诊疗规范", level=3,
                  description="各科室诊疗指南与临床路径。",
                  children=[
                      _N(id="guideline", name="临床指南", level=4, description="各专科疾病诊疗指南与共识。"),
                      _N(id="pathway", name="临床路径", level=4, description="标准化诊疗路径与变异管理。"),
                      _N(id="consultation", name="会诊制度", level=4, description="多学科会诊流程与转诊标准。"),
                  ]),
               _N(id="medical_record", name="病历管理", level=3,
                  description="电子病历与医疗文书。",
                  children=[
                      _N(id="emr", name="电子病历规范", level=4, description="病历书写标准与质控要求。"),
                      _N(id="informed_consent", name="知情同意", level=4, description="各类知情同意书模板与签署规范。"),
                  ]),
               _N(id="quality_control", name="医疗质量", level=3,
                  description="医疗质量监控与改进。",
                  children=[
                      _N(id="indicator", name="质量指标", level=4, description="核心医疗质量与安全指标。"),
                      _N(id="adverse_event", name="不良事件", level=4, description="医疗不良事件报告与分析。"),
                  ]),
           ]),
        _N(id="pharmacy", name="药学服务", level=2,
           description="药品管理、处方审核与临床药学服务。",
           children=[
               _N(id="drug_mgmt", name="药品管理", level=3,
                  description="药品采购、储存与使用管理。",
                  children=[
                      _N(id="formulary", name="药品目录", level=4, description="医院基本药物目录与遴选标准。"),
                      _N(id="storage", name="药品储存", level=4, description="药品分类存放与效期管理。"),
                      _N(id="narcotic", name="特殊药品", level=4, description="麻醉药品、精神药品管理规范。"),
                  ]),
               _N(id="clinical_pharmacy", name="临床药学", level=3,
                  description="处方审核与合理用药。",
                  children=[
                      _N(id="prescription", name="处方审核", level=4, description="处方审核要点与干预记录。"),
                      _N(id="adr", name="药物不良反应", level=4, description="ADR监测与报告管理。"),
                  ]),
           ]),
        _N(id="nursing", name="护理管理", level=2,
           description="护理质量、培训与患者安全管理。",
           children=[
               _N(id="care", name="护理质量", level=3,
                  description="护理操作规范与质量评价。",
                  children=[
                      _N(id="procedure", name="护理操作规程", level=4, description="基础与专科护理操作标准。"),
                      _N(id="assessment", name="护理评估", level=4, description="跌倒、压疮等风险评估工具。"),
                      _N(id="documentation", name="护理文书", level=4, description="护理记录书写规范。"),
                  ]),
               _N(id="education", name="护理培训", level=3,
                  description="护理人员能力培养。",
                  children=[
                      _N(id="orientation", name="新护士培训", level=4, description="新入职护士规范化培训方案。"),
                      _N(id="specialist", name="专科护士", level=4, description="专科护士培养计划与考核。"),
                  ]),
           ]),
        _N(id="public_health", name="公共卫生", level=2,
           description="传染病防控、健康教育与卫生应急。",
           children=[
               _N(id="prevention", name="疾病预防", level=3,
                  description="传染病监测与预防控制。",
                  children=[
                      _N(id="surveillance", name="疫情监测", level=4, description="传染病报告与监测预警。"),
                      _N(id="vaccination", name="预防接种", level=4, description="免疫规划与接种异常反应处理。"),
                  ]),
               _N(id="health_education", name="健康教育", level=3,
                  description="健康促进与患者教育。",
                  children=[
                      _N(id="material", name="宣教材料", level=4, description="疾病防治与健康生活方式宣教。"),
                      _N(id="chronic", name="慢病管理", level=4, description="高血压/糖尿病等慢病随访管理。"),
                  ]),
           ]),
        _N(id="admin", name="行政管理", level=2,
           description="医院综合行政、人力资源与财务管理。",
           children=[
               _N(id="hr", name="人力资源", level=3,
                  description="医院人事与绩效管理。",
                  children=[
                      _N(id="recruitment", name="人员招聘", level=4, description="岗位编制与招聘录用流程。"),
                      _N(id="performance", name="绩效考核", level=4, description="科室与个人绩效考核方案。"),
                  ]),
               _N(id="finance", name="财务管理", level=3,
                  description="医院财务与成本控制。",
                  children=[
                      _N(id="billing", name="收费管理", level=4, description="医疗收费项目与物价标准。"),
                      _N(id="cost", name="成本核算", level=4, description="科室成本核算与预算管理。"),
                  ]),
               _N(id="facility", name="后勤保障", level=3,
                  description="医院后勤与设备设施管理。",
                  children=[
                      _N(id="medical_equipment", name="医疗设备", level=4, description="大型医疗设备采购与维护。"),
                      _N(id="infection_control", name="院感控制", level=4, description="医院感染预防与消毒隔离。"),
                  ]),
           ]),
    ],
)
