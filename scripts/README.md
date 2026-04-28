# scripts · KAP 项目脚本工具集

## kap-delegate · 委派代码工作给睿动 + Claude

把繁重的代码工作（多文件重构、测试循环修复、代码调研）委派给睿动网关上的 Claude（Sonnet/Haiku/Opus），保留 git 安全壳与人工审核环节。

### 设计动机

原 [`codex-delegate` skill](https://github.com/Cliff-AI-Lab/codex-delegate) 走 OpenAI Codex CLI，但：

- Codex CLI 0.118 已强制 Responses API（`/v1/responses`）
- 睿动网关只提供标准 Chat Completions API（`/v1/chat/completions`）
- CRS 中继是 ChatGPT 账号绑定的，**显式拒绝 claude-* 模型**

本脚本是 codex-delegate 工作流在**睿动 + Claude Sonnet** 上的等价实现。

### 一次性配置

脚本支持**双 backend**：

| Backend | 端点 | 优势 | 适用 |
|---|---|---|---|
| `anthropic`（默认）| CRS Anthropic API | **支持 Opus 全系列**（4-1 / 4-5 / 4-6 / 4-7 / 4-6-thinking）| 首选，规划任务必须 |
| `openai` | 睿动 OpenAI 兼容 | 模型选择多（含 Qwen / GLM / GPT 等）| Sonnet/Haiku 备选 |

**Anthropic backend（默认）**：

```bash
# Windows
setx ANTHROPIC_AUTH_TOKEN cr_...
setx ANTHROPIC_BASE_URL http://18.141.210.162:3000/api    # 可选，脚本有内置默认

# Linux / macOS（写入 ~/.bashrc）
export ANTHROPIC_AUTH_TOKEN=cr_...
export ANTHROPIC_BASE_URL=http://18.141.210.162:3000/api  # 可选
```

**OpenAI backend（备选，需 --backend openai）**：

```bash
setx IRUIDONG_API_KEY sk-...     # Windows
export IRUIDONG_API_KEY=sk-...   # Linux/macOS
```

> 原 `~/.codex/config.toml` 不动。kap-delegate 完全独立运行。

### 团队约定 · 任务 → 模型路由

通过 `--task-type` 自动选模型，避免每次手填：

| 任务类型 | 默认模型 | 适用 |
|---|---|---|
| `--task-type plan` | **claude-opus-4-7** | 架构设计、PRD、技术方案、调研规划 |
| `--task-type dev` _(默认)_ | claude-sonnet-4-6 | 多文件重构、实现代码、测试修复 |
| `--task-type light` | claude-haiku-4-5-20251001 | 重命名、格式化、轻量批改、文档润色 |

**注意 Opus 4.7 / *-thinking 系列不接受 `--temperature` 参数**（推理模型温度由内部决定），脚本会自动忽略这些模型的 temperature 设置。

可用模型清单（CRS Anthropic 端点 `/api/v1/models`）：
- **Claude**：opus-4-1 / 4-5 / 4-6 / 4-6-thinking / **4-7**；sonnet-4 / 4-5 / 4-6；haiku-4-5
- **Gemini**：2.5-flash / 2.5-pro / 3-pro / 3.1-pro
- **GPT**：5 / 5.1 / 5.3-codex / 5.4 / 5.4-pro

睿动 OpenAI 端点 `/v1/models` 另含 GLM / Qwen / DeepSeek 等 39 个模型。

### 三种模式

```bash
# cautious（默认）：AI 出方案 → 显示 diff → 用户确认 → 应用
./kap-delegate.sh "重构 packages/governance/agents/auditor.py 为异步" \
    --files "packages/governance/agents/*.py"

# quick：AI 直接给 diff，自动应用（已 git stash 兜底）
./kap-delegate.sh --mode quick "把所有 print 改为 logger.info" \
    --files "src/**/*.py"

# diagnosis：只读分析，不产 diff
./kap-delegate.sh --mode diagnosis \
    --files "packages/distillation/**/*.py" \
    "解释蒸馏链各 Agent 的依赖关系"
```

### 测试循环（自动修复）

```bash
./kap-delegate.sh --mode quick \
    --test-cmd "pytest tests/test_router.py -x" \
    --max-rounds 5 \
    "修复路由测试失败"
```

每轮独立调用 LLM（不累积上下文），最多 N 轮。每轮失败输出尾 3KB 注入下一轮。

### 安全机制

每次运行前：

1. `git rev-parse HEAD` 记录 `HEAD_BEFORE`
2. 工作树脏 → `git stash push -u -m kap-delegate-stash-{ts}`
3. 调用 LLM → 提取 ```diff 块 → 展示给用户
4. 用户确认（cautious）或直接应用（quick）
5. Post-flight：`git diff --stat HEAD` + 显式给出回滚命令

中断（Ctrl+C）打印 stash 提醒。

### 完整选项

```
positional arguments:
  prompt                任务描述（必填）

主要选项:
  --mode {cautious,quick,diagnosis}     工作模式
  --backend {anthropic,openai}          模型后端，默认 anthropic
  --task-type {plan,dev,light}          任务类型 → 自动选模型
  --model MODEL                         手动指定模型（覆盖 --task-type）
  --files PATTERN                       注入文件上下文的 glob，可多次
  --test-cmd CMD                        测试命令（启用循环修复）
  --max-rounds N                        循环修复最大轮数（默认 5）

调优选项:
  --temperature FLOAT                   默认 0.2（Opus 4.7 / *-thinking 自动忽略）
  --max-tokens N                        默认 8192
  --output DIR                          日志目录（默认 .kap-delegate/logs/{ts}）
  --api-base URL                        覆盖 backend 默认 URL
  --system-prompt-file FILE             覆盖默认系统提示词
  --project-root PATH                   项目根（默认当前目录）

控制:
  --no-git                              跳过 git 安全检查
  -y, --yes                             cautious 模式跳过确认
```

### 何时用 / 何时不用

**用 kap-delegate**：

- 多文件批量改动（> 3 文件）
- 需要反复跑测试 → 改 → 再跑（≥ 3 轮）
- 样板代码批量生成
- 大段代码调研（diagnosis 模式）

**不要用**：

- 单文件小改（直接在 IDE 里改）
- 架构决策 / 产品讨论（在 Claude Code 里讨论）
- 涉及凭据 / .env 的操作

### 典型工作流

#### 工作流 1 · 重构一个模块（cautious）

```bash
./kap-delegate.sh \
    --files "packages/governance/agents/*.py" \
    "把 auditor.py 的同步 httpx.Client 改为 AsyncClient，函数签名加 async/await，调用方同步更新"
```

→ AI 给方案 → 你审 diff → 输入 y 应用 → post-flight 显示 git diff --stat → 回滚命令打印。

#### 工作流 2 · 跑挂的测试用循环修（quick + test-fix）

```bash
./kap-delegate.sh --mode quick \
    --test-cmd "pytest tests/test_pipeline.py -x" \
    --max-rounds 5 \
    "修复管道测试"
```

→ 跑测试 → 失败 → AI 修 → 应用 → 再跑测试 → 直到全绿或 5 轮。

#### 工作流 3 · 理解一个不熟悉的模块（diagnosis）

```bash
./kap-delegate.sh --mode diagnosis \
    --task-type plan \
    --files "packages/distillation/*.py" "packages/retrieval/*.py" \
    "解释蒸馏链与检索链的耦合点，列出可能的解耦改造方案"
```

→ AI 输出分析 → 不改任何文件 → 你拿到调研结果。

#### 工作流 4 · 文档润色（light）

```bash
./kap-delegate.sh --task-type light \
    --files "docs/02-产品需求PRD.md" \
    "把 §3 的措辞润色得更面向 SME 受众，不改章节结构"
```

→ Haiku 跑得快、成本低，适合文字工作。

### 故障排查

| 症状 | 排查 |
|---|---|
| `IRUIDONG_API_KEY 未设置` | 用 setx / export 设置；新开 shell 后生效 |
| `HTTP 401` | Key 失效，去睿动控制台查 |
| `HTTP 404` on `/chat/completions` | API base 错误，检查 `--api-base` |
| `网络错误，3 次重试后失败` | 检查 https://iruidong.com 可达性 |
| diff 提取失败 | LLM 输出格式不规范，看 `.kap-delegate/logs/.../main.log`，必要时用 `--system-prompt-file` 自定义提示词 |
| `git apply` 失败 | 工作树状态变了，diff 与当前不匹配；先 git status 检查 |

### 日志位置

每次运行生成：

```
<project-root>/.kap-delegate/logs/<时间戳>/
  ├── main.log       # 主调用：system prompt + user prompt + assistant 完整输出
  └── round-N.log    # test-fix 循环每轮的独立调用日志
```

建议把 `.kap-delegate/` 加入 `.gitignore`。

### 升级路线

- ☑ ~~等睿动接入 Opus → 修 `TASK_MODELS["plan"]`~~ → 改用 CRS Anthropic 端点（已实现）
- ☐ 流式 diff 实时预览（不等完成）
- ☐ 多个 diff 块的 selective apply（只应用其中几个）
- ☐ 与 Claude Code 集成：作为外部工具，让 Claude Code 在合适的时候自动调用
- ☐ 支持 Extended Thinking（Opus 4.6-thinking 的可见思维链）

### 与 codex-delegate 的关系

| 维度 | codex-delegate | kap-delegate（本脚本）|
|---|---|---|
| 后端 | OpenAI Codex CLI | 直连睿动 Chat Completions |
| 默认模型 | gpt-5-codex | claude-sonnet-4-6 |
| 工作流 | git stash + 三模式 + 测试循环 | **完全相同** |
| 配置位置 | `~/.codex/config.toml` | 项目内 `scripts/` + 环境变量 |
| 团队适用性 | 需要 OpenAI / CRS 中继 | 任何能访问睿动的环境 |

行为模式向上兼容 codex-delegate skill 文档，只换了底层实现。
