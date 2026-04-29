---
title: KAP 进度快照（按里程碑）
type: kap-progress-index
tags: [kap, index]
---

> 进入最新里程碑：[**M4 重抽影子库**](M4-snapshot.md)
>
> 设计蓝本（中心节点）：[**01-技术决策书**](../01-技术决策书.md)

# KAP 进度（线性进程）

[M0](M0-snapshot.md) → [M1](M1-snapshot.md) → [M2](M2-snapshot.md) → [M3](M3-snapshot.md) → [M4](M4-snapshot.md) → M5（待启动）

---

## Obsidian 图谱配色建议

打开 obsidian → Graph view → 右下角 ⚙️ Filters → Color groups，按路径设：

| 节点 | 路径模式 | 建议颜色 |
|:---|:---|:---:|
| KAP 新作 | `path:docs/ OR path:backend/ OR path:frontend/` | 蓝色 |
| KAP 进程链 | `path:docs/progress/` | 绿色（线性递增） |
| 设计蓝本 | `01-技术决策书 OR 02-产品需求` | 黄色（中心） |
| ISS 参考项目 | `path:_refs/iss-kb/` | 红色 |
| Wiki-map V15 参考 | `path:_refs/wiki-map/` | 橙色 |

每份 M{N}-snapshot.md 只链：上一份 / 下一份 / 决策书具体章节 / 自己改的代码 + 测试。
**不引用 README**，避免本文件辐射中心化。
