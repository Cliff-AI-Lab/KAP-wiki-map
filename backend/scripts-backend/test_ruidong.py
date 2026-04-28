"""
睿动 (iRuidong) 平台连通性 + 模型遍历验证脚本

用法：
    python scripts/test_ruidong.py

输出：
    1. 网络连通
    2. API Key 校验
    3. /v1/models 可用模型列表
    4. 聊天模型过滤结果（按照睿动开发规范 MUST-3）
    5. 第一个聊天模型的 chat completion 调用测试
    6. 推荐写入 .env 的 LLM_MODEL

约束（来自 C:\\Users\\issuser\\.claude\\rules\\common\\ruidong-agent-dev.md）：
- MUST: 所有模型调用走 iruidong.com/v1（OpenAI 兼容）
- MUST: 客户端过滤非聊天模型
- MUST NOT: 硬编码 API Key / 模型列表
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Windows 控制台 UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# 加载 .env
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    print("[WARN] python-dotenv 未安装，将直接读环境变量")

API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
BASE_URL = os.environ.get("OPENAI_BASE_URL", "").strip().rstrip("/")


def check(label: str, ok: bool, detail: str = "") -> None:
    mark = "OK " if ok else "ERR"
    print(f"[{mark}] {label}" + (f"  ({detail})" if detail else ""))
    if not ok:
        sys.exit(1)


def main() -> None:
    print("=" * 60)
    print("  睿动 iRuidong · 连通性与模型遍历检查")
    print("=" * 60)

    # Step 1: 配置核查
    check("API_KEY 非空", bool(API_KEY), f"len={len(API_KEY)}")
    check("BASE_URL 指向睿动",
          "iruidong.com" in BASE_URL,
          BASE_URL)

    # Step 2: HTTP 可达
    import httpx
    try:
        r = httpx.get(BASE_URL.replace("/v1", ""), timeout=10, verify=True)
        check("网络可达", True, f"HTTP {r.status_code}")
    except Exception as e:
        check("网络可达", False, str(e))

    # Step 3: /v1/models 列表
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        r = httpx.get(f"{BASE_URL}/models", headers=headers, timeout=15)
        check("/v1/models 返回 200", r.status_code == 200, f"HTTP {r.status_code}")
        payload = r.json()
    except Exception as e:
        check("/v1/models 返回 200", False, str(e))
        return

    models = payload.get("data", payload) if isinstance(payload, dict) else payload
    print(f"[INFO] 原始模型数: {len(models)}")

    # Step 4: 客户端过滤聊天模型（MUST-3）
    CHAT_HINT = ("gpt", "claude", "qwen", "llama", "mistral", "yi",
                 "glm", "deepseek", "ernie", "moonshot", "baichuan",
                 "kimi", "minimax", "ruidong-flash", "ruidong-pro",
                 "chat", "instruct", "4o", "sonnet", "haiku", "opus")
    NON_CHAT = ("embedding", "embed", "rerank", "reranker", "bge", "m3e",
                "audio", "whisper", "tts", "voice", "speech",
                "vision-only", "image", "dall-e", "sd", "flux",
                "moderation",
                # 音乐 / 视频生成
                "ace-step", "wan-", "t2v", "i2v", "ti2v", "video",
                "music",
                # 代码补全专用（非对话）
                "coder-local", "coder-completion")

    def looks_like_chat(name: str) -> bool:
        n = name.lower()
        if any(k in n for k in NON_CHAT):
            return False
        return any(k in n for k in CHAT_HINT) or "/" in n or "-" in n

    ids = [m.get("id") if isinstance(m, dict) else str(m) for m in models]
    chat_models = [m for m in ids if m and looks_like_chat(m)]
    print(f"[INFO] 过滤后聊天模型: {len(chat_models)}")
    for m in chat_models[:15]:
        print(f"       - {m}")
    if len(chat_models) > 15:
        print(f"       ... ({len(chat_models) - 15} more)")

    if not chat_models:
        print("[ERR] 无聊天模型可用，请检查 Key 权限")
        sys.exit(1)

    # Step 5: 第一个聊天模型做 chat completion 冒烟测试
    test_model = chat_models[0]
    print(f"[INFO] 冒烟测试模型: {test_model}")
    try:
        body = {
            "model": test_model,
            "messages": [{"role": "user", "content": "你好，回一个字：好"}],
            "max_tokens": 16,
            "temperature": 0,
        }
        r = httpx.post(f"{BASE_URL}/chat/completions",
                       headers=headers, json=body, timeout=30)
        check("/chat/completions 200", r.status_code == 200,
              f"HTTP {r.status_code}")
        reply = r.json()["choices"][0]["message"]["content"]
        print(f"[INFO] 模型回复: {reply!r}")
    except Exception as e:
        check("/chat/completions 200", False, str(e))

    # Step 6: 推荐配置
    print()
    print("=" * 60)
    print("  结果 · 将下面一行填入 .env")
    print("=" * 60)
    print(f"  LLM_MODEL={test_model}")
    print()
    print("  (可选) 其他可用模型：")
    for m in chat_models[1:6]:
        print(f"         {m}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[ABORT] 用户中断")
        sys.exit(130)
