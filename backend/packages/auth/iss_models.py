"""ISS 领域模型镜像（Pydantic）。

镜像 `_refs/iss-kb/iss-ai-knowledge/iss-common/iss-api-system/.../model/LoginUser.java`
与 `.../domain/SysUser.java`，让 Python 端能反序列化 ISS Redis 中的 LoginUser
与 ISS-System HTTP 返回的部门/用户实体。

字段对齐原则：
- 名称保持 ISS Java 命名（驼峰），Pydantic 用 ``alias`` 兼容下划线访问
- 容忍未知字段（``extra="ignore"``），ISS 升级新增字段不破坏 KAP
- 不写 ISS 的业务方法（如 ``isAdmin()``），仅做数据承接
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ISSSysUser(BaseModel):
    """对齐 com.isoftstone.system.api.domain.SysUser."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    user_id: int | None = Field(default=None, alias="userId")
    user_name: str | None = Field(default=None, alias="userName")
    nick_name: str | None = Field(default=None, alias="nickName")
    email: str | None = None
    phone: str | None = None
    sex: str | None = None
    avatar: str | None = None
    status: str | None = None  # 0=正常 / 1=停用
    del_flag: str | None = Field(default=None, alias="delFlag")
    dept_id: int | None = Field(default=None, alias="deptId")


class ISSDept(BaseModel):
    """对齐 com.isoftstone.system.api.domain.SysDept（部分字段，按需扩展）."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    dept_id: int = Field(alias="deptId")
    parent_id: int | None = Field(default=None, alias="parentId")
    ancestors: str = ""  # 逗号分隔的祖先链，如 "0,100,101"
    dept_name: str | None = Field(default=None, alias="deptName")
    order_num: int | None = Field(default=None, alias="orderNum")
    leader: str | None = None
    status: str | None = None
    del_flag: str | None = Field(default=None, alias="delFlag")


class ISSLoginUser(BaseModel):
    """对齐 com.isoftstone.system.api.model.LoginUser，存储在 Redis ``login_tokens:{user_key}``."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    token: str = ""
    userid: int | None = None
    username: str = ""
    login_time: int | None = Field(default=None, alias="loginTime")
    expire_time: int | None = Field(default=None, alias="expireTime")
    ipaddr: str = ""
    permissions: set[str] = Field(default_factory=set)
    roles: set[str] = Field(default_factory=set)
    sys_user: ISSSysUser | None = Field(default=None, alias="sysUser")

    @classmethod
    def from_redis_payload(cls, payload: dict[str, Any]) -> ISSLoginUser:
        """从 Redis 反序列化结果（ISS 用 FastJSON2，Python 用 json.loads）构造实例。

        ISS RedisService 写入时调 FastJSON2，对象包含 ``@type`` 等元字段，需要忽略；
        permissions / roles 在 JSON 中可能是 list，需转 set。
        """
        cleaned: dict[str, Any] = {}
        for k, v in payload.items():
            if k.startswith("@"):
                continue
            cleaned[k] = v
        for key in ("permissions", "roles"):
            val = cleaned.get(key)
            if isinstance(val, list):
                cleaned[key] = set(val)
            elif isinstance(val, dict):
                # FastJSON2 set 序列化可能是 dict，取 keys
                cleaned[key] = set(val.keys())
        return cls.model_validate(cleaned)
