---
title: 能源行业测试样例
type: kap-test-samples-industry
industry: energy
parent: "[[../README]]"
project: "[[../../README]]"
file-count: 33
versions: [v7-baseline, v12-revised, v15-extra]
related:
  - "[[../../docs/01-技术决策书]]"
  - "[[../../backend/templates/energy/domain-keywords]]"
  - "[[../../backend/templates/energy/judge-thresholds]]"
status: ready-for-test
---

# 能源行业测试样例（33 文件）

← 测试样例总入口：[`../README.md`](../README.md)
← 项目首页：[`../../README.md`](../../README.md) · [`../../CLAUDE.md`](../../CLAUDE.md)
→ 行业模板：[`../../backend/templates/energy/`](../../backend/templates/energy/)
→ 行业实测报告（V7 历史）：[`../../_refs/wiki-map/bookworm-agent/docs/energy-test-results.md`](../../_refs/wiki-map/bookworm-agent/docs/energy-test-results.md)

## 行业定位

能源是 KAP 首批锁定的两个行业之一（决策书 §1.3）。Wiki-map V15 已有完整的 **53 域 4 级知识体系**，
KAP 直接复用作为行业模板基线（参见 `backend/templates/energy/domain-keywords.yaml`）。

## 三个版本子集

### `v7-baseline/` — V7 早期完整集（18 文件，2026-04 初）

覆盖能源行业 6 个一级业务域：安全 / 生产 / 环保 / 应急 / 物流 / 采购。
主要用于 **W4 实体抽取 + Critic 6 维质疑测试**（含跨文档相同实体，如汽轮机/作业许可）。

| # | 文件 | 格式 | 主题域（domain_id） |
|---|---|---|---|
| 01 | 安全生产责任制 | txt | energy/safety |
| 02 | 隐患排查治理制度 | txt | energy/safety/hazard |
| 03 | 特种设备安全管理规定 | txt | energy/safety + energy/production/equipment |
| 04 | 催化裂化装置操作规程 | txt | energy/production/process/sop |
| 05 | 设备预防性维护计划 | txt | energy/production/equipment/maintenance |
| 06 | 生产调度管理办法 | txt | energy/production/scheduling |
| 07 | 废气排放监测管理办法 | txt | energy/environment |
| 08 | 环境应急预案 | txt | energy/emergency + energy/environment |
| 09 | 火灾爆炸事故应急预案 | txt | energy/emergency |
| 10 | 危险化学品泄漏应急处置方案 | txt | energy/emergency |
| 11 | 设备采购管理规范 | txt | energy/procurement |
| 12 | 物资入库检验标准 | txt | energy/procurement |
| 13 | 危险化学品运输安全管理规程 | md | energy/logistics + energy/safety |
| 14 | 安全培训管理办法 | md | energy/safety/training |
| 15 | 废水处理与排放管理制度 | md | energy/environment |
| 16 | 危化品仓储安全管理规定 | docx | energy/logistics + energy/safety |
| 17 | 供应商准入与绩效评价管理办法 | docx | energy/procurement |
| 18 | 应急演练计划与评估管理办法 | docx | energy/emergency |

### `v12-revised/` — V12 精简标准基线（10 文件）

V12 阶段重新精挑的 10 份样本，覆盖能源行业核心十大主题，**推荐用于 W2 自动归类回归**。

| # | 文件 | 格式 | 主题域 |
|---|---|---|---|
| 01 | 安全生产管理制度 | txt | energy/safety |
| 02 | 化工装置操作规程 | md | energy/production/process/sop |
| 03 | 环保废气处理方案 | txt | energy/environment |
| 04 | 特种设备管理规定 | md | energy/production/equipment |
| 05 | 电气安全作业标准 | txt | energy/safety/permit |
| 06 | 消防应急预案 | md | energy/emergency |
| 07 | 危化品储运管理 | txt | energy/logistics + energy/safety |
| 08 | 职业健康管理制度 | md | energy/safety + energy/safety/training |
| 09 | 节能减排年度报告 | txt | energy/environment |
| 10 | 设备点检与润滑标准 | md | energy/production/equipment/inspection + maintenance |

### `v15-extra/` — V15 增补真实场景集（5 文件，多格式）

V15 阶段补的 5 份**真实电力 / 配电网场景**样本，**主要用于 W1 多模态解析测试**（含 pdf/html/docx 三种主流非 txt 格式）。

| 文件 | 格式 | 主题域 | 解析考察点 |
|---|---|---|---|
| 35kV及以下电网设备验收技术要求 | docx | energy/production/equipment | Word 表格 / 多级标题 |
| 南方电网调度自动化系统运维管理办法 | html | energy/production/scheduling | HTML 解析 + 嵌入图片 |
| 变电站二次设备运行维护规程 | txt | energy/production/equipment/maintenance | 纯文本 baseline |
| 国家电网客户用电业务管理实施细则 | md | energy/production + 客户服务 | Markdown 结构化 |
| 配电网带电作业操作规程 | pdf | energy/safety/permit | PDF 多页 + 图表 |

## 推荐测试组合

| 测试目标 | 数据集 | 期望指标 |
|---|---|---|
| 端到端冒烟（最快）| `v12-revised/` 10 份 | KAP-Lite Day 1 演示 ≤ 5 min 蒸馏完毕 |
| W1 多模态解析覆盖 | `v15-extra/` 5 份（pdf+html+docx+md+txt）| 全格式无解析失败 |
| W2 归类准确率 | `v12-revised/` 10 份 + 期望 domain_id 表 | ≥ 90%（决策书 §F1.2 验收标准）|
| W4 关系抽取 | `v7-baseline/` 18 份（含同实体跨文档）| 同实体合并提议触发 |
| 大批量并发压测 | 全 33 份 × 5 倍 | `arun_pipeline` 并发不阻塞 |

## 行业 53 域映射参考

V15 实测时建立的能源 4 级体系（来自 [`../../_refs/wiki-map/bookworm-agent/docs/energy-test-results.md`](../../_refs/wiki-map/bookworm-agent/docs/energy-test-results.md)）：

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

完整规则见 [`../../backend/templates/energy/domain-keywords.yaml`](../../backend/templates/energy/domain-keywords.yaml)。
