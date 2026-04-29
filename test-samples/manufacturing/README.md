---
title: 制造行业测试样例
type: kap-test-samples-industry
industry: manufacturing
file-count: 5
---

# 制造行业测试样例（5 文件）

> 导航：[← 测试样例总入口](../README.md) · [← 项目首页](../../README.md) · [决策书 §7.1](../../docs/01-技术决策书.md) · [配套行业模板](../../backend/templates/manufacturing/)

制造业是 KAP 首批锁定的两个行业之一（[决策书 §1.3](../../docs/01-技术决策书.md)）。
M0 阶段制造行业模板尚未完整建设（M1 上线，参考 ISA-95 + IATF 16949 + ISO 9001），
本测试集是 V15 早期捕获的 5 份典型样本。

配套：[backend/templates/manufacturing/domain-keywords.yaml](../../backend/templates/manufacturing/domain-keywords.yaml)（M0 占位）

## 文件清单

| # | 文件 | 类别 | 主题域（参考决策书 §7.1）| 测试关注点 |
|---|---|---|---|---|
| 1 | [ISO9001质量管理手册.txt](./ISO9001质量管理手册.txt) | 质量体系 | manufacturing/quality | 长文档 / 章节多 / 质量管理体系核心 |
| 2 | [供应商评审管理规定.txt](./供应商评审管理规定.txt) | 供应链 | manufacturing/supply | 流程类规章 + 评审表格 |
| 3 | [注塑车间作业指导书.txt](./注塑车间作业指导书.txt) | 工艺 SOP | manufacturing/process/sop | 工艺步骤 + 参数标准 |
| 4 | [生产安全操作规程.txt](./生产安全操作规程.txt) | 安全 | manufacturing/safety + process/sop | 安全规范 + 操作步骤混合 |
| 5 | [设备预防性维护计划.txt](./设备预防性维护计划.txt) | 设备 | manufacturing/equipment/maintenance | 时间表 + 部件清单 + 检查项 |

## 推荐测试组合

| 测试目标 | 验证关注点 |
|---|---|
| W3 切块策略分流 | 5 份覆盖 SOP / 制度 / 技术规范三种文档类型，`CHUNK_STRATEGY` 自适应 |
| W2 跨行业冲突识别 | 与 [能源 v12-revised/](../energy/README.md#v12-revised) 混合输入，验证模板隔离（不会把制造文档归到 energy/* 域）|
| 块① 行业识别准确率 | 仅传 5 份输入给智能体，期望识别为 manufacturing |
| 决策书 §7.4 模板加载 | 加载 [manufacturing/domain-keywords.yaml](../../backend/templates/manufacturing/domain-keywords.yaml) 后，所有 5 份应分到 manufacturing/* 域 |

## 行业骨架（决策书 §7.1 参考）

KAP 制造业 L1 主树骨架（M1 完整建设，本测试集对照之）：

```
研发体系 / 工艺与制造 / 质量与检验 / 供应链 / 设备与维保 / 安全环保 / 综合管理
```

对应 ISA-95 + IATF 16949 + ISO 9001 + ISO 14224。

## 已知局限

- 5 份样本不足以覆盖**装备制造 / 流程制造 / 离散制造**全部子方向
- M1 制造完整模板包就绪后，应**扩充至 30+ 份**（覆盖 BOM / 工艺路线 / 质量缺陷 / 试验等）
- 当前缺研发文档（设计图纸 / 试验报告 / 专利）— PoC 阶段需向客户索取

## 期望规则覆盖

[manufacturing/domain-keywords.yaml](../../backend/templates/manufacturing/domain-keywords.yaml)（M0 占位）应能命中：

- [ISO9001质量管理手册](./ISO9001质量管理手册.txt) → manufacturing/quality（含"质量"关键词）
- [供应商评审管理规定](./供应商评审管理规定.txt) → manufacturing/supply（"供应商"）
- [注塑车间作业指导书](./注塑车间作业指导书.txt) → manufacturing/process/sop（"作业指导"+"工艺"）
- [生产安全操作规程](./生产安全操作规程.txt) → manufacturing/process/sop（"操作规程"）
- [设备预防性维护计划](./设备预防性维护计划.txt) → manufacturing/equipment/maintenance（"预防性维护"）

---

## 图谱锚点（Obsidian 反向关联）

**上行**：[← 测试样例总入口](../README.md) → [← 项目首页](../../README.md) → [Claude 内存](../../CLAUDE.md)

**KAP 主线**：[决策书 §7.1](../../docs/01-技术决策书.md) · [PRD](../../docs/02-产品需求PRD.md) · [M0 技改地图](../../docs/M0-tech-debt.md)

**配套模板**：[manufacturing/domain-keywords.yaml](../../backend/templates/manufacturing/domain-keywords.yaml)

**横向参考**：[能源样例](../energy/README.md) · [金融样例](../finance/README.md) · [IT 样例](../it/README.md)
