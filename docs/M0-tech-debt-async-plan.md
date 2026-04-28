# KAP 坑 1 LLM 全链路异步化 · 迁移地图

> **文档版本**：v1.0
> **撰写日期**：2026-04-28
> **作者**：claude-opus-4-7（via kap-delegate plan diagnosis）+ KAP 项目组复核
> **文档定位**：M0-tech-debt §2 坑 1 + 额外坑 A/D/F 的代码级实施计划
> **数据依据**：基于 backend/ 实际代码（llm_client.py / pipeline.py / agents/* / config.py）的只读分析

## 0. 与其他文档关系

```
M0-tech-debt.md §2 坑 1 + §3 坑 A/D/F（高层）
        ↓
本文档（5 批次落地 + 估时 16h）
        ↓
逐批 PR / commit
```

---

## 1. 调用栈摸底

### 1.1 当前同步调用栈全貌

| 层级 | 文件 | 关键符号 | 同步性质 |
|---|---|---|---|
| L4 HTTP I/O | `packages/distillation/llm_client.py` | `httpx.Client(verify=False)` | **同步**（决策书 §13 禁项） |
| L4 SDK 客户端 | 同上 | `OpenAI(...)` / `Anthropic(...)` | 同步 SDK |
| L3 LLM 入口 | 同上 | `call_llm(...)` | **`def` + tenacity 同步重试** |
| L3 JSON 包装 | 同上 | `call_llm_json(...)` | 同步 |
| L2 Agent | `agents/{librarian,conflict_auditor,judge,refiner}.py` | `run_*(...)` | 全部同步 |
| L1 Orchestrator | `pipeline.py` | `run_pipeline(...)` | **同步 + `ThreadPoolExecutor`** |
| L1 Step wrappers | 同上 | `_run_*_safe(...)` | 同步包装 |
| L0 API endpoint | （上下文未提供） | — | **待人工确认** |

### 1.2 三类阻塞模式

**A. 直接 `def` 可平移为 `async def`**：4 个 agent 的 `run_*` + `call_llm` / `call_llm_json`

**B. 显式线程池用法**（`pipeline.py`）：4 个 step（Librarian/Auditor/Judge/Refiner）都是 `ThreadPoolExecutor.submit(_run_*_safe, ...)` + `as_completed` —— 决策书 §10.3 明确反对

**C. 同步函数被 async 上下文调用的潜在阻塞点**：
- `_get_openai()` / `_get_anthropic()` 模块级懒加载单例（一次性 IO，可保留）
- `tenacity.retry` 同步装饰器（必须切 `AsyncRetrying`）
- `lru_cache`（命中即返回，未命中触发同步文件 IO，量小可接受）

### 1.3 mock 路径的异步含义

- `_mock_*` 全部纯 CPU，**无需变 async**
- 但 `call_llm` 的 async 版返回 mock 时需保持调用契约一致

---

## 2. 迁移分批方案（自下而上，总 16h）

### 批 0 · settings + 配置位（最小，零风险）— **1.5h**

**修改文件**：`backend/packages/common/config.py`

**新增字段**：
- `llm_verify_ssl: bool`（坑 D，env `KAP_LLM_VERIFY_SSL`）
- `llm_http_timeout: float`（统一 timeout，当前 openai=60 / anthropic=10 不一致）
- `llm_max_concurrency: int`（async 化后取代 `pipeline_max_workers` 信号量语义）
- `allow_mock_llm: bool`（坑 F，env `KAP_ALLOW_MOCK_LLM`，sandbox/prod 强制 False）
- `kap_environment: str`（如未存在则补，dev/sandbox/prod 三态）

**关键风险**：`model_post_init` 中 verify_ssl + allow_mock_llm 强制规则需放同钩子，注意覆盖顺序。

**回归测试**：`tests/test_settings.py` 加三环境矩阵 case。

---

### 批 1 · llm_client 双轨（保留 sync wrapper + 新增 async）— **4h**

**修改文件**：`backend/packages/distillation/llm_client.py`

**改造形态**：
- 模块级新增：`_async_openai_client` / `_async_anthropic_client`（懒加载，`httpx.AsyncClient(verify=settings.llm_verify_ssl)`）
- 新增 `async def acall_llm(...)`：tenacity `AsyncRetrying` 或 retry async 形式
- 新增 `async def acall_llm_json(...)`：复用 `_extract_json`，包装 JsonDecodeError → LLMCallError
- 旧 `call_llm` / `call_llm_json` **保留**（M0 兼容期）

**关键风险**：
1. tenacity AsyncRetrying 兼容（≥6.2）
2. mock fallback 静默冲突（坑 F 处理）
3. JSON 解析异常包装签名一致
4. AsyncAnthropic vs Anthropic
5. timeout 不一致需统一
6. AsyncClient 不能跨 event loop 复用

**回归测试**：`tests/distillation/test_llm_client.py` 双轨 case（mock + respx）。

---

### 批 2 · agents 改 async（4 个 agent 文件）— **3h**

**修改文件**：`agents/{librarian,conflict_auditor,judge,refiner}.py`

**改造形态**：
- 4 个 `run_*` → `async def`，内部 `await acall_llm_json(...)`
- 纯函数（`_build_documents_text` / `_validate_and_fix_relations` / `_fuzzy_match_entity` / `_build_index_text`）保持同步

**关键风险**：
1. `decide()` / `load_thresholds()` 是同步 IO（YAML），async 函数内同步调用合法但量大需 `asyncio.to_thread`
2. **批 2 单独合入会导致 pipeline.py 编译错** —— 必须批 2 + 批 3 同 PR，或保留 sync 兼容 wrapper
3. Conflict Auditor 早返回 `if len(docs) < 2: return AuditResult(...)` 不调 LLM，async 化保持类型

**回归测试**：`tests/distillation/agents/test_*.py` 加 `@pytest.mark.asyncio`，mock 用 `AsyncMock`。

---

### 批 3 · pipeline orchestrator 改 asyncio.gather — **4h**

**修改文件**：`pipeline.py`

**改造形态**：
- `run_pipeline` → `async def`
- 4 个 `_run_*_safe` wrapper → `async def`（异常吞 + 三元组返回契约必须保持）
- 4 个 step 的 `ThreadPoolExecutor` + `as_completed` → `asyncio.gather(*coros)`
- 并发度：`asyncio.Semaphore(settings.llm_max_concurrency)` 包装每个 wrapper

**关键风险**：
1. **Auditor 的 `futures[future]` 反查映射** → asyncio.gather 顺序对应，重构循环易出 bug
2. `return_exceptions=False` 选择（wrapper 已吞异常）
3. Step 间顺序依赖必须 `await` 串联
4. **Judge 失败降级 KEEP** 兜底逻辑必须保留
5. 日志结构化字段不丢
6. noise_filter 同步规则保持同步调用

**回归测试**：`tests/distillation/test_pipeline.py` 用 `pytest-asyncio` + `asyncio_mode=auto`。

**建议拆 4 个 commit**（每 step 一个，单 step 故障可只回滚一个 commit）。

---

### 批 4 · API 层 endpoint 改 async — **1.5h**

**修改文件**：上下文未提供，**需人工补全**：
- 推测 `backend/apps/*/api/distillation.py` 或 `backend/services/*/routes/*.py`
- 推测 handler `POST /distillation/run` 或 `POST /pipeline/run`

**关键风险**：
- `def` handler + async `run_pipeline` → `coroutine never awaited`
- BackgroundTasks / Celery 路径需另行评估

---

### 批 5 · 同步 wrapper 删除 — **0h（M0 不做）**

M0 保留 `call_llm` / `call_llm_json` 同步版本兼容；M1 待全部调用方切 async 后才删。

---

### 估时合计

| 批次 | 估时（人时 P50）|
|---|---|
| 批 0 settings | 1.5h |
| 批 1 llm_client 双轨 | 4.0h |
| 批 2 agents async | 3.0h |
| 批 3 pipeline asyncio.gather | 4.0h |
| 批 4 API endpoint | 1.5h |
| **小计** | **14h** |
| tenacity / asyncio.gather 调试缓冲 | 2h |
| **总计** | **16h** |

---

## 3. 顺手坑（A/D/F）的接入位置

### 3.1 坑 D · verify_ssl 设置开关

**当前位置**：`llm_client.py::_get_openai()` 内 `httpx.Client(verify=False)` 硬编码。

**接入方案**：
- 字段：`Settings.llm_verify_ssl: bool`，env `KAP_LLM_VERIFY_SSL`
- `model_post_init` 三环境强制：dev 允许 False；sandbox/prod 强制 True，无视用户输入
- `_get_openai` / `_get_anthropic` / async 版本都读 `settings.llm_verify_ssl`

### 3.2 坑 F · mock fallback env gate

**当前 mock 触发**（`call_llm` 内）：
1. `provider == "mock"`（显式）
2. `not _has_valid_api_key()` → 隐式回落
3. `except Exception` → **静默回落 mock**（决策书 §10.3 禁项）

**接入方案**：
- 字段：`Settings.allow_mock_llm: bool = False`，env `KAP_ALLOW_MOCK_LLM`
- 三处 mock 触发都加 gate（False 时抛 LLMCallError）
- `except Exception` 分支彻底删除 mock fallback，让异常上抛
- `model_post_init` 中 sandbox/prod 强制 False

### 3.3 坑 A · mock 业务逻辑剥离

**问题文件**：所有 `_mock_*` 函数（librarian/auditor/judge/refiner/router）内嵌业务规则。

**M0 范围内最小集**（不做完整剥离）：
- 在 `_mock_judge` / `_mock_refiner` / `_mock_router` 头部加 `# DEPRECATED: business rules to be moved to templates/`
- 批 2 改 async 时**保持函数签名不变**，给后续替换留接口

**完整剥离（拆出 M0 独立 ticket，6-8h）**：
- 文档类型推断 → `classifiers/doc_type_classifier.py`
- 决策业务规则 → 已有 `judge_decision.py`
- 能源关系模板 → `templates/energy/relation-templates.yaml`
- 路由规则 → `templates/<industry>/routing-rules.yaml`

---

## 4. 测试策略

### 4.1 fixture 迁移

- 顶层 `conftest.py` 加 `pytest_plugins = ["pytest_asyncio"]`
- `pyproject.toml` 设 `asyncio_mode = "auto"`（已存在，确认即可）
- 现有 sync fixture 保留；新增 async fixture 按需

### 4.2 mock LLM 异步化

- `monkeypatch.setattr("...call_llm_json", lambda ...)` → 补 `acall_llm_json` mock
- 推荐 `respx` 库拦截 httpx.AsyncClient

### 4.3 新增 async 集成烟测

- `tests/integration/test_pipeline_async.py`：5 篇文档 mock 模式跑全 pipeline，验证并发收益
- `tests/integration/test_llm_real_api.py`（可选）：sandbox 真实调用，验证 verify_ssl + AsyncClient

---

## 5. 风险清单 + 回滚预案

### 5.1 最容易出 bug 的点（按概率排序）

1. **tenacity AsyncRetrying 重试不生效**（旧版本协程对象当返回值）
2. **Anthropic SDK async 兼容**（`AsyncAnthropic` vs `Anthropic`）
3. **pipeline Auditor `futures[future]` 反查丢失** → audit_results 错位
4. **mock fallback 删除后 sandbox 测试挂掉**（5xx 显形）
5. **httpx.AsyncClient 跨 event loop 复用**（`RuntimeError: Event loop is closed`）
6. lru_cache 跨 async 调用（当前 (org_id, project_id) 安全）
7. JsonDecodeError `from e` 链式
8. timeout 不一致统一后行为变更

### 5.2 分批回滚预案

| 批次 | 回滚方式 | 影响 |
|---|---|---|
| 批 0 | 单文件回滚，新字段未读取则零影响 | 低 |
| 批 1 | 双轨保护，sync `call_llm` 仍可用 | 低 |
| 批 2 | 必须批 2+3 同 PR 或 sync 兼容 wrapper | 中 |
| 批 3 | 拆 4 个 commit，单 step 可独立回滚 | 高 |
| 批 4 | 临时 `def f(): return asyncio.run(async_f())` 救火 | 中 |

### 5.3 灰度策略

- 批 1 合入 → dev mock 24h 烟测
- 批 2+3 合入 → sandbox 真 API 100 篇批量测，对比 sync 版指标
- 批 4 合入 → prod 灰度 5%

---

## 6. 建议人工验证的点（开工前）

1. **API endpoint 真实位置**：`grep -r "run_pipeline" backend/apps backend/services`
2. **`Settings.kap_environment` 是否已存在**
3. **tenacity 版本 ≥6.2**
4. **openai ≥1.0、anthropic ≥0.18**
5. **`pipeline_max_workers` 当前默认值**
6. **`load_skills()` / `load_thresholds()` / `infer_domain_id()` 同步 IO 是否成为热点**（profile 验证）
7. **是否有 Celery / Background tasks 调用 pipeline**
8. **`pyproject.toml` 中 `asyncio_mode` 当前值**
9. **mock 函数是否有真实业务依赖方**（demo / PoC）
10. **`_extract_json` Anthropic 格式兼容性**

---

## 附录 · 文档变更记录

| 版本 | 日期 | 变更说明 |
|---|---|---|
| v1.0 | 2026-04-28 | 首版。Opus 4.7 via kap-delegate 分析产出，KAP 项目组复核 |
