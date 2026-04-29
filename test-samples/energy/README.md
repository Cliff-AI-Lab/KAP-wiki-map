---
title: 能源行业测试样例
type: kap-test-samples-industry
industry: energy
file-count: 33
---

# 能源行业测试样例（33 文件）

> 导航：[← 测试样例总入口](../README.md) · [← 项目首页](../../README.md) · [决策书 §7.2](../../docs/01-技术决策书.md) · [配套行业模板](../../backend/templates/energy/) · [V15 实测报告（来源）](../../_refs/wiki-map/bookworm-agent/docs/energy-test-results.md)

能源是 KAP 首批锁定的两个行业之一（[决策书 §1.3](../../docs/01-技术决策书.md)）。
Wiki-map V15 已有完整的 **53 域 4 级知识体系**，KAP 直接复用作为行业模板基线。

配套：

- [backend/templates/energy/domain-keywords.yaml](../../backend/templates/energy/domain-keywords.yaml) — 17 条关键词规则
- [backend/templates/energy/judge-thresholds.yaml](../../backend/templates/energy/judge-thresholds.yaml) — 能源调优阈值

## 三个版本子集

### V7 早期完整集（18 文件） {#v7-baseline}

覆盖能源行业 6 个一级业务域：安全 / 生产 / 环保 / 应急 / 物流 / 采购。
主要用于 **W4 实体抽取 + Critic 6 维质疑测试**（含跨文档相同实体）。

| # | 文件 | 主题域（domain_id） |
|---|---|---|
| 01 | [01_安全生产责任制.txt](./v7-baseline/01_安全生产责任制.txt) | energy/safety |
| 02 | [02_隐患排查治理制度.txt](./v7-baseline/02_隐患排查治理制度.txt) | energy/safety/hazard |
| 03 | [03_特种设备安全管理规定.txt](./v7-baseline/03_特种设备安全管理规定.txt) | energy/safety + energy/production/equipment |
| 04 | [04_催化裂化装置操作规程.txt](./v7-baseline/04_催化裂化装置操作规程.txt) | energy/production/process/sop |
| 05 | [05_设备预防性维护计划.txt](./v7-baseline/05_设备预防性维护计划.txt) | energy/production/equipment/maintenance |
| 06 | [06_生产调度管理办法.txt](./v7-baseline/06_生产调度管理办法.txt) | energy/production/scheduling |
| 07 | [07_废气排放监测管理办法.txt](./v7-baseline/07_废气排放监测管理办法.txt) | energy/environment |
| 08 | [08_环境应急预案.txt](./v7-baseline/08_环境应急预案.txt) | energy/emergency + energy/environment |
| 09 | [09_火灾爆炸事故应急预案.txt](./v7-baseline/09_火灾爆炸事故应急预案.txt) | energy/emergency |
| 10 | [10_危险化学品泄漏应急处置方案.txt](./v7-baseline/10_危险化学品泄漏应急处置方案.txt) | energy/emergency |
| 11 | [11_设备采购管理规范.txt](./v7-baseline/11_设备采购管理规范.txt) | energy/procurement |
| 12 | [12_物资入库检验标准.txt](./v7-baseline/12_物资入库检验标准.txt) | energy/procurement |
| 13 | [13_危险化学品运输安全管理规程.md](./v7-baseline/13_危险化学品运输安全管理规程.md) | energy/logistics + energy/safety |
| 14 | [14_安全培训管理办法.md](./v7-baseline/14_安全培训管理办法.md) | energy/safety/training |
| 15 | [15_废水处理与排放管理制度.md](./v7-baseline/15_废水处理与排放管理制度.md) | energy/environment |
| 16 | [16_危化品仓储安全管理规定.docx](./v7-baseline/16_危化品仓储安全管理规定.docx) | energy/logistics + energy/safety |
| 17 | [17_供应商准入与绩效评价管理办法.docx](./v7-baseline/17_供应商准入与绩效评价管理办法.docx) | energy/procurement |
| 18 | [18_应急演练计划与评估管理办法.docx](./v7-baseline/18_应急演练计划与评估管理办法.docx) | energy/emergency |

### V12 精简标准基线（10 文件） {#v12-revised}

V12 阶段重新精挑的 10 份样本，覆盖能源行业核心十大主题，**推荐用于 W2 自动归类回归**。

| # | 文件 | 主题域 |
|---|---|---|
| 01 | [01_安全生产管理制度.txt](./v12-revised/01_安全生产管理制度.txt) | energy/safety |
| 02 | [02_化工装置操作规程.md](./v12-revised/02_化工装置操作规程.md) | energy/production/process/sop |
| 03 | [03_环保废气处理方案.txt](./v12-revised/03_环保废气处理方案.txt) | energy/environment |
| 04 | [04_特种设备管理规定.md](./v12-revised/04_特种设备管理规定.md) | energy/production/equipment |
| 05 | [05_电气安全作业标准.txt](./v12-revised/05_电气安全作业标准.txt) | energy/safety/permit |
| 06 | [06_消防应急预案.md](./v12-revised/06_消防应急预案.md) | energy/emergency |
| 07 | [07_危化品储运管理.txt](./v12-revised/07_危化品储运管理.txt) | energy/logistics + energy/safety |
| 08 | [08_职业健康管理制度.md](./v12-revised/08_职业健康管理制度.md) | energy/safety + energy/safety/training |
| 09 | [09_节能减排年度报告.txt](./v12-revised/09_节能减排年度报告.txt) | energy/environment |
| 10 | [10_设备点检与润滑标准.md](./v12-revised/10_设备点检与润滑标准.md) | energy/production/equipment/inspection + maintenance |

### V15 增补真实场景集（5 文件，多格式） {#v15-extra}

V15 阶段补的 5 份**真实电力 / 配电网场景**样本，**主要用于 W1 多模态解析测试**（含 pdf/html/docx 三种主流非 txt 格式）。

| # | 文件 | 主题域 | 解析考察点 |
|---|---|---|---|
| 1 | [35kV及以下电网设备验收技术要求.docx](./v15-extra/35kV及以下电网设备验收技术要求.docx) | energy/production/equipment | Word 表格 / 多级标题 |
| 2 | [南方电网调度自动化系统运维管理办法.html](./v15-extra/南方电网调度自动化系统运维管理办法.html) | energy/production/scheduling | HTML 解析 + 嵌入图片 |
| 3 | [变电站二次设备运行维护规程.txt](./v15-extra/变电站二次设备运行维护规程.txt) | energy/production/equipment/maintenance | 纯文本 baseline |
| 4 | [国家电网客户用电业务管理实施细则.md](./v15-extra/国家电网客户用电业务管理实施细则.md) | energy/production + 客户服务 | Markdown 结构化 |
| 5 | [配电网带电作业操作规程.pdf](./v15-extra/配电网带电作业操作规程.pdf) | energy/safety/permit | PDF 多页 + 图表 |

## 推荐测试组合

| 测试目标 | 数据集 | 期望指标 |
|---|---|---|
| 端到端冒烟（最快）| [v12-revised/](#v12-revised) 10 份 | KAP-Lite Day 1 演示 ≤ 5 min 蒸馏完毕 |
| W1 多模态解析覆盖 | [v15-extra/](#v15-extra) 5 份（pdf+html+docx+md+txt）| 全格式无解析失败 |
| W2 归类准确率 | [v12-revised/](#v12-revised) 10 份 + 期望 domain_id 表 | ≥ 90%（决策书 §F1.2 验收标准）|
| W4 关系抽取 | [v7-baseline/](#v7-baseline) 18 份（含同实体跨文档）| 同实体合并提议触发 |
| 大批量并发压测 | 全 33 份 × 5 倍 | `arun_pipeline` 并发不阻塞 |

## 行业 53 域映射参考

V15 实测时建立的能源 4 级体系（来自 [V15 实测报告](../../_refs/wiki-map/bookworm-agent/docs/energy-test-results.md)）：

```
energy/
  ├── safety/
  │   ├── hazard/         (隐患排查)
  │   ├── training/       (安全培训)
  │   └── permit/         (作业许可：动火/高处/受限空间)
  ├── production/
  │   ├── process/        (工艺管理：sop / params / optimization)
  │   ├── equipment/      (设备：maintenance / inspection / fault)
  │   └── scheduling/     (生产调度)
  ├── environment/        (环保管理)
  ├── emergency/          (应急管理)
  ├── logistics/          (物流管理)
  └── procurement/        (采购管理)
```

完整规则见 [domain-keywords.yaml](../../backend/templates/energy/domain-keywords.yaml)。

---

## 图谱锚点（Obsidian 反向关联）

**上行**：[← 测试样例总入口](../README.md) → [← 项目首页](../../README.md) → [Claude 内存](../../CLAUDE.md)

**KAP 主线**：[决策书 §7.2](../../docs/01-技术决策书.md) · [PRD §10.5](../../docs/02-产品需求PRD.md) · [M0 技改地图](../../docs/M0-tech-debt.md) · [上游参考索引](../../docs/_refs-index.md)

**配套模板**：[domain-keywords.yaml](../../backend/templates/energy/domain-keywords.yaml) · [judge-thresholds.yaml](../../backend/templates/energy/judge-thresholds.yaml)

**横向参考**：[制造样例](../manufacturing/README.md) · [金融样例](../finance/README.md) · [IT 样例](../it/README.md)

**上游来源**：[Wiki-map V15 docs/energy-test-results.md](../../_refs/wiki-map/bookworm-agent/docs/energy-test-results.md) · [上游 README](../../_refs/wiki-map/bookworm-agent/docs/v15-summary.md)
