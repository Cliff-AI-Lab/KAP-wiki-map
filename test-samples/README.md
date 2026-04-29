---
title: KAP 测试样例集 · 总入口
type: kap-test-samples-root
parent: "[[../README]]"
industries: [energy, manufacturing, finance, it]
total-files: 48
related:
  - "[[../docs/01-技术决策书]]"
  - "[[../docs/02-产品需求PRD]]"
  - "[[../docs/_refs-index]]"
status: ready-for-test
---

# KAP 测试样例集 · 总入口

← 返回项目首页：[`../README.md`](../README.md) · [`../CLAUDE.md`](../CLAUDE.md)
↑ 上游来源：[`../_refs/wiki-map/bookworm-agent/`](../_refs/wiki-map/bookworm-agent/)（已修复 GBK 乱码）
→ 索引文档：[`../docs/_refs-index.md`](../docs/_refs-index.md)

## 用途

本目录是 KAP 项目**自有的、可直接执行的、按行业组织的测试样例集**，
共 4 个行业 / **48 份文档**。来源于 Wiki-map V15 的真实测试数据集（已修复编码问题）。

KAP 各阶段测试时直接从这里取数据，**不再依赖 `_refs/`**（_refs 在 .gitignore，可被删除）。

## 行业分布

| 行业 | 文件数 | 入口 | 主要用于测试 |
|---|---|---|---|
| **能源**（含电力 / 油气 / 化工）| 33 | [`energy/README.md`](./energy/README.md) | 决策书 §7.2 能源 L1 主树骨架 / 制造能源优先验证 |
| **制造**（含 ISO9001 / 注塑 / 装备）| 5 | [`manufacturing/README.md`](./manufacturing/README.md) | 决策书 §7.1 制造 L1 主树骨架 / M1 制造模板验证 |
| **金融**（含信贷 / 反洗钱 / 理财）| 5 | [`finance/README.md`](./finance/README.md) | 第二批扩展（决策书 §1.3）GA 后金融模板验证 |
| **IT**（含微服务 / 敏捷 / DBA）| 5 | [`it/README.md`](./it/README.md) | IT 内部知识管理类客户场景 |

能源细分三个版本（保留版本演化痕迹，便于回归对比）：

| 子集 | 文件数 | 时期 | 特点 |
|---|---|---|---|
| `energy/v7-baseline/` | 18 | V7 早期 | 18 份混合 txt/md/docx，覆盖安全/生产/环保/应急/采购全域 |
| `energy/v12-revised/` | 10 | V12 重制 | 10 份 txt+md，按 10 大主题精简后的标准基线 |
| `energy/v15-extra/` | 5 | V15 增补 | 5 份多格式（含 .pdf / .html / .docx）真实场景样本 |

## 测试场景索引

不同测试任务用不同子集：

| 测试场景 | 推荐使用 | 验证目标 |
|---|---|---|
| W1 多模态解析 | `energy/v15-extra/`（含 pdf/html/docx）| ISS-Knowledge-Parser 多格式覆盖 |
| W2 自动归类 | `energy/v12-revised/`（10 份精简，对应能源 53 域）| 决策书 §7.4 行业模板 + `domain_inference.infer_domain_id` |
| W3 切块策略 | `manufacturing/`（5 份，含表格 / 步骤 / 规则混合）| 不同文档类型分流（SOP / 规章 / 技术）|
| W4 实体抽取 + Critic | `energy/v7-baseline/`（18 份，含跨文档相同实体）| Refiner V8 关系提取 + 6 维质疑 |
| W5 入库双写 | 全部 48 份 | Milvus 双向量 + Neo4j 持久化端到端 |
| W6 召回 / 命中率 | `energy/v12-revised/` + 配套 QA 集（待补）| HybridScorer 三路召回 |
| 块① 行业识别 | `manufacturing/` + `finance/` + `it/` 混合 | 智能体识别能力（决策书 §4.2）|
| 跨行业分类 | 全部 48 份打散 | 多行业模板共存场景 |
| 大批量蒸馏压测 | 全部 48 份 × 10 倍重复 | 异步 pipeline `arun_pipeline` 并发性能 |

## 与项目主线的关联

- 决策书 §7（行业标准锚定）：`energy/` 对应 §7.2，`manufacturing/` 对应 §7.1
- PRD §10.5 关键依赖："行业模板就绪：M0 启动前完成能源模板验证（V15 已有 53 域可用）"——本目录提供能源样本
- M0-tech-debt 坑 4b：`backend/templates/<industry>/domain-keywords.yaml` 用于
  分类这里的样本到具体 `domain_id`
- M0-tech-debt 坑 6：embedding provider 可用本目录的真实文档跑端到端烟测

## 编辑约束

- ✅ 可在本目录新增样本（按行业放对应子目录），加进 manifest 即可
- ✅ 可重命名文件，但请同步更新对应 `<industry>/README.md` 的清单
- ❌ 不要修改原文档内容（会污染回归基线，导致跨版本对比失效）
- ❌ 不要把生产 / 客户的真实文档放这里（会泄露，应放 `.uploads/` 或受控目录）

## 重新生成

如本目录被误删 / 编码坏掉，重跑：

```bash
python scripts/copy_test_samples.py
```

依赖原始 ZIP `E:/Obsidian/知识PPL/raw/Wiki-map/bookworm-agent-v15.zip`
（已通过 [`scripts/fix_refs_mojibake.py`](../scripts/fix_refs_mojibake.py) 用 `metadata_encoding='gbk'` 修复编码）。
