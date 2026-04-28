#!/usr/bin/env python3
"""
kap-delegate · 把繁重的代码工作委派给睿动网关上的 Claude Sonnet（或其他模型）

设计动机：
  原 codex-delegate skill 走 OpenAI Codex CLI，但 codex 0.118 已强制 Responses API，
  与睿动的 Chat Completions 不兼容。本脚本是 codex-delegate 工作流在睿动 + Claude Sonnet
  上的等价实现，保留 git 安全壳 + 三模式 + 测试循环。

用法：
  kap-delegate.py [选项] "任务描述"

模式：
  --mode cautious   （默认）AI 出方案 → 显示 diff → 用户确认 → 应用
  --mode quick      AI 直接给 diff，自动应用（已 stash 兜底）
  --mode diagnosis  只读分析，不产 diff

典型场景：
  # 重构一个 Python 模块为异步
  ./kap-delegate.py --files "packages/governance/agents/*.py" \\
                    "把 auditor.py 的 httpx.Client 改为 AsyncClient"

  # 测试循环修复
  ./kap-delegate.py --mode quick --test-cmd "pytest tests/test_router.py" \\
                    --max-rounds 5 \\
                    "修复路由测试失败"

  # 调研代码（只读）
  ./kap-delegate.py --mode diagnosis \\
                    --files "packages/distillation/**/*.py" \\
                    "解释蒸馏链各 Agent 的依赖关系"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from glob import glob
from pathlib import Path
from typing import Iterator

# ---------- 基础配置 ----------

DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 8192
DEFAULT_MAX_ROUNDS = 5

# ----- 双 Backend 配置 -----
# anthropic : 走 CRS Anthropic 原生 API（/v1/messages），有 Opus 全系列；推荐
# openai    : 走睿动 OpenAI Chat Completions（/v1/chat/completions），无 Opus；备选
BACKEND_ANTHROPIC = "anthropic"
BACKEND_OPENAI = "openai"
DEFAULT_BACKEND = BACKEND_ANTHROPIC

BACKEND_DEFAULTS = {
    BACKEND_ANTHROPIC: {
        "base_url_env":  "ANTHROPIC_BASE_URL",
        "base_url_fallback": "http://18.141.210.162:3000/api",
        "key_env":  "ANTHROPIC_AUTH_TOKEN",
    },
    BACKEND_OPENAI: {
        "base_url_env":  "IRUIDONG_BASE_URL",
        "base_url_fallback": "https://iruidong.com/v1",
        "key_env":  "IRUIDONG_API_KEY",
    },
}

# 按任务类型路由模型（团队约定）：
#   plan  规划/架构/PRD/方案 → Claude Opus 4.7（最强推理，CRS Anthropic 端点）
#   dev   开发/重构/实现     → Claude Sonnet 4.6（性价比平衡）
#   light 轻量/格式化/重命名 → Claude Haiku 4.5（快、便宜）
TASK_MODELS = {
    "plan":  "claude-opus-4-7",
    "dev":   "claude-sonnet-4-6",
    "light": "claude-haiku-4-5-20251001",
}
DEFAULT_TASK_TYPE = "dev"
DEFAULT_MODEL = TASK_MODELS[DEFAULT_TASK_TYPE]

# ---------- 颜色（Windows Git Bash 友好） ----------

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") != "1"

class C:
    RESET  = "\033[0m" if USE_COLOR else ""
    DIM    = "\033[2m" if USE_COLOR else ""
    BOLD   = "\033[1m" if USE_COLOR else ""
    AMBER  = "\033[38;5;214m" if USE_COLOR else ""
    CYAN   = "\033[38;5;80m"  if USE_COLOR else ""
    SAGE   = "\033[38;5;108m" if USE_COLOR else ""
    OXIDE  = "\033[38;5;167m" if USE_COLOR else ""
    PAPER  = "\033[38;5;187m" if USE_COLOR else ""

def info(msg: str)    -> None: print(f"{C.DIM}[i]{C.RESET} {msg}")
def step(msg: str)    -> None: print(f"{C.AMBER}[>]{C.RESET} {C.BOLD}{msg}{C.RESET}")
def ok(msg: str)      -> None: print(f"{C.SAGE}[+]{C.RESET} {msg}")
def warn(msg: str)    -> None: print(f"{C.AMBER}[!]{C.RESET} {msg}")
def fail(msg: str)    -> None: print(f"{C.OXIDE}[x]{C.RESET} {msg}", file=sys.stderr)
def hr() -> None: print(f"{C.DIM}{'─' * 64}{C.RESET}")

# ---------- 系统提示词 ----------

SYS_CAUTIOUS = """你是一名资深的、谨慎的代码变更助手，正在为 KAP（知识智能体平台）项目工作。

工作流程：
1. 用 1-2 句话说明你对任务的理解。
2. 列出需要修改的文件清单。
3. 用 ```diff ... ``` 代码块给出 unified diff（路径用项目根的相对路径）。
4. 最后用 1 句话说明风险点 / 需要人工验证的地方。

强制约束：
- 只做必要的最小改动。不重排版、不顺手优化、不加无关功能。
- 不修改用户未指定范围之外的文件。
- 任务模糊时，先反问澄清，不要猜测。
- 触及 .env / 凭据 / sk-* 等敏感文件时，拒绝并说明。
- 缩进：Python 4 空格、JS/TS/HTML/YAML 2 空格。
- 引用项目的命名/编码约定（如 CLAUDE.md 已声明）。

输出格式（严格遵守）：
## Understanding
[1-2 句]

## Plan
- file1: 改 X
- file2: 改 Y

## Diffs

```diff
--- a/path/to/file.py
+++ b/path/to/file.py
@@ ...
```

```diff
--- a/path/to/other.py
+++ b/path/to/other.py
@@ ...
```

## Risk / Verify
[1 句]
"""

SYS_QUICK = SYS_CAUTIOUS + """

【quick 模式补充】
你给出的 diff 将自动 git apply 到工作树（用户已 stash 兜底）。所以质量要求更高：
- 只在改动确定无歧义时输出 diff。
- 任何不确定，宁可输出"## Question" 段反问，也不要给出可能错的 diff。
"""

SYS_DIAGNOSIS = """你是一名只读代码分析师，正在为 KAP（知识智能体平台）项目做代码理解 / 调研。

你的输出**绝对不能**包含 diff、git 命令、或任何修改建议。
只输出分析、解释、依赖关系、潜在问题清单。

输出结构建议：
## 概览
## 关键模块
## 调用 / 依赖关系
## 潜在问题或观察
## 建议人工验证的点
"""

# ---------- 数据结构 ----------

@dataclass
class Config:
    prompt: str
    mode: str
    model: str
    backend: str
    files: list[str]
    test_cmd: str | None
    max_rounds: int
    output: Path
    api_base: str
    temperature: float
    max_tokens: int
    system_prompt_file: Path | None
    project_root: Path
    no_git: bool
    yes: bool

# ---------- 文件上下文收集 ----------

def collect_file_context(globs: list[str], project_root: Path, max_chars: int = 80_000) -> str:
    """读取 --files 匹配的文件，拼成 markdown 上下文。被 max_chars 截断。"""
    if not globs:
        return ""
    chunks = []
    total = 0
    seen = set()
    for pattern in globs:
        # glob 相对项目根
        if not pattern.startswith("/") and not pattern[1:2] == ":":
            full_pattern = str(project_root / pattern)
        else:
            full_pattern = pattern
        matched = glob(full_pattern, recursive=True)
        for path_str in sorted(matched):
            p = Path(path_str)
            if not p.is_file() or p in seen:
                continue
            seen.add(p)
            try:
                content = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue
            rel = p.relative_to(project_root) if p.is_relative_to(project_root) else p
            block = f"\n### `{rel}`\n```{p.suffix.lstrip('.') or 'text'}\n{content}\n```\n"
            if total + len(block) > max_chars:
                chunks.append(f"\n*[更多文件因长度限制省略，已包含 {len(chunks)} 个文件]*\n")
                return "".join(chunks)
            chunks.append(block)
            total += len(block)
    return "".join(chunks)

# ---------- 睿动 API 调用（SSE 流式） ----------

class APIError(Exception): pass

def _retry_request(req: urllib.request.Request, timeout: int) -> urllib.request.urlopen:
    """带 3 次指数退避的 urlopen。HTTPError 不重试（4xx 重试无意义）。"""
    last_err = None
    for attempt in range(3):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            body = e.read()[:500].decode("utf-8", errors="replace")
            raise APIError(f"HTTP {e.code}: {body}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            if attempt < 2:
                wait = 2 ** attempt
                warn(f"网络错误（尝试 {attempt+1}/3）: {e}，{wait}s 后重试")
                time.sleep(wait)
                continue
    raise APIError(f"3 次重试后仍失败: {last_err}")

def call_openai_streaming(
    api_base: str, api_key: str, model: str,
    system: str, user_msg: str, temperature: float, max_tokens: int,
    timeout: int = 120,
) -> Iterator[str]:
    """OpenAI Chat Completions 流式（睿动）。"""
    url = f"{api_base.rstrip('/')}/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "stream": True,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
    )
    with _retry_request(req, timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                return
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            text = delta.get("content")
            if text:
                yield text

def call_anthropic_streaming(
    api_base: str, api_key: str, model: str,
    system: str, user_msg: str, temperature: float, max_tokens: int,
    timeout: int = 180,
) -> Iterator[str]:
    """Anthropic Messages 流式（CRS /api 端点）。SSE 事件解析 content_block_delta.text。"""
    url = f"{api_base.rstrip('/')}/v1/messages"
    payload: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_msg}],
        "stream": True,
    }
    # Opus 4.7 与 *-thinking 系列废弃了 temperature 参数（推理模型温度由内部决定）
    if not (model.startswith("claude-opus-4-7") or model.endswith("-thinking")):
        payload["temperature"] = temperature
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "accept": "text/event-stream",
        },
    )
    with _retry_request(req, timeout) as resp:
        # Anthropic SSE：event: ... \n data: {...} \n\n
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            try:
                evt = json.loads(payload)
            except json.JSONDecodeError:
                continue
            etype = evt.get("type")
            if etype == "content_block_delta":
                delta = evt.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        yield text
            elif etype == "message_stop":
                return
            elif etype == "error":
                err = evt.get("error", {})
                raise APIError(f"Anthropic stream error: {err}")

def call_llm_streaming(
    backend: str, api_base: str, api_key: str, model: str,
    system: str, user_msg: str, temperature: float, max_tokens: int,
) -> Iterator[str]:
    """Backend 调度。"""
    if backend == BACKEND_ANTHROPIC:
        return call_anthropic_streaming(api_base, api_key, model, system, user_msg, temperature, max_tokens)
    elif backend == BACKEND_OPENAI:
        return call_openai_streaming(api_base, api_key, model, system, user_msg, temperature, max_tokens)
    else:
        raise APIError(f"未知 backend: {backend}")

# ---------- Git 安全壳 ----------

def run_git(args: list[str], cwd: Path, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)

def git_preflight(cwd: Path) -> dict:
    """返回 {head_before, stash_ref, is_dirty, is_repo}。脏树自动 stash 并打 ref。"""
    result = {"head_before": None, "stash_ref": None, "is_dirty": False, "is_repo": False}

    r = run_git(["rev-parse", "--is-inside-work-tree"], cwd)
    if r.returncode != 0:
        info("不在 git 仓库内，跳过 git 安全检查")
        return result
    result["is_repo"] = True

    r = run_git(["rev-parse", "HEAD"], cwd)
    head = r.stdout.strip() if r.returncode == 0 else None
    result["head_before"] = head

    r = run_git(["status", "--porcelain"], cwd)
    is_dirty = bool(r.stdout.strip())
    result["is_dirty"] = is_dirty

    if is_dirty:
        ts = int(time.time())
        msg = f"kap-delegate-stash-{ts}"
        r = run_git(["stash", "push", "-u", "-m", msg], cwd)
        if r.returncode == 0:
            stash_ref = f"stash@{{0}}"  # 最新 stash
            result["stash_ref"] = msg
            warn(f"工作树脏，已 stash → {msg}（恢复: git stash pop）")
        else:
            fail(f"stash 失败: {r.stderr}")
    return result

def git_postflight(cwd: Path, head_before: str | None, stash_ref: str | None) -> None:
    """汇报变更，给出回滚命令。"""
    hr()
    step("Post-flight 摘要")
    r = run_git(["diff", "--stat", "HEAD"], cwd)
    if r.stdout.strip():
        print(r.stdout)
    r = run_git(["status", "--short"], cwd)
    if r.stdout.strip():
        print(f"{C.DIM}状态:{C.RESET}\n{r.stdout}")
    if head_before:
        print(f"\n{C.DIM}回滚命令:{C.RESET} git reset --hard {head_before[:12]}")
    if stash_ref:
        print(f"{C.DIM}原工作树:{C.RESET} git stash list | grep '{stash_ref}'，恢复: git stash pop")

# ---------- Diff 提取与应用 ----------

DIFF_BLOCK_RE = re.compile(r"```(?:diff|patch)\s*\n(.*?)\n```", re.DOTALL)

def extract_diffs(text: str) -> list[str]:
    return DIFF_BLOCK_RE.findall(text)

def apply_diff(diff_text: str, cwd: Path) -> tuple[bool, str]:
    """git apply 应用 diff。返回 (success, stderr)。"""
    with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False, encoding="utf-8") as f:
        f.write(diff_text)
        if not diff_text.endswith("\n"):
            f.write("\n")
        diff_path = f.name
    try:
        r = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", diff_path],
            cwd=cwd, capture_output=True, text=True,
        )
        return r.returncode == 0, r.stderr
    finally:
        try:
            os.unlink(diff_path)
        except OSError:
            pass

def show_diff(diff_text: str) -> None:
    """彩色简单展示 diff。"""
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            print(f"{C.BOLD}{line}{C.RESET}")
        elif line.startswith("+"):
            print(f"{C.SAGE}{line}{C.RESET}")
        elif line.startswith("-"):
            print(f"{C.OXIDE}{line}{C.RESET}")
        elif line.startswith("@@"):
            print(f"{C.CYAN}{line}{C.RESET}")
        else:
            print(line)

# ---------- 主流程 ----------

def build_user_prompt(prompt: str, file_context: str, mode: str) -> str:
    parts = [prompt.strip()]
    if file_context:
        parts.append("\n---\n## 项目内文件上下文\n" + file_context)
    if mode == "cautious":
        parts.append("\n请按系统提示词的输出格式给出。")
    elif mode == "quick":
        parts.append("\n请直接给最小改动 diff。")
    elif mode == "diagnosis":
        parts.append("\n只做分析，不输出任何 diff 或修改建议。")
    return "\n".join(parts)

def select_system_prompt(mode: str, custom_path: Path | None) -> str:
    if custom_path:
        return custom_path.read_text(encoding="utf-8")
    return {"cautious": SYS_CAUTIOUS, "quick": SYS_QUICK, "diagnosis": SYS_DIAGNOSIS}[mode]

def stream_and_collect(cfg: Config, api_key: str, system: str, user_msg: str, log_path: Path) -> str:
    """调 LLM，边流式打印边落盘日志。返回完整文本。"""
    full = []
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as logf:
        logf.write(f"# kap-delegate log · {datetime.now().isoformat()}\n")
        logf.write(f"# backend={cfg.backend} model={cfg.model} mode={cfg.mode}\n")
        logf.write(f"# api_base={cfg.api_base}\n\n")
        logf.write(f"## system\n{system}\n\n")
        logf.write(f"## user\n{user_msg}\n\n")
        logf.write("## assistant (streaming)\n")
        logf.flush()

        for chunk in call_llm_streaming(
            cfg.backend, cfg.api_base, api_key, cfg.model,
            system, user_msg, cfg.temperature, cfg.max_tokens,
        ):
            sys.stdout.write(chunk)
            sys.stdout.flush()
            logf.write(chunk)
            full.append(chunk)
        sys.stdout.write("\n")
    return "".join(full)

def confirm(question: str, default_no: bool = True) -> bool:
    suffix = "[y/N]" if default_no else "[Y/n]"
    try:
        ans = input(f"{C.AMBER}? {question} {suffix}{C.RESET} ").strip().lower()
    except EOFError:
        return False
    if not ans:
        return not default_no
    return ans in ("y", "yes")

def run_one_round(cfg: Config, api_key: str, system: str, user_msg: str, log_path: Path) -> str:
    """跑一轮 LLM 调用，返回 assistant 完整输出。"""
    step(f"调用 {cfg.model} via {cfg.backend}（mode={cfg.mode}）")
    return stream_and_collect(cfg, api_key, system, user_msg, log_path)

def cautious_apply_flow(reply: str, cfg: Config) -> bool:
    diffs = extract_diffs(reply)
    if not diffs:
        warn("未在回复中检测到 ```diff 块。请人工查阅日志，必要时手工应用。")
        return False
    hr()
    step(f"提取到 {len(diffs)} 个 diff 块")
    for i, d in enumerate(diffs, 1):
        print(f"\n{C.DIM}─── diff [{i}/{len(diffs)}] ───{C.RESET}")
        show_diff(d)
    hr()
    if not cfg.yes and not confirm("应用以上 diff 到工作树？", default_no=True):
        warn("已放弃应用。")
        return False
    applied = 0
    for i, d in enumerate(diffs, 1):
        success, err = apply_diff(d, cfg.project_root)
        if success:
            ok(f"diff [{i}/{len(diffs)}] 应用成功")
            applied += 1
        else:
            fail(f"diff [{i}/{len(diffs)}] 失败:\n{err}")
    return applied > 0

def quick_apply_flow(reply: str, cfg: Config) -> bool:
    diffs = extract_diffs(reply)
    if not diffs:
        warn("未检测到 diff 块，跳过。")
        return False
    applied = 0
    for i, d in enumerate(diffs, 1):
        success, err = apply_diff(d, cfg.project_root)
        if success:
            ok(f"[quick] diff [{i}/{len(diffs)}] 已自动应用")
            applied += 1
        else:
            fail(f"[quick] diff [{i}/{len(diffs)}] 失败:\n{err}")
    return applied > 0

def test_fix_loop(cfg: Config, api_key: str, log_dir: Path) -> bool:
    """测试-修复循环。每轮独立 LLM 调用，避免上下文膨胀。"""
    if not cfg.test_cmd:
        return True
    step(f"启动 test-fix 循环（最大 {cfg.max_rounds} 轮）: {cfg.test_cmd}")
    for r in range(1, cfg.max_rounds + 1):
        hr()
        step(f"Round {r}/{cfg.max_rounds} · 跑测试")
        proc = subprocess.run(
            cfg.test_cmd, cwd=cfg.project_root, shell=True,
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            ok(f"测试全绿 · round {r}")
            return True
        tail = (proc.stdout + "\n" + proc.stderr)[-3000:]
        warn(f"测试失败 → 委派修复（输出尾 3KB 注入）")
        system = select_system_prompt("quick", cfg.system_prompt_file)
        user_msg = (
            f"测试命令：`{cfg.test_cmd}`\n\n"
            f"测试输出（尾部）：\n```\n{tail}\n```\n\n"
            f"请用最小改动修复测试失败。直接给 diff。"
        )
        log_path = log_dir / f"round-{r}.log"
        reply = run_one_round(cfg, api_key, system, user_msg, log_path)
        if not quick_apply_flow(reply, cfg):
            fail(f"Round {r} 应用失败，终止循环。")
            return False
    fail(f"达到最大轮数 {cfg.max_rounds}，仍未全绿。")
    return False

# ---------- 入口 ----------

def parse_args() -> Config:
    p = argparse.ArgumentParser(
        prog="kap-delegate",
        description="把繁重代码工作委派给睿动网关上的 Claude Sonnet（或其他模型）。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
典型用法:
  kap-delegate.py "重构 packages/governance/agents/auditor.py 为异步" \\
      --files "packages/governance/agents/*.py"

  kap-delegate.py --mode quick --test-cmd "pytest tests/" --max-rounds 5 \\
      "修复测试失败"

  kap-delegate.py --mode diagnosis --files "**/*.py" \\
      "解释这个项目的整体调用链"

环境变量:
  IRUIDONG_API_KEY    睿动 API Key（必需）
""",
    )
    p.add_argument("prompt", help="任务描述")
    p.add_argument("--mode", choices=["cautious", "quick", "diagnosis"], default="cautious",
                   help="cautious=出方案后用户确认；quick=直接 apply；diagnosis=只读分析")
    p.add_argument("--backend", choices=[BACKEND_ANTHROPIC, BACKEND_OPENAI], default=DEFAULT_BACKEND,
                   help=(
                       f"模型后端：anthropic=CRS Anthropic API（默认，含 Opus 全系列）；"
                       f"openai=睿动 OpenAI 兼容（仅 Sonnet/Haiku）"
                   ))
    p.add_argument("--task-type", choices=list(TASK_MODELS.keys()), default=DEFAULT_TASK_TYPE,
                   help=(
                       f"任务类型决定默认模型："
                       f"plan→{TASK_MODELS['plan']} (规划)；"
                       f"dev→{TASK_MODELS['dev']} (开发，默认)；"
                       f"light→{TASK_MODELS['light']} (轻量)"
                   ))
    p.add_argument("--model", default=None,
                   help="模型名（覆盖 --task-type 默认）。anthropic backend 模型清单见 CRS /api/v1/models")
    p.add_argument("--files", action="append", default=[],
                   help="要注入上下文的文件 glob，可多次指定（如 'packages/**/*.py'）")
    p.add_argument("--test-cmd", default=None,
                   help="测试命令；指定后启用 test-fix 循环")
    p.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS,
                   help=f"test-fix 最大轮数，默认 {DEFAULT_MAX_ROUNDS}")
    p.add_argument("--output", type=Path, default=None,
                   help="日志目录（默认 .kap-delegate/logs/{ts}/）")
    p.add_argument("--api-base", default=None,
                   help="API base URL，默认按 --backend 取（anthropic 默认 http://18.141.210.162:3000/api ; openai 默认 https://iruidong.com/v1）")
    p.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    p.add_argument("--system-prompt-file", type=Path, default=None,
                   help="自定义系统提示词文件，覆盖默认")
    p.add_argument("--project-root", type=Path, default=Path.cwd(),
                   help="项目根目录，默认当前目录")
    p.add_argument("--no-git", action="store_true", help="跳过 git 安全检查")
    p.add_argument("-y", "--yes", action="store_true",
                   help="cautious 模式跳过确认（慎用）")
    args = p.parse_args()

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = args.output or args.project_root / ".kap-delegate" / "logs" / ts
    model = args.model or TASK_MODELS[args.task_type]

    backend_cfg = BACKEND_DEFAULTS[args.backend]
    api_base = (
        args.api_base
        or os.environ.get(backend_cfg["base_url_env"])
        or backend_cfg["base_url_fallback"]
    )

    return Config(
        prompt=args.prompt, mode=args.mode, model=model, backend=args.backend,
        files=args.files, test_cmd=args.test_cmd, max_rounds=args.max_rounds,
        output=output, api_base=api_base,
        temperature=args.temperature, max_tokens=args.max_tokens,
        system_prompt_file=args.system_prompt_file,
        project_root=args.project_root.resolve(), no_git=args.no_git,
        yes=args.yes,
    )

def main() -> int:
    cfg = parse_args()

    backend_cfg = BACKEND_DEFAULTS[cfg.backend]
    key_env = backend_cfg["key_env"]
    api_key = os.environ.get(key_env)
    if not api_key:
        fail(f"环境变量 {key_env} 未设置（backend={cfg.backend}）。")
        if cfg.backend == BACKEND_ANTHROPIC:
            info("Windows: setx ANTHROPIC_AUTH_TOKEN cr_...")
            info("Linux/Mac: export ANTHROPIC_AUTH_TOKEN=cr_...")
            info("可选: export ANTHROPIC_BASE_URL=http://18.141.210.162:3000/api")
        else:
            info("Windows: setx IRUIDONG_API_KEY sk-...")
            info("Linux/Mac: export IRUIDONG_API_KEY=sk-...")
        return 2

    print(f"\n{C.BOLD}{C.AMBER}╭─ kap-delegate ──────────────────────────────────────╮{C.RESET}")
    print(f"{C.BOLD}{C.AMBER}│{C.RESET}  task     · {cfg.prompt[:50]}{'...' if len(cfg.prompt)>50 else ''}")
    print(f"{C.BOLD}{C.AMBER}│{C.RESET}  mode     · {cfg.mode}")
    print(f"{C.BOLD}{C.AMBER}│{C.RESET}  backend  · {cfg.backend}")
    print(f"{C.BOLD}{C.AMBER}│{C.RESET}  model    · {cfg.model}")
    print(f"{C.BOLD}{C.AMBER}│{C.RESET}  api      · {cfg.api_base}")
    print(f"{C.BOLD}{C.AMBER}│{C.RESET}  cwd      · {cfg.project_root}")
    print(f"{C.BOLD}{C.AMBER}│{C.RESET}  log dir  · {cfg.output}")
    if cfg.files:
        print(f"{C.BOLD}{C.AMBER}│{C.RESET}  files    · {', '.join(cfg.files[:3])}{'...' if len(cfg.files)>3 else ''}")
    if cfg.test_cmd:
        print(f"{C.BOLD}{C.AMBER}│{C.RESET}  test     · {cfg.test_cmd} (max {cfg.max_rounds})")
    print(f"{C.BOLD}{C.AMBER}╰─────────────────────────────────────────────────────╯{C.RESET}\n")

    # Pre-flight
    git_state = {"head_before": None, "stash_ref": None}
    if not cfg.no_git and cfg.mode != "diagnosis":
        git_state = git_preflight(cfg.project_root)

    # 上下文
    ctx = collect_file_context(cfg.files, cfg.project_root)
    if ctx:
        info(f"已注入 {len(ctx)} 字符的文件上下文")

    # 主调用
    user_prompt = build_user_prompt(cfg.prompt, ctx, cfg.mode)
    system = select_system_prompt(cfg.mode, cfg.system_prompt_file)
    cfg.output.mkdir(parents=True, exist_ok=True)
    log_path = cfg.output / "main.log"

    hr()
    try:
        reply = run_one_round(cfg, api_key, system, user_prompt, log_path)
    except APIError as e:
        fail(f"LLM 调用失败: {e}")
        return 3

    # 应用 diff
    applied = False
    if cfg.mode == "cautious":
        applied = cautious_apply_flow(reply, cfg)
    elif cfg.mode == "quick":
        applied = quick_apply_flow(reply, cfg)
    elif cfg.mode == "diagnosis":
        ok("diagnosis 模式完成（只读，无变更）")

    # 测试循环
    if cfg.test_cmd and cfg.mode != "diagnosis":
        test_fix_loop(cfg, api_key, cfg.output)

    # Post-flight
    if git_state.get("is_repo") and cfg.mode != "diagnosis":
        git_postflight(cfg.project_root, git_state.get("head_before"), git_state.get("stash_ref"))

    print()
    ok(f"日志已保存到: {log_path}")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        warn("被用户中断（Ctrl+C）。如已 stash，恢复: git stash pop")
        sys.exit(130)
