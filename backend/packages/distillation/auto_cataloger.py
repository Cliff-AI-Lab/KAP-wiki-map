"""自动目录生成器 — 基于 taxonomy 骨架 + 主题匹配生成规范化 category_path。

OPT-01: 替代原先简陋的 "/".join(key_topics[:2]) 逻辑。
将 Librarian 提取的 key_topics 与 Refiner 输出的 domain_id 结合，
生成层级化、一致性的 category_path，并与 domain_id 体系对齐。
"""

from __future__ import annotations

import re
from functools import lru_cache

from packages.common import get_logger

log = get_logger("distillation.auto_cataloger")

# ── 同义词归一化表 ──────────────────────────────────────
# key: 非标准表述 → value: 规范主题名
# 随实际数据增长可持续补充
_SYNONYM_MAP: dict[str, str] = {
    # 财务相关
    "差旅报销": "差旅费报销",
    "出差报销": "差旅费报销",
    "报销制度": "费用报销",
    "报销管理": "费用报销",
    "费用管理": "费用报销",
    "薪酬管理": "薪酬福利",
    "工资管理": "薪酬福利",
    "薪资": "薪酬福利",
    "预算管理": "预算制度",
    "财务规范": "财务报销",
    "财务管理": "财务报销",
    # 人事相关
    "入职管理": "入职流程",
    "新员工入职": "入职流程",
    "离职管理": "离职流程",
    "员工离职": "离职流程",
    "请假管理": "考勤管理",
    "考勤打卡": "考勤管理",
    "绩效考核": "绩效管理",
    "KPI考核": "绩效管理",
    "OKR": "绩效管理",
    # 技术相关
    "系统设计": "架构设计",
    "技术架构": "架构设计",
    "API文档": "接口文档",
    "接口说明": "接口文档",
    "部署手册": "运维部署",
    "部署文档": "运维部署",
    "运维手册": "运维部署",
    # 项目相关
    "会议记录": "会议纪要",
    "周报": "进度跟踪",
    "日报": "进度跟踪",
    "项目计划": "项目规划",
    "项目规划书": "项目规划",
    "Sprint": "迭代管理",
    "迭代": "迭代管理",
    # 产品相关
    "PRD": "需求文档",
    "产品需求": "需求文档",
    "需求说明": "需求文档",
    "用户故事": "需求文档",
    "竞品分析": "市场分析",
    "市场调研": "市场分析",
    # 质量相关
    "测试报告": "测试文档",
    "测试计划": "测试文档",
    "Bug": "缺陷管理",
    "缺陷": "缺陷管理",
}

# ── doc_type → 默认 domain_id 映射 ────────────────────
_DOC_TYPE_DOMAIN_HINTS: dict[str, str] = {
    "规章制度": "regulation",
    "流程说明": "regulation",
    "会议纪要": "project",
    "技术文档": "tech",
    "培训材料": "tech",
    "通知公告": "regulation",
}


class AutoCataloger:
    """自动目录生成器。

    基于 taxonomy 知识域体系，将 (key_topics, domain_id, doc_type)
    映射为规范化的 category_path。
    """

    def __init__(self) -> None:
        from packages.retrieval.taxonomy import (
            get_default_taxonomy,
            get_domain_name_map,
            get_domain_description_map,
        )
        self._taxonomy = get_default_taxonomy()
        self._domain_name_map = get_domain_name_map()       # domain_id → 中文名
        self._domain_desc_map = get_domain_description_map() # domain_id → description
        # 反向映射：中文名 → domain_id（用于从 key_topics 推断）
        self._name_to_domain: dict[str, str] = {}
        for did, name in self._domain_name_map.items():
            self._name_to_domain[name] = did
        # 构建 description 中的关键词索引：keyword → domain_id
        self._keyword_domain_index: dict[str, str] = {}
        self._build_keyword_index()

        log.info(
            "auto_cataloger_init",
            domains=len(self._domain_name_map),
            synonyms=len(_SYNONYM_MAP),
        )

    def _build_keyword_index(self) -> None:
        """从 taxonomy description 中提取关键词，建立 keyword→domain_id 索引。"""
        for did, desc in self._domain_desc_map.items():
            # 提取中文词汇（简单分词：按标点和符号切分）
            terms = re.split(r'[，、。；：（）(),.;:\s]+', desc)
            for term in terms:
                term = term.strip()
                if len(term) >= 2:
                    self._keyword_domain_index[term] = did

    def generate_category_path(
        self,
        key_topics: list[str],
        domain_id: str = "",
        doc_type: str = "",
    ) -> str:
        """生成规范化的 category_path。

        优先级：
        1. domain_id 有效 → 用 domain 层级作为前缀 + key_topics 补充末级
        2. domain_id 无效 → 从 key_topics 推断 domain → 同上
        3. 都无法匹配 → 用 doc_type hint 或 fallback 到 "未分类"
        """
        # 归一化 key_topics
        normalized_topics = [self._normalize_topic(t) for t in key_topics if t.strip()]

        # Step 1: 确定 domain
        resolved_domain = domain_id
        if not resolved_domain or resolved_domain not in self._domain_name_map:
            resolved_domain = self._match_domain_from_topics(normalized_topics)
        if not resolved_domain:
            resolved_domain = _DOC_TYPE_DOMAIN_HINTS.get(doc_type, "")

        # Step 2: 构建路径
        if resolved_domain and resolved_domain in self._domain_name_map:
            path_parts = self._domain_to_path_parts(resolved_domain)
            # 补充第三层级：从 key_topics 中选一个不重复于 domain 名称的主题
            sub_topic = self._pick_sub_topic(normalized_topics, path_parts)
            if sub_topic:
                path_parts.append(sub_topic)
            return "/".join(path_parts)

        # Fallback: 用 key_topics 直接构建（最多2层）
        if normalized_topics:
            return "/".join(normalized_topics[:2])

        return "未分类"

    def _normalize_topic(self, topic: str) -> str:
        """主题归一化：同义词合并。"""
        topic = topic.strip()
        return _SYNONYM_MAP.get(topic, topic)

    def _match_domain_from_topics(self, topics: list[str]) -> str:
        """从 key_topics 推断最匹配的 domain_id。

        匹配策略：
        1. 精确匹配：topic == domain.name
        2. 包含匹配：topic 包含 domain.name 或反之
        3. 关键词索引匹配：topic 在 description 关键词中出现
        """
        if not topics:
            return ""

        best_domain = ""
        best_score = 0

        for topic in topics:
            # 精确匹配 domain name
            if topic in self._name_to_domain:
                did = self._name_to_domain[topic]
                score = 10
                if score > best_score:
                    best_score = score
                    best_domain = did
                continue

            # 包含匹配
            for name, did in self._name_to_domain.items():
                if topic in name or name in topic:
                    score = 5
                    if score > best_score:
                        best_score = score
                        best_domain = did

            # 关键词索引匹配
            if topic in self._keyword_domain_index:
                did = self._keyword_domain_index[topic]
                score = 3
                if score > best_score:
                    best_score = score
                    best_domain = did

            # 部分关键词匹配
            for kw, did in self._keyword_domain_index.items():
                if len(kw) >= 3 and (kw in topic or topic in kw):
                    score = 2
                    if score > best_score:
                        best_score = score
                        best_domain = did

        if best_domain:
            log.debug(
                "domain_inferred",
                topics=topics,
                domain=best_domain,
                score=best_score,
            )
        return best_domain

    def _domain_to_path_parts(self, domain_id: str) -> list[str]:
        """将 domain_id 转换为中文路径层级。

        例: "regulation/finance" → ["制度规范", "财务管理"]
        例: "tech" → ["技术文档"]
        """
        parts: list[str] = []
        # 处理层级 domain_id（如 "regulation/finance"）
        id_segments = domain_id.split("/")

        # 先查找完整的 domain_id
        if domain_id in self._domain_name_map:
            # 如果有 parent_id，先加 parent 名称
            domain = next((d for d in self._taxonomy if d.domain_id == domain_id), None)
            if domain and domain.parent_id:
                parent_name = self._domain_name_map.get(domain.parent_id, "")
                if parent_name:
                    parts.append(parent_name)
            parts.append(self._domain_name_map[domain_id])
        else:
            # 逐段查找
            for seg in id_segments:
                name = self._domain_name_map.get(seg, "")
                if name:
                    parts.append(name)

        return parts if parts else [domain_id]

    def _pick_sub_topic(self, topics: list[str], path_parts: list[str]) -> str:
        """从 key_topics 中选一个补充到分类路径末级的主题。

        排除已在 path_parts 中出现的主题名。
        """
        path_set = set(path_parts)
        for topic in topics:
            if topic not in path_set and len(topic) >= 2:
                return topic
        return ""


# ── 模块级单例 ──────────────────────────────────────────

_instance: AutoCataloger | None = None


def get_auto_cataloger() -> AutoCataloger:
    """获取 AutoCataloger 单例。"""
    global _instance
    if _instance is None:
        _instance = AutoCataloger()
    return _instance
