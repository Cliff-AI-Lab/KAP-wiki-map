---
title: IT 行业测试样例
type: kap-test-samples-industry
industry: it
file-count: 5
status: cross-industry-utility
---

# IT 行业测试样例（5 文件）

> 导航：[← 测试样例总入口](../README.md) · [← 项目首页](../../README.md) · [决策书](../../docs/01-技术决策书.md) · [配套通用模板](../../backend/templates/_default/)

IT **不是 KAP 首批锁定行业**，但所有客户（含制造 / 能源 / 金融）都有 IT 内部知识管理需求。
本集主要用作 **`_default` 通用模板的回归测试基线**（[决策书 §7.4](../../docs/01-技术决策书.md)），
也是**自身知识管理**（KAP 团队自己用 KAP 管理代码 / 文档）的样例。

配套：[backend/templates/_default/domain-keywords.yaml](../../backend/templates/_default/domain-keywords.yaml)

## 文件清单

| # | 文件 | 类别 | 主题域（_default 模板）|
|---|---|---|---|
| 1 | [代码审查流程v2.0.txt](./代码审查流程v2.0.txt) | 工程流程 | tech / project/sprint |
| 2 | [信息安全管理制度.txt](./信息安全管理制度.txt) | 安全合规 | regulation + tech |
| 3 | [微服务架构设计规范.txt](./微服务架构设计规范.txt) | 架构 | tech/architecture |
| 4 | [敏捷开发迭代规范.txt](./敏捷开发迭代规范.txt) | 项目管理 | project/sprint |
| 5 | [数据库运维手册.txt](./数据库运维手册.txt) | DBA | tech/deploy |

## 推荐测试场景

| 场景 | 用法 | 期望 |
|---|---|---|
| `_default` 通用模板回归 | 5 份按 [`_default/domain-keywords.yaml`](../../backend/templates/_default/domain-keywords.yaml) 分类 | 应全部命中 tech/* 或 project/*，无 routing_pending |
| 命名规范多版本号识别 | "[代码审查流程v2.0](./代码审查流程v2.0.txt)" 文件名解析 | Librarian Agent 应正确提取 version=v2.0 |
| 跨行业冲突识别 | 与 [能源 v12-revised/](../energy/README.md#v12-revised) 混合 | IT 文档不应被误归到 energy/* |
| 跨域引用关系 | [信息安全管理制度.txt](./信息安全管理制度.txt)（regulation + tech）| Refiner 应抽出多 domain 标签或主域 + Facet 分配 |

## 与 KAP 自身的关系

KAP 团队自用场景：用 KAP 管理 KAP 自己的开发文档（dogfood）。
本测试集对应 [docs/](../../docs/) 下文档的"原型"——
未来真正落地时，可把 [docs/01-技术决策书.md](../../docs/01-技术决策书.md) 等也当成
KAP 内部 IT 文档跑端到端，验证"本平台能管自己的知识库"。

---

## 图谱锚点（Obsidian 反向关联）

**上行**：[← 测试样例总入口](../README.md) → [← 项目首页](../../README.md) → [Claude 内存](../../CLAUDE.md)

**KAP 主线**：[决策书 §7.4](../../docs/01-技术决策书.md) · [PRD](../../docs/02-产品需求PRD.md) · [M0 技改地图](../../docs/M0-tech-debt.md) · [上游参考索引](../../docs/_refs-index.md)

**配套通用模板**：[\_default/domain-keywords.yaml](../../backend/templates/_default/domain-keywords.yaml)

**横向参考**：[能源样例](../energy/README.md) · [制造样例](../manufacturing/README.md) · [金融样例](../finance/README.md)

**dogfood 参考**：[KAP 自身 docs/](../../docs/) · [01-技术决策书](../../docs/01-技术决策书.md) · [02-产品需求PRD](../../docs/02-产品需求PRD.md)
