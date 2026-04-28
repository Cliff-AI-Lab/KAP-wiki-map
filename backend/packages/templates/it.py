"""信息技术行业知识体系模板。

定义软件开发、系统集成与IT服务行业的四级知识体系架构。
包含6个L2部门分支：
  - product    产品管理（需求/路线图）
  - tech       技术管理（架构/开发规范/运维部署）
  - project    项目管理（敏捷/交付）
  - quality    质量管理（测试/缺陷）
  - customer   客户管理（售前/售后）
  - compliance 合规管理（信息安全/知识产权）

本模板在项目创建时由 registry.py 自动注册，通过 get_template("it") 获取。
当前 demo 数据（AI质检系统）使用此模板。
"""

from packages.templates.registry import IndustryTemplate, TaxonomyNode

# _N 是 TaxonomyNode 的简写别名
_N = TaxonomyNode

IT_TEMPLATE = IndustryTemplate(
    code="it",
    name="信息技术",
    name_en="Information Technology",
    icon="Monitor",
    description="软件开发、系统集成与IT服务行业知识管理，涵盖产品研发、技术架构、项目交付、质量保障和客户服务。",
    taxonomy=[
        _N(id="product", name="产品管理", level=2,
           description="产品规划、需求分析与产品运营。",
           children=[
               _N(id="requirement", name="需求管理", level=3,
                  description="需求采集、分析与优先级管理。",
                  children=[
                      _N(id="prd", name="产品需求文档", level=4, description="PRD编写规范与模板。"),
                      _N(id="user_story", name="用户故事", level=4, description="用户故事编写与验收标准。"),
                      _N(id="competitive", name="竞品分析", level=4, description="竞品调研报告与功能对标。"),
                  ]),
               _N(id="roadmap", name="产品路线图", level=3,
                  description="产品版本规划与发布计划。",
                  children=[
                      _N(id="version", name="版本规划", level=4, description="季度/年度版本功能规划。"),
                      _N(id="release", name="发布管理", level=4, description="发布流程与变更通知。"),
                  ]),
           ]),
        _N(id="tech", name="技术管理", level=2,
           description="系统架构、开发规范与技术运维。",
           children=[
               _N(id="architecture", name="架构设计", level=3,
                  description="系统架构与技术选型。",
                  children=[
                      _N(id="system", name="系统架构文档", level=4, description="整体架构图、模块划分与接口定义。"),
                      _N(id="selection", name="技术选型", level=4, description="框架/中间件/数据库选型评估。"),
                      _N(id="api", name="API接口文档", level=4, description="接口规范、协议定义与联调指南。"),
                  ]),
               _N(id="development", name="开发规范", level=3,
                  description="编码标准与代码管理。",
                  children=[
                      _N(id="coding", name="编码规范", level=4, description="语言编码风格与命名约定。"),
                      _N(id="git", name="版本控制", level=4, description="Git分支策略与提交规范。"),
                      _N(id="review", name="代码审查", level=4, description="Code Review流程与检查清单。"),
                  ]),
               _N(id="devops", name="运维部署", level=3,
                  description="持续集成、部署与监控。",
                  children=[
                      _N(id="cicd", name="CI/CD流水线", level=4, description="构建、测试、部署自动化流程。"),
                      _N(id="monitoring", name="监控告警", level=4, description="系统监控指标与告警规则。"),
                      _N(id="incident", name="故障处理", level=4, description="故障分级、响应与复盘流程。"),
                  ]),
           ]),
        _N(id="project", name="项目管理", level=2,
           description="项目计划执行、资源协调与交付管理。",
           children=[
               _N(id="agile", name="敏捷管理", level=3,
                  description="Scrum/Kanban敏捷实践。",
                  children=[
                      _N(id="sprint", name="Sprint管理", level=4, description="迭代规划、每日站会与回顾。"),
                      _N(id="backlog", name="Backlog管理", level=4, description="需求池维护与优先级排序。"),
                  ]),
               _N(id="delivery", name="交付管理", level=3,
                  description="里程碑与验收管理。",
                  children=[
                      _N(id="milestone", name="里程碑计划", level=4, description="关键里程碑定义与进度跟踪。"),
                      _N(id="acceptance", name="验收标准", level=4, description="项目验收条件与交付物清单。"),
                  ]),
           ]),
        _N(id="quality", name="质量管理", level=2,
           description="软件测试与质量保障体系。",
           children=[
               _N(id="testing", name="测试管理", level=3,
                  description="测试策略与执行。",
                  children=[
                      _N(id="plan", name="测试计划", level=4, description="测试范围、策略与资源安排。"),
                      _N(id="case", name="测试用例", level=4, description="功能测试、性能测试与自动化测试。"),
                      _N(id="report", name="测试报告", level=4, description="测试结果汇总与缺陷分析。"),
                  ]),
               _N(id="bug", name="缺陷管理", level=3,
                  description="缺陷跟踪与分析。",
                  children=[
                      _N(id="tracking", name="缺陷跟踪", level=4, description="Bug提交规范与生命周期管理。"),
                      _N(id="analysis", name="缺陷分析", level=4, description="缺陷趋势分析与根因定位。"),
                  ]),
           ]),
        _N(id="customer", name="客户管理", level=2,
           description="客户需求对接、售后服务与满意度管理。",
           children=[
               _N(id="presales", name="售前支持", level=3,
                  description="客户需求调研与方案输出。",
                  children=[
                      _N(id="proposal", name="解决方案", level=4, description="技术方案与报价文档。"),
                      _N(id="demo", name="演示与POC", level=4, description="产品演示脚本与POC实施。"),
                  ]),
               _N(id="support", name="售后服务", level=3,
                  description="技术支持与客户反馈。",
                  children=[
                      _N(id="ticket", name="工单管理", level=4, description="客户问题受理与处理流程。"),
                      _N(id="feedback", name="客户反馈", level=4, description="满意度调查与改进措施。"),
                  ]),
           ]),
        _N(id="compliance", name="合规管理", level=2,
           description="信息安全、数据保护与法规遵从。",
           children=[
               _N(id="security", name="信息安全", level=3,
                  description="网络安全与数据保护。",
                  children=[
                      _N(id="policy", name="安全策略", level=4, description="信息安全管理制度与等级保护。"),
                      _N(id="data_protection", name="数据保护", level=4, description="个人信息保护与数据分级分类。"),
                  ]),
               _N(id="license", name="知识产权", level=3,
                  description="软件著作权与专利管理。",
                  children=[
                      _N(id="copyright", name="著作权管理", level=4, description="软件著作权登记与开源合规。"),
                      _N(id="patent", name="专利管理", level=4, description="技术专利申请与维护。"),
                  ]),
           ]),
    ],
)
