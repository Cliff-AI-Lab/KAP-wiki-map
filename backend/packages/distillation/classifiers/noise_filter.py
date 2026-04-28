"""废话过滤器 — PoC 阶段使用规则引擎，后续可替换为 BERT 分类器。

识别 IM 群聊中的纯寒暄、打卡、无意义回复等低价值内容。
"""

from __future__ import annotations

import re

from packages.common import get_logger
from packages.common.types import RawDocument

log = get_logger("classifier.noise_filter")

# 废话关键词/模式
NOISE_PATTERNS = [
    r"^(收到|好的|OK|ok|嗯|嗯嗯|哈哈|👍|666|赞|了解|明白|知道了|谢谢|感谢|辛苦了?)$",
    r"^(早|早上好|早安|下午好|晚上好|下班了?)$",
    r"^[\U0001F300-\U0001FAFF\U00002702-\U000027B0\U0000FE00-\U0000FE0F]+$",  # 纯表情
    r"^@\S+\s*(收到|好的|OK|ok)$",
    r"^(来了|马上到|在路上|马上|等一下|稍等)$",
    r"^(走|吃饭|走吧|去吃饭|午饭|晚饭).*$",
    r"^\+1$",
]

_compiled = [re.compile(p, re.UNICODE) for p in NOISE_PATTERNS]


def _line_is_noise(line: str) -> bool:
    """判断单行消息是否为废话。"""
    # 提取消息内容（去掉时间戳和发送者前缀）
    m = re.match(r"^\[[\d:]+\]\s*\S+:\s*(.+)$", line.strip())
    text = m.group(1).strip() if m else line.strip()

    if not text:
        return True

    for pat in _compiled:
        if pat.match(text):
            return True

    # 过短的消息（<=3字，且不含实质内容）
    if len(text) <= 3 and not any(c.isdigit() for c in text):
        return True

    return False


def compute_noise_ratio(doc: RawDocument) -> float:
    """计算文档的废话比例。返回 0.0-1.0，越高越多废话。"""
    lines = [ln for ln in doc.content.split("\n") if ln.strip()]
    if not lines:
        return 1.0

    noise_count = sum(1 for ln in lines if _line_is_noise(ln))
    ratio = noise_count / len(lines)

    log.debug(
        "noise_ratio",
        doc_id=doc.doc_id,
        total_lines=len(lines),
        noise_lines=noise_count,
        ratio=round(ratio, 3),
    )
    return ratio


def is_noise_document(doc: RawDocument, threshold: float = 0.7) -> bool:
    """判断文档是否为噪声文档。

    两个维度：
    1. 聊天记录废话比例（原有逻辑）
    2. 是否与企业知识体系完全无关（新增）
    """
    content_lower = doc.title.lower()

    # 维度 1: 聊天记录废话过滤
    if "聊天" in content_lower or "群聊" in content_lower or "chat" in content_lower:
        ratio = compute_noise_ratio(doc)
        if ratio >= threshold:
            log.info(
                "noise_filter_chat_noise",
                doc_id=doc.doc_id,
                title=doc.title,
                noise_ratio=round(ratio, 3),
            )
            return True

    # 维度 2: 企业知识体系匹配检查
    # 如果文档内容完全匹配不到任何知识域关键词，标记为噪声
    if not _matches_any_domain(doc):
        log.info(
            "noise_filter_no_domain_match",
            doc_id=doc.doc_id,
            title=doc.title,
        )
        # 不直接判定噪声，但记录警告（宁可误留不可误删）
        # 后续由 Judge Agent 做最终决策

    return False


# 知识域关键词——用于快速判断文档是否属于企业知识体系
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "制度规范": ["制度", "规定", "管理办法", "规章", "政策", "准则", "规范", "条例"],
    "财务": ["报销", "费用", "差旅", "预算", "发票", "审批", "财务"],
    "人事": ["入职", "离职", "考勤", "绩效", "薪酬", "请假", "招聘", "培训", "试用期"],
    "行政": ["办公", "会议室", "印章", "物资", "行政"],
    "流程": ["流程", "步骤", "审批", "指南", "操作", "手册"],
    "技术": ["部署", "配置", "代码", "API", "Docker", "数据库", "服务器", "架构", "技术"],
    "项目": ["项目", "会议", "纪要", "OKR", "规划", "里程碑", "产品", "需求"],
    "安全": ["安全", "应急", "消防", "环保", "事故", "隐患", "防护"],
    "生产": ["生产", "工艺", "质量", "质检", "车间", "产线", "排产"],
    "设备": ["设备", "维修", "保养", "巡检", "故障", "维护"],
    "物流": ["物流", "仓储", "运输", "发货", "库存", "出入库"],
}


def _matches_any_domain(doc: RawDocument) -> bool:
    """检查文档是否匹配任何知识域关键词。"""
    text = (doc.title + " " + doc.content[:500]).lower()
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return True
    return False
