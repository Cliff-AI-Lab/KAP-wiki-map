# ISS-Job ↔ KAP 调度集成配置

> M13 #4 · [决策书 §10.5](../01-技术决策书.md) ISS 集成 · ISS 零侵入

KAP 不接 Quartz 框架（feedback memory · 轻量化 + ISS 零侵入），仅暴露 HTTP 端点供 ISS-Job 调用。本文档说明 ISS-Job 侧应如何配置 cron job。

## 协调端点

```
GET /api/v1/iss-job/cron-recommendations
```

返回当前 KAP 状态摘要 + 推荐的 cron 配置。ISS-Job 推荐 5 分钟拉一次，根据返回的 `interval_seconds` 动态调整下游 job 频率。

**返回示例**：

```json
{
  "kap_status": {
    "active_observations": 2,
    "alerting_observations": 0,
    "total_observations": 5,
    "decisions_total": 142,
    "queries_total": 3580,
    "ground_truth_count": 12
  },
  "recommended_jobs": [
    {
      "name": "tick_all_observations",
      "endpoint": "/api/v1/rebuild/observations/tick-all",
      "method": "POST",
      "body": {},
      "interval_seconds": 300,
      "reason": "alerting=0, active=2; 按启发式推荐 300s"
    },
    {
      "name": "eval_all_recall",
      "endpoint": "/api/v1/observability/recall-eval/eval-all",
      "method": "POST",
      "body": {"k": 5, "version": ""},
      "interval_seconds": 3600,
      "reason": "ground_truth=12; 推荐 3600s"
    }
  ],
  "version": "1",
  "notes": "ISS-Job 调用 KAP HTTP 端点时需带 SME role JWT；失败重试建议指数退避"
}
```

## 间隔启发式

`tick_all_observations` 由 `recommended_jobs[0].interval_seconds` 控制：

| KAP 状态                       | 推荐间隔  | 含义                      |
|:-------------------------------|:---------:|:-------------------------|
| `alerting_observations ≥ 1`    | 60 s     | 告警时密集监控           |
| `active_observations ≥ 1`      | 300 s    | 默认 5 分钟              |
| 都没有                          | 1800 s   | 半小时一次轻探活         |

`eval_all_recall` 由 `recommended_jobs[1].interval_seconds` 控制：

| KAP 状态                  | 推荐间隔   |
|:--------------------------|:----------:|
| `ground_truth_count > 0`  | 3600 s     |
| `ground_truth_count == 0` | 10800 s    |

## ISS-Job (Quartz) 端配置示例

### 1. 协调 job — 拉 KAP 推荐配置

```xml
<!-- iss-job-quartz.xml -->
<job>
  <name>kap-cron-coordinator</name>
  <group>kap-integration</group>
  <description>每 5 分钟拉 KAP 推荐配置，更新下游 cron</description>
  <job-class>com.iss.kap.CronCoordinatorJob</job-class>
  <durability>true</durability>
</job>

<trigger>
  <cron>
    <name>kap-cron-coordinator-trigger</name>
    <job-name>kap-cron-coordinator</job-name>
    <cron-expression>0 */5 * * * ?</cron-expression>
  </cron>
</trigger>
```

### 2. tick-all observations — 动态间隔 job

```xml
<job>
  <name>kap-tick-all</name>
  <group>kap-integration</group>
  <job-class>com.iss.kap.HttpInvokeJob</job-class>
  <job-data-map>
    <entry>
      <key>endpoint</key>
      <value>${kap.base.url}/api/v1/rebuild/observations/tick-all</value>
    </entry>
    <entry>
      <key>method</key>
      <value>POST</value>
    </entry>
    <entry>
      <key>auth.token.source</key>
      <value>${kap.sme.jwt}</value>
    </entry>
  </job-data-map>
</job>
```

`CronCoordinatorJob` 拉到推荐间隔后用 `Scheduler.rescheduleJob()` 调整 `kap-tick-all` 的 trigger。

### 3. eval-all recall — 同上模式

```xml
<job>
  <name>kap-eval-all</name>
  <group>kap-integration</group>
  <job-class>com.iss.kap.HttpInvokeJob</job-class>
  <job-data-map>
    <entry>
      <key>endpoint</key>
      <value>${kap.base.url}/api/v1/observability/recall-eval/eval-all</value>
    </entry>
    <entry>
      <key>method</key>
      <value>POST</value>
    </entry>
    <entry>
      <key>body</key>
      <value>{"k":5,"version":""}</value>
    </entry>
  </job-data-map>
</job>
```

## 鉴权

ISS-Job 调用 KAP POST 端点时 **必须** 携带 SME role JWT：

```
Authorization: Bearer <jwt>
```

JWT 中 claims 需含 `roles: ["SME"]`（决策书 §10.4 RBAC）。建议用 ISS 内置的服务账号 `kap-iss-job@iss.local`，预置 SME 角色。

## 错误处理

- HTTP 4xx → 不重试（配置错误，写日志）
- HTTP 5xx → 指数退避重试（建议 3 次：5s / 20s / 60s）
- 网络超时 → 同 5xx
- 协调端点 `cron-recommendations` 自身 5xx → 用上次缓存的 interval（容错）

## 监控

ISS-Job 端建议把 `kap_status.alerting_observations > 0` 的事件转发给运维群（钉钉 / 企微 webhook），便于 SME 快速响应观察期告警。

## 月度分区维护（M14 #3 加入）

`decision_events` / `query_events` 改为 PG 月度分区后，需每月初提前创建下月分区。建议 ISS-Job 配一个 **每月 1 号** 触发的运维 job：

```python
# 通过 KAP 提供的工具函数（运维脚本调用）
from datetime import date
from packages.observability import ensure_partition_for_month
from packages.common.config import settings
import psycopg

async def monthly_partition_maintenance():
    today = date.today()
    # 提前 2 个月创建分区（缓冲）
    targets = [
        (today.year, today.month),
        (today.year + (today.month // 12), (today.month % 12) + 1),
    ]
    conn = await psycopg.AsyncConnection.connect(settings.postgres_dsn)
    try:
        for year, month in targets:
            await ensure_partition_for_month(
                conn, "decision_events", year, month,
            )
            await ensure_partition_for_month(
                conn, "query_events", year, month,
            )
    finally:
        await conn.close()
```

ISS-Job Quartz cron 表达式：`0 0 2 1 * ?`（每月 1 号凌晨 2 点）

## 与 KAP 内置 cron 的关系

KAP 自身**不内置** cron 调度器（轻量化 + ISS 零侵入）。所有定时触发都依赖 ISS-Job 通过本文档配置的 HTTP 调用。

**例外**：单元测试 / 本地调试可用 `curl` 手动触发：

```bash
# 手动 tick 一次所有观察期
curl -X POST http://localhost:8001/api/v1/rebuild/observations/tick-all \
  -H "Authorization: Bearer $KAP_SME_JWT"

# 手动跑一次召回评估
curl -X POST http://localhost:8001/api/v1/observability/recall-eval/eval-all \
  -H "Authorization: Bearer $KAP_SME_JWT" \
  -H "Content-Type: application/json" \
  -d '{"k":5,"version":""}'
```
