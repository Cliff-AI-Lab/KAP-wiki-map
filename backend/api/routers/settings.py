"""系统设置 API — 大模型配置管理"""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "configs"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = CONFIG_DIR / "llm_settings.json"


class LLMSettingsPayload(BaseModel):
    llm_provider: str = "openai"
    llm_model: str = "deepseek"
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    embedding_provider: str = "mock"


class TestConnectionPayload(BaseModel):
    provider: str
    api_key: str
    base_url: str
    model: str


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_settings(data: dict):
    SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@router.get("")
async def get_settings():
    """获取当前 LLM 配置（API Key 脱敏）"""
    data = load_settings()
    if data.get("openai_api_key"):
        key = data["openai_api_key"]
        data["openai_api_key"] = key[:8] + "****" + key[-4:] if len(key) > 12 else "****"
    return data


@router.post("")
async def save_settings_api(payload: LLMSettingsPayload):
    """保存 LLM 配置"""
    data = payload.model_dump()
    # 如果前端传了脱敏的 key，保留原有 key
    existing = load_settings()
    if data.get("openai_api_key") and "****" in (data.get("openai_api_key") or ""):
        data["openai_api_key"] = existing.get("openai_api_key", "")
    save_settings(data)
    return {"status": "ok", "message": "配置已保存"}


@router.post("/test")
async def test_connection(payload: TestConnectionPayload):
    """测试 LLM 连接"""
    import httpx

    try:
        base_url = payload.base_url.rstrip("/")

        if payload.provider == "anthropic":
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{base_url}/messages",
                    headers={
                        "x-api-key": payload.api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": payload.model,
                        "max_tokens": 5,
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                    timeout=15.0,
                )
                if resp.status_code in (200, 201):
                    return {"status": "ok", "message": f"{payload.model} 连接成功"}
                else:
                    detail = resp.json().get("error", {}).get("message", resp.text[:100])
                    raise HTTPException(status_code=400, detail=f"连接失败: {detail}")
        else:
            # OpenAI-compatible
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {payload.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": payload.model,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 5,
                    },
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    return {"status": "ok", "message": f"{payload.model} 连接成功"}
                else:
                    detail = resp.json().get("error", {}).get("message", resp.text[:100])
                    raise HTTPException(status_code=400, detail=f"连接失败: {detail}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="连接超时，请检查 API 端点")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"连接错误: {str(e)}")
