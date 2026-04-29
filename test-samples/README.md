---
title: KAP 测试样例集 · 总入口
type: kap-test-samples-root
industries: [energy, manufacturing, finance, it]
total-files: 48
---

# KAP 测试样例集 · 总入口（48 文档 / 4 行业）

> 导航：[← 项目首页](../README.md) · [决策书](../docs/01-技术决策书.md) · [PRD](../docs/02-产品需求PRD.md) · [M0 技改地图](../docs/M0-tech-debt.md) · [上游参考索引](../docs/_refs-index.md) · [Claude 项目内存](../CLAUDE.md)

## 用途

本目录是 KAP 项目**自有的、可直接执行的、按行业组织的测试样例集**，
共 4 个行业 / **48 份文档**。来源于 Wiki-map V15 的真实测试数据集（已修复 GBK 编码问题）。

KAP 各阶段测试时直接从这里取数据，**不再依赖 `_refs/`**（_refs 在 .gitignore，可被删除）。

## 行业入口

每个行业 README 含完整文件清单（每文件一条相对链接）+ 推荐测试场景。

- [能源行业测试样例（33 文件）](./energy/README.md)
  - V7 早期完整集（18 文件）：[能源 README → v7-baseline 段](./energy/README.md#v7-baseline)
  - V12 精简标准基线（10 文件）：[能源 README → v12-revised 段](./energy/README.md#v12-revised)
  - V15 增补真实场景（5 文件，多格式）：[能源 README → v15-extra 段](./energy/README.md#v15-extra)
- [制造行业测试样例（5 文件）](./manufacturing/README.md)
- [金融行业测试样例（5 文件）](./finance/README.md)
- [IT 行业测试样例（5 文件）](./it/README.md)

## 测试场景索引

不同测试任务用不同子集：

| 测试场景 | 推荐使用 | 验证目标 |
|---|---|---|
| W1 多模态解析 | [energy/v15-extra/](./energy/README.md#v15-extra) (含 pdf/html/docx) | ISS-Knowledge-Parser 多格式覆盖 |
| W2 自动归类 | [energy/v12-revised/](./energy/README.md#v12-revised) (10 份精简) | 决策书 §7.4 行业模板 + `domain_inference.infer_domain_id` |
| W3 切块策略 | [manufacturing/](./manufacturing/README.md) (5 类型混合) | 不同文档类型分流（SOP / 规章 / 技术）|
| W4 实体抽取 + Critic | [energy/v7-baseline/](./energy/README.md#v7-baseline) (18 份跨文档同实体) | Refiner V8 关系提取 + 6 维质疑 |
| W5 入库双写 | 全部 48 份 | Milvus 双向量 + Neo4j 持久化端到端 |
| W6 召回 / 命中率 | [energy/v12-revised/](./energy/README.md#v12-revised) + 配套 QA 集 | HybridScorer 三路召回 |
| 块① 行业识别 | [manufacturing/](./manufacturing/README.md) + [finance/](./finance/README.md) + [it/](./it/README.md) 混合 | 智能体识别能力（决策书 §4.2）|
| 跨行业冲突 | 全部 48 份打散 | 多行业模板共存场景 |
| 大批量蒸馏压测 | 全部 48 份 × 10 倍重复 | 异步 pipeline `arun_pipeline` 并发性能 |
| dogfood 自管理 | KAP 自身 [docs/](../docs/) | 用 KAP 管理 KAP 项目文档 |

## 与项目主线的关联

- [决策书 §7](../docs/01-技术决策书.md) 行业标准锚定 —— `energy/` 对应 §7.2，`manufacturing/` 对应 §7.1
- [PRD §10.5](../docs/02-产品需求PRD.md) 关键依赖："行业模板就绪：M0 启动前完成能源模板验证"——本目录提供能源样本
- [M0-tech-debt 坑 4b](../docs/M0-tech-debt.md) ：[backend/templates/<industry>/domain-keywords.yaml](../backend/templates/) 用于
  分类这里的样本到具体 `domain_id`
- [M0-tech-debt 坑 6](../docs/M0-tech-debt.md) ：embedding provider 可用本目录的真实文档跑端到端烟测
- [上游参考索引](../docs/_refs-index.md) —— Wiki-map V15 / ISS 完整文档导航

## 目录结构

```
test-samples/
├── README.md                    总入口（本文件）
├── energy/
│   ├── README.md                能源行业 README（含三个版本子集）
│   ├── v7-baseline/   18 文件   V7 早期完整集
│   ├── v12-revised/   10 文件   V12 精简标准基线
│   └── v15-extra/      5 文件   V15 增补真实场景（多格式）
├── manufacturing/      5 + README
├── finance/            5 + README
└── it/                 5 + README
```

## 编辑约束

- ✅ 可在本目录新增样本（按行业放对应子目录），加进对应 README 清单即可
- ✅ 可重命名文件，但请同步更新对应 `<industry>/README.md` 清单
- ❌ 不要修改原文档内容（会污染回归基线，跨版本对比失效）
- ❌ 不要把生产 / 客户的真实文档放这里

## 重新生成

如本目录被误删 / 编码坏掉，重跑：

```bash
python scripts/copy_test_samples.py
```

依赖原始 ZIP（已通过 [`scripts/fix_refs_mojibake.py`](../scripts/fix_refs_mojibake.py) 用 `metadata_encoding='gbk'` 修复编码）。

---

## 图谱锚点（Obsidian 反向关联）

本节集中所有上下游链接，方便 Obsidian 图谱建立反向边：

**主项目入口**：[../README.md](../README.md) · [../CLAUDE.md](../CLAUDE.md)

**KAP 主线文档**：[决策书](../docs/01-技术决策书.md) · [PRD](../docs/02-产品需求PRD.md) · [M0 技改地图](../docs/M0-tech-debt.md) · [异步化迁移地图](../docs/M0-tech-debt-async-plan.md) · [上游参考索引](../docs/_refs-index.md)

**4 个行业 README**：[能源](./energy/README.md) · [制造](./manufacturing/README.md) · [金融](./finance/README.md) · [IT](./it/README.md)

**配套行业模板（backend/templates/）**：[_default](../backend/templates/_default/) · [energy](../backend/templates/energy/) · [manufacturing](../backend/templates/manufacturing/)

**生成脚本**：[copy_test_samples.py](../scripts/copy_test_samples.py) · [fix_refs_mojibake.py](../scripts/fix_refs_mojibake.py)
