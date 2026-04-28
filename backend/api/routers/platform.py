"""
平台API路由 - 飞书/钉钉文档对接

严格按照企业级API授权流程：
1. 配置应用凭证（app_id/app_secret）
2. 申请API权限（需管理员审批）
3. 获取访问令牌
4. 调用文档API
"""

import os
import json
import httpx
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
from datetime import datetime
from pathlib import Path

router = APIRouter(prefix="/api/platform", tags=["platform"])

# ========== 配置存储路径 ==========
CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "configs"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
PLATFORM_CONFIG_FILE = CONFIG_DIR / "platform_credentials.json"

# ========== 数据模型 ==========

class PlatformCredentials(BaseModel):
    """平台凭证配置"""
    platform: str  # feishu / dingtalk
    app_id: str = Field(..., description="飞书App ID / 钉钉AppKey")
    app_secret: str = Field(..., description="飞书App Secret / 钉钉AppSecret")
    configured_at: Optional[str] = None
    configured_by: Optional[str] = None


class AuthStatusResponse(BaseModel):
    """授权状态响应"""
    platform: str
    configured: bool = False  # 凭证是否已配置
    authorized: bool = False  # Token是否有效
    app_id: Optional[str] = None  # 脱敏显示
    permissions: List[str] = []  # 已授权的权限
    error: Optional[str] = None
    required_permissions: List[Dict[str, str]] = []  # 需要申请的权限


class DocItem(BaseModel):
    """文档项"""
    id: str
    name: str
    type: str  # folder, doc, docx, sheet, wiki, pdf, file
    parent_id: Optional[str] = None
    size: Optional[int] = None
    update_time: Optional[str] = None
    url: Optional[str] = None
    children: Optional[List['DocItem']] = None


class DocumentsResponse(BaseModel):
    """文档列表响应"""
    platform: str
    documents: List[DocItem]
    total: int = 0


# ========== 凭证管理 ==========

def load_platform_config() -> Dict[str, PlatformCredentials]:
    """加载平台配置"""
    if PLATFORM_CONFIG_FILE.exists():
        try:
            data = json.loads(PLATFORM_CONFIG_FILE.read_text())
            return {k: PlatformCredentials(**v) for k, v in data.items()}
        except Exception:
            return {}
    return {}


def save_platform_config(configs: Dict[str, PlatformCredentials]):
    """保存平台配置"""
    data = {k: v.model_dump() for k, v in configs.items()}
    PLATFORM_CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


# ========== 飞书所需权限说明 ==========
FEISHU_REQUIRED_PERMISSIONS = [
    {
        "scope": "wiki:wiki:readonly",
        "name": "获取知识库信息",
        "description": "读取知识库空间和节点列表"
    },
    {
        "scope": "docx:document:readonly", 
        "name": "获取文档内容",
        "description": "读取云文档内容"
    },
    {
        "scope": "drive:drive:readonly",
        "name": "获取云盘文件",
        "description": "读取云盘文件列表"
    },
    {
        "scope": "drive:file:readonly",
        "name": "下载云盘文件",
        "description": "下载云盘中的文件"
    },
]

# ========== 钉钉所需权限说明 ==========
DINGTALK_REQUIRED_PERMISSIONS = [
    {
        "scope": "Contact.User.Read",
        "name": "读取用户信息",
        "description": "获取当前用户基本信息"
    },
    {
        "scope": "storage",
        "name": "云盘权限",
        "description": "读取钉钉云盘文件"
    },
    {
        "scope": "doc",
        "name": "文档权限", 
        "description": "读取钉钉文档内容"
    },
]


# ========== 凭证配置接口 ==========

@router.get("/{platform}/config")
async def get_platform_config(platform: str):
    """
    获取平台配置状态（不返回敏感信息）
    """
    if platform not in ["feishu", "dingtalk"]:
        raise HTTPException(status_code=400, detail="不支持的平台")
    
    configs = load_platform_config()
    config = configs.get(platform)
    
    required_permissions = FEISHU_REQUIRED_PERMISSIONS if platform == "feishu" else DINGTALK_REQUIRED_PERMISSIONS
    
    if config:
        # 脱敏显示app_id
        masked_app_id = config.app_id[:6] + "****" + config.app_id[-4:] if len(config.app_id) > 10 else "****"
        return {
            "platform": platform,
            "configured": True,
            "app_id": masked_app_id,
            "configured_at": config.configured_at,
            "required_permissions": required_permissions,
            "setup_guide": get_setup_guide(platform),
        }
    else:
        return {
            "platform": platform,
            "configured": False,
            "required_permissions": required_permissions,
            "setup_guide": get_setup_guide(platform),
        }


@router.post("/{platform}/config")
async def save_platform_config_api(
    platform: str,
    credentials: PlatformCredentials = Body(...)
):
    """
    保存平台凭证配置
    
    飞书：需要在飞书开放平台创建企业自建应用
    钉钉：需要在钉钉开放平台创建企业内部应用
    """
    if platform not in ["feishu", "dingtalk"]:
        raise HTTPException(status_code=400, detail="不支持的平台")
    
    credentials.platform = platform
    credentials.configured_at = datetime.now().isoformat()
    
    # 验证凭证是否有效
    try:
        if platform == "feishu":
            token = await get_feishu_tenant_token(credentials.app_id, credentials.app_secret)
        else:
            token = await get_dingtalk_token(credentials.app_id, credentials.app_secret)
        
        if not token:
            raise HTTPException(status_code=401, detail="凭证验证失败，请检查App ID和App Secret")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"凭证验证失败: {str(e)}")
    
    # 保存配置
    configs = load_platform_config()
    configs[platform] = credentials
    save_platform_config(configs)
    
    return {
        "status": "success",
        "message": f"{platform}凭证配置成功",
        "platform": platform,
    }


@router.delete("/{platform}/config")
async def delete_platform_config(platform: str):
    """删除平台配置"""
    configs = load_platform_config()
    if platform in configs:
        del configs[platform]
        save_platform_config(configs)
    return {"status": "success", "message": "配置已删除"}


# ========== 授权状态检查 ==========

@router.get("/{platform}/auth/status", response_model=AuthStatusResponse)
async def check_auth_status(platform: str):
    """
    检查平台授权状态
    
    返回：
    - configured: 凭证是否已配置
    - authorized: Token是否可用
    - permissions: 已授权的权限列表
    """
    if platform not in ["feishu", "dingtalk"]:
        raise HTTPException(status_code=400, detail="不支持的平台")
    
    configs = load_platform_config()
    config = configs.get(platform)
    
    required_permissions = FEISHU_REQUIRED_PERMISSIONS if platform == "feishu" else DINGTALK_REQUIRED_PERMISSIONS
    
    if not config:
        return AuthStatusResponse(
            platform=platform,
            configured=False,
            authorized=False,
            required_permissions=required_permissions,
            error="未配置应用凭证，请先配置App ID和App Secret"
        )
    
    # 验证Token
    try:
        if platform == "feishu":
            token = await get_feishu_tenant_token(config.app_id, config.app_secret)
            # 可选：检查权限范围
            permissions = await check_feishu_permissions(token)
        else:
            token = await get_dingtalk_token(config.app_id, config.app_secret)
            permissions = []
        
        masked_app_id = config.app_id[:6] + "****" + config.app_id[-4:] if len(config.app_id) > 10 else "****"
        
        return AuthStatusResponse(
            platform=platform,
            configured=True,
            authorized=True,
            app_id=masked_app_id,
            permissions=permissions,
            required_permissions=required_permissions,
        )
    except Exception as e:
        return AuthStatusResponse(
            platform=platform,
            configured=True,
            authorized=False,
            required_permissions=required_permissions,
            error=f"授权验证失败: {str(e)}"
        )


# ========== 文档列表接口 ==========

@router.get("/{platform}/documents", response_model=DocumentsResponse)
async def get_documents(
    platform: str,
    space_id: Optional[str] = Query(None, description="知识库/空间ID"),
    folder_id: Optional[str] = Query(None, description="文件夹ID"),
):
    """
    获取平台文档列表
    
    飞书：返回知识库空间列表，或指定空间下的文档
    钉钉：返回文档空间列表，或指定空间下的文档
    """
    if platform not in ["feishu", "dingtalk"]:
        raise HTTPException(status_code=400, detail="不支持的平台")
    
    configs = load_platform_config()
    config = configs.get(platform)
    
    if not config:
        raise HTTPException(status_code=401, detail="未配置平台凭证")
    
    try:
        if platform == "feishu":
            documents = await fetch_feishu_documents(config, space_id, folder_id)
        else:
            documents = await fetch_dingtalk_documents(config, space_id, folder_id)
        
        return DocumentsResponse(
            platform=platform,
            documents=documents,
            total=len(documents),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文档失败: {str(e)}")


@router.get("/{platform}/documents/{doc_id}/download")
async def download_document(
    platform: str,
    doc_id: str,
    doc_type: str = Query("docx", description="文档类型"),
):
    """
    下载文档内容
    
    返回文档的原始内容或转换后的文本
    """
    if platform not in ["feishu", "dingtalk"]:
        raise HTTPException(status_code=400, detail="不支持的平台")
    
    configs = load_platform_config()
    config = configs.get(platform)
    
    if not config:
        raise HTTPException(status_code=401, detail="未配置平台凭证")
    
    try:
        if platform == "feishu":
            content = await download_feishu_document(config, doc_id, doc_type)
        else:
            content = await download_dingtalk_document(config, doc_id)
        
        return {
            "doc_id": doc_id,
            "content": content,
            "doc_type": doc_type,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载文档失败: {str(e)}")


# ========== 飞书 API 实现 ==========

async def get_feishu_tenant_token(app_id: str, app_secret: str) -> str:
    """获取飞书租户访问令牌"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": app_id,
                "app_secret": app_secret,
            },
            timeout=10.0,
        )
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(data.get("msg", "获取飞书Token失败"))
        
        return data["tenant_access_token"]


async def check_feishu_permissions(token: str) -> List[str]:
    """检查飞书应用权限"""
    # 这里可以尝试调用各个API来检查权限
    # 简化处理，返回已配置的权限
    permissions = []
    async with httpx.AsyncClient() as client:
        # 尝试获取知识库
        try:
            resp = await client.get(
                "https://open.feishu.cn/open-apis/wiki/v2/spaces",
                headers={"Authorization": f"Bearer {token}"},
                params={"page_size": 1},
                timeout=5.0,
            )
            if resp.json().get("code") == 0:
                permissions.append("wiki:wiki:readonly")
        except:
            pass
        
        # 尝试获取云盘
        try:
            resp = await client.get(
                "https://open.feishu.cn/open-apis/drive/v1/files",
                headers={"Authorization": f"Bearer {token}"},
                params={"page_size": 1},
                timeout=5.0,
            )
            if resp.json().get("code") == 0:
                permissions.append("drive:drive:readonly")
        except:
            pass
    
    return permissions


async def fetch_feishu_documents(
    config: PlatformCredentials,
    space_id: Optional[str] = None,
    folder_id: Optional[str] = None,
) -> List[DocItem]:
    """获取飞书文档列表"""
    token = await get_feishu_tenant_token(config.app_id, config.app_secret)
    documents = []
    
    async with httpx.AsyncClient() as client:
        if not space_id:
            # 获取知识库空间列表
            resp = await client.get(
                "https://open.feishu.cn/open-apis/wiki/v2/spaces",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            data = resp.json()
            
            if data.get("code") == 0:
                for space in data.get("data", {}).get("items", []):
                    documents.append(DocItem(
                        id=space["space_id"],
                        name=space["name"],
                        type="folder",
                    ))
            
            # 同时获取云盘根目录
            resp = await client.get(
                "https://open.feishu.cn/open-apis/drive/v1/files",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            data = resp.json()
            
            if data.get("code") == 0:
                for file in data.get("data", {}).get("files", []):
                    doc_type = "folder" if file["type"] == "folder" else \
                               "docx" if file["type"] in ["docx", "doc"] else \
                               "sheet" if file["type"] == "sheet" else \
                               "pdf" if file.get("mime_type", "").endswith("pdf") else "file"
                    
                    documents.append(DocItem(
                        id=file["token"],
                        name=file["name"],
                        type=doc_type,
                        size=file.get("size"),
                        update_time=datetime.fromtimestamp(file.get("modified_time", 0)).strftime("%Y-%m-%d") if file.get("modified_time") else None,
                    ))
        else:
            # 获取指定空间下的文档
            params = {"page_size": 50}
            if folder_id:
                params["parent_node_token"] = folder_id
            
            resp = await client.get(
                f"https://open.feishu.cn/open-apis/wiki/v2/spaces/{space_id}/nodes",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=10.0,
            )
            data = resp.json()
            
            if data.get("code") == 0:
                for node in data.get("data", {}).get("items", []):
                    doc_type = "folder" if node.get("has_child") else \
                               "wiki" if node.get("obj_type") == "docx" else \
                               node.get("obj_type", "doc")
                    
                    documents.append(DocItem(
                        id=node["node_token"],
                        name=node["title"],
                        type=doc_type,
                        update_time=datetime.fromtimestamp(node.get("edit_time", 0)).strftime("%Y-%m-%d") if node.get("edit_time") else None,
                    ))
    
    return documents


async def download_feishu_document(
    config: PlatformCredentials,
    doc_id: str,
    doc_type: str,
) -> str:
    """下载飞书文档内容"""
    token = await get_feishu_tenant_token(config.app_id, config.app_secret)
    
    async with httpx.AsyncClient() as client:
        if doc_type in ["docx", "wiki", "doc"]:
            # 获取文档纯文本内容
            resp = await client.get(
                f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/raw_content",
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )
            data = resp.json()
            
            if data.get("code") == 0:
                return data.get("data", {}).get("content", "")
            else:
                raise Exception(data.get("msg", "获取文档内容失败"))
        else:
            # 下载文件
            resp = await client.get(
                f"https://open.feishu.cn/open-apis/drive/v1/files/{doc_id}/download",
                headers={"Authorization": f"Bearer {token}"},
                timeout=60.0,
            )
            if resp.status_code == 200:
                return resp.text
            else:
                raise Exception("下载文件失败")


# ========== 钉钉 API 实现 ==========

async def get_dingtalk_token(app_key: str, app_secret: str) -> str:
    """获取钉钉访问令牌"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.dingtalk.com/v1.0/oauth2/accessToken",
            json={
                "appKey": app_key,
                "appSecret": app_secret,
            },
            timeout=10.0,
        )
        data = response.json()
        
        if "accessToken" not in data:
            raise Exception(data.get("message", "获取钉钉Token失败"))
        
        return data["accessToken"]


async def fetch_dingtalk_documents(
    config: PlatformCredentials,
    space_id: Optional[str] = None,
    folder_id: Optional[str] = None,
) -> List[DocItem]:
    """获取钉钉文档列表"""
    token = await get_dingtalk_token(config.app_id, config.app_secret)
    documents = []
    
    async with httpx.AsyncClient() as client:
        if not space_id:
            # 获取文档空间列表
            resp = await client.get(
                "https://api.dingtalk.com/v1.0/doc/spaces",
                headers={"x-acs-dingtalk-access-token": token},
                timeout=10.0,
            )
            data = resp.json()
            
            for space in data.get("spaces", []):
                documents.append(DocItem(
                    id=space["spaceId"],
                    name=space["name"],
                    type="folder",
                ))
        else:
            # 获取指定空间下的文档
            params = {"spaceId": space_id}
            if folder_id:
                params["parentId"] = folder_id
            
            resp = await client.get(
                "https://api.dingtalk.com/v1.0/doc/docs",
                headers={"x-acs-dingtalk-access-token": token},
                params=params,
                timeout=10.0,
            )
            data = resp.json()
            
            for doc in data.get("docs", []):
                doc_type = "folder" if doc.get("docType") == "folder" else \
                           "doc" if doc.get("docType") == "alidoc" else \
                           doc.get("docType", "doc")
                
                documents.append(DocItem(
                    id=doc["docId"],
                    name=doc["title"],
                    type=doc_type,
                    update_time=doc.get("updatedTime"),
                ))
    
    return documents


async def download_dingtalk_document(config: PlatformCredentials, doc_id: str) -> str:
    """下载钉钉文档内容"""
    token = await get_dingtalk_token(config.app_id, config.app_secret)
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.dingtalk.com/v1.0/doc/documents/{doc_id}",
            headers={"x-acs-dingtalk-access-token": token},
            timeout=30.0,
        )
        
        if resp.status_code == 200:
            return resp.text
        else:
            raise Exception("下载文档失败")


# ========== 配置指南 ==========

def get_setup_guide(platform: str) -> Dict[str, Any]:
    """获取平台配置指南"""
    if platform == "feishu":
        return {
            "title": "飞书应用配置指南",
            "steps": [
                {
                    "step": 1,
                    "title": "创建企业自建应用",
                    "description": "登录飞书开放平台 (open.feishu.cn)，点击「创建应用」→「企业自建应用」",
                    "url": "https://open.feishu.cn/app"
                },
                {
                    "step": 2,
                    "title": "获取应用凭证",
                    "description": "在应用详情页的「凭证与基础信息」中获取 App ID 和 App Secret"
                },
                {
                    "step": 3,
                    "title": "申请API权限",
                    "description": "在「权限管理」中搜索并添加以下权限：\n- wiki:wiki:readonly（知识库读取）\n- docx:document:readonly（文档读取）\n- drive:drive:readonly（云盘读取）\n- drive:file:readonly（文件下载）"
                },
                {
                    "step": 4,
                    "title": "发布应用并审批",
                    "description": "创建应用版本并发布，等待企业管理员审批通过后方可使用"
                },
            ],
            "doc_url": "https://open.feishu.cn/document/home/introduction-to-custom-app-development/self-built-application-development-process"
        }
    else:
        return {
            "title": "钉钉应用配置指南",
            "steps": [
                {
                    "step": 1,
                    "title": "创建企业内部应用",
                    "description": "登录钉钉开放平台 (open.dingtalk.com)，进入「应用开发」→「企业内部开发」→「创建应用」",
                    "url": "https://open.dingtalk.com/developer"
                },
                {
                    "step": 2,
                    "title": "获取应用凭证",
                    "description": "在应用详情页获取 AppKey 和 AppSecret"
                },
                {
                    "step": 3,
                    "title": "申请API权限",
                    "description": "在「权限管理」中申请以下权限：\n- 通讯录个人信息读取\n- 云盘空间管理\n- 文档读取权限"
                },
                {
                    "step": 4,
                    "title": "发布并审批",
                    "description": "提交应用发布申请，等待管理员审批"
                },
            ],
            "doc_url": "https://open.dingtalk.com/document/orgapp/obtain-orgapp-token"
        }
