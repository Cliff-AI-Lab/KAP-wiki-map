"""金融行业知识体系模板。

定义银行、保险、证券等金融行业的四级知识体系架构。
包含5个L2部门分支：
  - risk        风险管理（信用/市场/操作风险）
  - compliance  合规管理（监管/反洗钱/内控）
  - trading     交易管理（执行/清算结算）
  - customer    客户管理（分层/财富管理）
  - operations  运营管理（网点/数字化运营）

本模板在项目创建时由 registry.py 自动注册，通过 get_template("finance") 获取。
"""

from packages.templates.registry import IndustryTemplate, TaxonomyNode

# _N 是 TaxonomyNode 的简写别名
_N = TaxonomyNode

FINANCE_TEMPLATE = IndustryTemplate(
    code="finance",
    name="金融",
    name_en="Finance",
    icon="Landmark",
    description="银行、保险、证券等金融行业知识管理，涵盖风险控制、合规监管、交易管理、客户服务和运营管理。",
    taxonomy=[
        _N(id="risk", name="风险管理", level=2,
           description="信用风险、市场风险和操作风险的识别与控制。",
           children=[
               _N(id="credit", name="信用风险", level=3,
                  description="贷款与信用风险评估管理。",
                  children=[
                      _N(id="rating", name="信用评级", level=4, description="客户信用评级模型与评分标准。"),
                      _N(id="approval", name="审批流程", level=4, description="授信审批权限与风控规则。"),
                      _N(id="monitoring", name="贷后监控", level=4, description="贷后风险预警与催收管理。"),
                  ]),
               _N(id="market", name="市场风险", level=3,
                  description="利率、汇率和资产价格波动风险管理。",
                  children=[
                      _N(id="var", name="VaR模型", level=4, description="风险价值计算方法与回测。"),
                      _N(id="stress_test", name="压力测试", level=4, description="压力情景设计与测试方案。"),
                  ]),
               _N(id="operational", name="操作风险", level=3,
                  description="内部流程、人员和系统的操作风险管理。",
                  children=[
                      _N(id="rcsa", name="风险自评", level=4, description="关键风险与控制自我评估。"),
                      _N(id="loss_event", name="损失事件", level=4, description="操作风险损失数据收集与分析。"),
                  ]),
           ]),
        _N(id="compliance", name="合规管理", level=2,
           description="监管合规、反洗钱与内部控制。",
           children=[
               _N(id="regulatory", name="监管合规", level=3,
                  description="监管政策解读与合规实施。",
                  children=[
                      _N(id="policy", name="监管政策", level=4, description="央行/银保监/证监会政策解读。"),
                      _N(id="reporting", name="监管报送", level=4, description="定期监管报表编制与报送。"),
                  ]),
               _N(id="aml", name="反洗钱", level=3,
                  description="反洗钱与反恐融资管理。",
                  children=[
                      _N(id="kyc", name="客户尽调", level=4, description="KYC客户身份识别与尽职调查。"),
                      _N(id="transaction", name="可疑交易", level=4, description="可疑交易监测与报告。"),
                  ]),
               _N(id="internal_control", name="内部控制", level=3,
                  description="内控制度建设与评价。",
                  children=[
                      _N(id="framework", name="内控框架", level=4, description="内部控制体系架构与关键控制点。"),
                      _N(id="audit", name="内部审计", level=4, description="审计计划、实施与整改跟踪。"),
                  ]),
           ]),
        _N(id="trading", name="交易管理", level=2,
           description="交易执行、清算结算和资产管理。",
           children=[
               _N(id="execution", name="交易执行", level=3,
                  description="各类金融产品交易操作。",
                  children=[
                      _N(id="procedure", name="交易规程", level=4, description="交易操作流程与授权管理。"),
                      _N(id="limit", name="限额管理", level=4, description="交易限额设定与超限审批。"),
                  ]),
               _N(id="settlement", name="清算结算", level=3,
                  description="交易清算与资金结算。",
                  children=[
                      _N(id="process", name="结算流程", level=4, description="日终清算、资金划转流程。"),
                      _N(id="reconciliation", name="对账管理", level=4, description="内外部对账与差异处理。"),
                  ]),
           ]),
        _N(id="customer", name="客户管理", level=2,
           description="客户分层服务、理财规划与投诉处理。",
           children=[
               _N(id="segmentation", name="客户分层", level=3,
                  description="客户分类与差异化服务。",
                  children=[
                      _N(id="classification", name="客户分类标准", level=4, description="资产规模分层与标签体系。"),
                      _N(id="service_model", name="服务模式", level=4, description="各层客户服务标准与权益。"),
                  ]),
               _N(id="wealth", name="财富管理", level=3,
                  description="理财产品与投资顾问服务。",
                  children=[
                      _N(id="product", name="理财产品", level=4, description="理财产品说明书与风险揭示。"),
                      _N(id="advisory", name="投资顾问", level=4, description="资产配置建议与投后服务。"),
                  ]),
           ]),
        _N(id="operations", name="运营管理", level=2,
           description="网点运营、业务流程与IT系统管理。",
           children=[
               _N(id="branch", name="网点运营", level=3,
                  description="营业网点日常运营管理。",
                  children=[
                      _N(id="counter", name="柜面业务", level=4, description="柜面操作规程与服务标准。"),
                      _N(id="cash", name="现金管理", level=4, description="现金库存管理与押运安全。"),
                  ]),
               _N(id="digital", name="数字化运营", level=3,
                  description="线上渠道与数字化转型。",
                  children=[
                      _N(id="mobile", name="移动银行", level=4, description="手机银行功能管理与用户体验。"),
                      _N(id="data_analytics", name="数据分析", level=4, description="经营数据分析与报表体系。"),
                  ]),
           ]),
    ],
)
