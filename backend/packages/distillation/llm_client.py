"""大模型 API 统一客户端 — 支持 OpenAI / Anthropic / Mock 模式。"""

from __future__ import annotations

import json
import re

from tenacity import retry, stop_after_attempt, wait_exponential

from packages.common import get_logger, settings
from packages.common.exceptions import LLMCallError

log = get_logger("llm_client")

_openai_client = None
_anthropic_client = None


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        import httpx

        # 睿动平台等部分 API 需要跳过 SSL 验证
        http_client = httpx.Client(verify=False)
        _openai_client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            http_client=http_client,
        )
    return _openai_client


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic

        _anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def _extract_json(text: str) -> dict:
    """从 LLM 回复中提取 JSON（兼容 markdown 代码块）。"""
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    text = text.strip()
    return json.loads(text)


# ── Mock LLM 引擎 ────────────────────────────────────

def _mock_llm_call(system_prompt: str, user_prompt: str) -> str:
    """基于规则的模拟 LLM — 根据 prompt 中的关键词生成合理的 JSON 响应。"""
    combined = system_prompt + user_prompt

    # Librarian Agent
    if "文档管理员" in system_prompt and "doc_type" in user_prompt:
        return _mock_librarian(user_prompt)

    # Conflict Auditor
    if "审计员" in system_prompt and "overlap_groups" in user_prompt:
        return _mock_auditor(user_prompt)

    # Judge Agent
    if "知识库管理专家" in system_prompt and "recency_analysis" in user_prompt:
        return _mock_judge(user_prompt)

    # Refiner Agent
    if "知识提炼专家" in system_prompt and "summary" in user_prompt:
        return _mock_refiner(user_prompt)

    # V8: SkillsRouter Stage 2
    if "知识体系路由专家" in system_prompt and "domain_path" in user_prompt:
        return _mock_skills_router(user_prompt)

    # LLM 知识路由
    if "路由专家" in system_prompt and "selected_domains" in user_prompt:
        return _mock_router(user_prompt)

    # QA 问答
    if "书虫" in system_prompt or "参考资料" in user_prompt:
        return _mock_qa(user_prompt)

    return '{"result": "mock response"}'


def _mock_librarian(prompt: str) -> str:
    """模拟 Librarian 的元数据提取。"""
    # 推断文档类型
    doc_type = "其他"
    if "制度" in prompt or "规定" in prompt or "管理" in prompt:
        doc_type = "规章制度"
    elif "会议" in prompt or "纪要" in prompt:
        doc_type = "会议纪要"
    elif "部署" in prompt or "技术" in prompt or "Docker" in prompt or "API" in prompt:
        doc_type = "技术文档"
    elif "流程" in prompt or "指南" in prompt or "入职" in prompt:
        doc_type = "流程说明"
    elif "通知" in prompt or "放假" in prompt:
        doc_type = "通知公告"
    elif "聊天" in prompt or "群聊" in prompt or "[" in prompt and "]" in prompt:
        doc_type = "聊天记录"

    # 推断版本
    version = None
    for pat in [r"v(\d+\.\d+)", r"V(\d+\.\d+)", r"(\d{4})版"]:
        m = re.search(pat, prompt)
        if m:
            version = m.group(0)
            break

    # 推断主题
    topics = []
    topic_keywords = {
        "报销": "报销管理", "财务": "财务管理", "入职": "入职流程",
        "产品": "产品规划", "部署": "技术部署", "Docker": "容器化部署",
        "放假": "行政通知", "选型": "技术选型", "向量": "向量数据库",
    }
    for kw, topic in topic_keywords.items():
        if kw in prompt:
            topics.append(topic)
    if not topics:
        topics = ["企业管理"]

    # 推断实体
    entities = []
    entity_patterns = [
        (r"(张\w{1,2}|李\w{1,2}|王\w{1,2}|赵\w{1,2}|刘\w{1,2}|陈\w{1,2})", "人物"),
        (r"(财务部|技术部|产品部|人事部|行政部|人力资源部)", "部门"),
        (r"(书虫|Milvus|Neo4j|Docker)", "项目"),
    ]
    for pat, etype in entity_patterns:
        for m in re.finditer(pat, prompt):
            entities.append({"name": m.group(1), "type": etype})
    # 去重
    seen = set()
    unique_entities = []
    for e in entities:
        key = e["name"]
        if key not in seen:
            seen.add(key)
            unique_entities.append(e)

    is_conv = doc_type == "聊天记录"
    value = "LOW" if doc_type in ("通知公告", "聊天记录") else "HIGH" if doc_type == "规章制度" else "MEDIUM"

    return json.dumps({
        "doc_type": doc_type,
        "version_id": version,
        "key_topics": topics[:3],
        "mentioned_entities": unique_entities[:5],
        "is_conversational": is_conv,
        "estimated_value": value,
    }, ensure_ascii=False)


def _mock_auditor(prompt: str) -> str:
    """模拟 Conflict Auditor 的冲突检测。"""
    # 检查是否有多个文档
    doc_ids = re.findall(r"ID:\s*(feishu_doc_\d+)", prompt)
    overlap_groups = []
    conflicts = []

    if len(doc_ids) >= 2:
        # 检查是否有版本迭代（同一主题不同版本）
        if "v2.0" in prompt and "v3.0" in prompt:
            overlap_groups.append({
                "doc_ids": doc_ids[:2],
                "overlap_type": "版本迭代",
                "description": "两个文档为同一制度的不同版本，v3.0 为最新版本",
                "recommended_primary": doc_ids[0],  # 假设第一个是较新的
            })

    return json.dumps({
        "overlap_groups": overlap_groups,
        "conflicts": conflicts,
        "summary": f"审计了 {len(doc_ids)} 篇文档，发现 {len(overlap_groups)} 组重叠。",
    }, ensure_ascii=False)


def _mock_judge(prompt: str) -> str:
    """模拟 Judge Agent 的价值评估。"""
    decision = "KEEP"
    confidence = 0.85
    recency_score = 7.0
    density_score = 7.0
    completeness_score = 7.0
    redundancy_score = 7.0
    summary = "该文档包含有效的企业知识内容，建议保留。"

    # 过时通知 → DISCARD
    if "2024年元旦" in prompt or "放假安排" in prompt:
        decision = "DISCARD"
        confidence = 0.95
        recency_score = 1.0
        density_score = 3.0
        redundancy_score = 2.0
        summary = "该文档为2024年元旦放假通知，已完全过时，建议剔除。"

    # 旧版本制度 → ARCHIVE
    elif "v2.0" in prompt and ("v3.0" in prompt or "已被" in prompt or "版本迭代" in prompt):
        decision = "ARCHIVE"
        confidence = 0.90
        recency_score = 3.0
        redundancy_score = 3.0
        summary = "该文档为旧版本制度，已被新版本替代，建议归档保留历史参考。"
    elif "v2.0" in prompt and "报销" in prompt:
        decision = "ARCHIVE"
        confidence = 0.88
        recency_score = 3.0
        redundancy_score = 3.0
        summary = "报销制度 v2.0 已有 v3.0 替代，归档作历史参考。"

    # 有实质内容的群聊记录 → KEEP
    elif "聊天" in prompt and ("选型" in prompt or "Milvus" in prompt or "方案" in prompt):
        decision = "KEEP"
        confidence = 0.75
        density_score = 6.0
        summary = "群聊中含有技术选型讨论的实质内容，建议保留。"

    # 正式文档 → KEEP
    elif any(kw in prompt for kw in ["制度", "流程", "指南", "v3.0"]):
        decision = "KEEP"
        confidence = 0.92
        density_score = 9.0
        completeness_score = 8.0
        summary = "正式的企业规章/流程文档，信息密度高，建议保留。"

    # 会议纪要 → KEEP
    elif "会议" in prompt or "纪要" in prompt:
        decision = "KEEP"
        confidence = 0.80
        density_score = 7.0
        summary = "会议纪要包含项目规划和任务分配，建议保留。"

    # 技术文档 → KEEP
    elif "部署" in prompt or "Docker" in prompt:
        decision = "KEEP"
        confidence = 0.88
        density_score = 8.0
        summary = "技术部署文档，含实质性操作指导，建议保留。"

    # 提取关键实体
    key_entities = []
    for pat in [r"(张\w{1,2}|李\w{1,2}|王\w{1,2}|赵\w{1,2})", r"(财务部|技术部|产品部|人事部)"]:
        for m in re.finditer(pat, prompt):
            if m.group(1) not in key_entities:
                key_entities.append(m.group(1))

    return json.dumps({
        "reasoning": {
            "recency_analysis": f"时效性评估：评分 {recency_score}",
            "recency_score": recency_score,
            "density_analysis": f"信息密度评估：评分 {density_score}",
            "density_score": density_score,
            "completeness_analysis": f"完整性评估：评分 {completeness_score}",
            "completeness_score": completeness_score,
            "redundancy_analysis": f"独特性评估：评分 {redundancy_score}",
            "redundancy_score": redundancy_score,
        },
        "decision": decision,
        "confidence": confidence,
        "summary": summary,
        "key_entities": key_entities[:5],
    }, ensure_ascii=False)


def _mock_infer_domain_id(prompt: str, title_text: str = "") -> str:
    """V8: 从文档内容推断 domain_id（Mock模式）。"""
    # 优先从标题+正文前500字推断，避免 prompt 模板中的干扰词
    content_start = prompt.find("## 完整正文")
    if content_start > 0:
        content_part = prompt[content_start:content_start + 500]
    else:
        content_part = prompt[:500]
    text = title_text + " " + content_part
    # 能源行业知识体系匹配（优先精确路径）
    if any(kw in text for kw in ["隐患", "安全检查", "安全隐患"]):
        return "energy/safety/hazard"
    if any(kw in text for kw in ["安全培训", "安全教育", "特种作业"]):
        return "energy/safety/training"
    if any(kw in text for kw in ["作业许可", "动火", "高处作业", "受限空间"]):
        return "energy/safety/permit"
    if any(kw in text for kw in ["安全", "安全生产", "安全管理"]):
        return "energy/safety"
    if any(kw in text for kw in ["环保", "环境", "排放", "废水", "废气"]):
        return "energy/environment"
    if any(kw in text for kw in ["设备", "检修", "维护", "维修"]):
        return "energy/production/equipment"
    if any(kw in text for kw in ["生产", "运行", "工艺", "操作规程"]):
        return "energy/production"
    if any(kw in text for kw in ["应急", "救援", "预案"]):
        return "energy/emergency"
    if any(kw in text for kw in ["物流", "仓储", "运输", "配送"]):
        return "energy/logistics"
    if any(kw in text for kw in ["采购", "供应商", "招标"]):
        return "energy/procurement"
    # 从 Refiner prompt 的知识域列表中匹配
    if "## 可用知识域" in prompt or "L1" in prompt:
        domain_lines = re.findall(r"\[([^\]]+)\]:\s*(.+?)(?:\n|$)", prompt)
        for did, dname in domain_lines:
            name_part = dname.split("—")[0].strip()
            if any(kw in text[:2000] for kw in name_part.split() if len(kw) >= 2):
                return did
    # 通用企业模板
    if any(kw in text for kw in ["报销", "费用", "差旅", "采购"]):
        return "regulation/finance"
    if any(kw in text for kw in ["入职", "离职", "考勤", "人事"]):
        return "regulation/hr"
    if any(kw in text for kw in ["架构", "选型", "技术方案"]):
        return "tech/architecture"
    if any(kw in text for kw in ["部署", "Docker", "运维", "服务器"]):
        return "tech/deploy"
    if any(kw in text for kw in ["API", "接口文档"]):
        return "tech/api"
    if any(kw in text for kw in ["Sprint", "迭代"]):
        return "project/sprint"
    if any(kw in text for kw in ["制度", "规定", "管理办法"]):
        return "regulation"
    if any(kw in text for kw in ["产品", "功能", "需求"]):
        return "product"
    if any(kw in text for kw in ["技术", "代码", "开发"]):
        return "tech"
    if any(kw in text for kw in ["项目", "会议", "纪要"]):
        return "project"
    return "regulation"


def _mock_refiner(prompt: str) -> str:
    """模拟 Refiner Agent 的知识提炼。"""
    title = re.search(r"标题:\s*(.+)", prompt)
    title_text = title.group(1).strip() if title else "未知文档"

    # 生成摘要
    content_start = prompt.find("## 完整正文")
    if content_start > 0:
        raw_content = prompt[content_start + 20:content_start + 300]
    else:
        raw_content = prompt[:200]

    summary = f"本文档为《{title_text}》，" + raw_content[:120].replace("\n", " ").strip()
    if len(summary) > 200:
        summary = summary[:197] + "..."

    # 提取关键词
    keywords = []
    keyword_candidates = [
        "报销", "流程", "制度", "入职", "部署", "Docker", "产品", "会议",
        "审批", "权限", "数据库", "向量", "Milvus", "知识库", "OKR",
        "试用期", "培训", "监控", "服务器", "员工",
    ]
    for kw in keyword_candidates:
        if kw in prompt:
            keywords.append(kw)

    # 提取实体（V8: 扩展8种类型，增加能源行业实体识别）
    entities = []
    for pat, etype in [
        (r"(张\w{1,2}|李\w{1,2}|王\w{1,2}|赵\w{1,2}|刘\w{1,2}|陈\w{1,2}|班组长|总经理|技术负责人|仓库管理员|采购员)", "人物"),
        (r"(财务部|技术部|产品部|人事部|行政部|人力资源部|安全生产部|生产运行部|设备管理部|环保管理部|应急管理部|物流管理部|采购管理部|调度中心|消防队)", "部门"),
        (r"(书虫项目|Milvus|Neo4j|Docker Compose)", "项目"),
        # V8: 能源行业实体
        (r"(安全生产法|环境保护法|突发事件应对法|消防法|危险化学品安全管理条例)", "标准规范"),
        (r"(安全隐患|隐患排查|安全培训|应急演练|安全检查|安全生产|日常巡检)", "流程工艺"),
        (r"(排放指标|排放达标|环保要求|废水处理|废气处理)", "流程工艺"),
        (r"(生产设备|在线监测系统|运输车辆|消防设施|防护装备)", "设备装置"),
        (r"(危险化学品|原材料|成品油|天然气)", "物料化学品"),
        (r"(生产车间|仓库|泵房|罐区|码头)", "位置区域"),
    ]:
        for m in re.finditer(pat, prompt):
            entities.append({"name": m.group(1), "type": etype})

    # 去重
    seen = set()
    unique = []
    for e in entities:
        if e["name"] not in seen:
            seen.add(e["name"])
            unique.append(e)

    # 提前计算 domain_id（在关系生成之前需要）
    domain_id = _mock_infer_domain_id(prompt, title_text)

    # 提取关系 — V8: 优先使用能源行业分支关系模板
    relations = []
    entity_names = [e["name"] for e in unique]

    # V8: 尝试匹配能源行业分支模板（确保每篇文档≥5条关系）
    energy_relations = _mock_generate_energy_relations(title_text, prompt, domain_id)
    for er in energy_relations:
        # 确保端点实体存在
        for name in (er["source"], er["target"]):
            if name not in entity_names:
                # 推断类型
                etype = "部门" if any(kw in name for kw in ["部", "中心", "队"]) else \
                        "人物" if any(kw in name for kw in ["长", "员", "人"]) else \
                        "标准规范" if "法" in name or "条例" in name else \
                        "流程工艺"
                unique.append({"name": name, "type": etype})
                entity_names.append(name)
        relations.append(er)

    # 自动推断：人物↔部门、人物↔项目、部门↔流程
    dept_ents = [e for e in unique if e["type"] in ("部门",)]
    person_ents = [e for e in unique if e["type"] in ("人物",)]
    for p in person_ents:
        for d in dept_ents[:2]:
            relations.append({"source": p["name"], "relation": "所属", "target": d["name"]})

    # 显式规则（兼容旧逻辑）
    if "财务部" in prompt and "报销" in prompt:
        relations.append({"source": "财务部", "relation": "负责", "target": "报销管理"})
    if "人力资源部" in prompt or "人事部" in prompt:
        dept = "人力资源部" if "人力资源部" in prompt else "人事部"
        relations.append({"source": dept, "relation": "负责", "target": "入职流程"})

    # 关键词派生的流程实体关系
    process_keywords = {"报销": "报销流程", "入职": "入职流程", "审批": "审批流程",
                        "部署": "部署流程", "培训": "培训流程", "监控": "运维监控"}
    for kw, process_name in process_keywords.items():
        if kw in prompt:
            if process_name not in entity_names:
                unique.append({"name": process_name, "type": "流程工艺"})
                entity_names.append(process_name)
            for d in dept_ents[:1]:
                relations.append({"source": d["name"], "relation": "执行", "target": process_name})

    # 去重关系
    seen_rels = set()
    deduped_rels = []
    for r in relations:
        key = (r["source"], r["relation"], r["target"])
        if key not in seen_rels:
            seen_rels.add(key)
            deduped_rels.append(r)
    relations = deduped_rels

    # domain_id 已在前面通过 _mock_infer_domain_id() 计算
    # 旧的 elif 通用匹配链已废弃（V8 由 _mock_infer_domain_id 统一处理）

    # 生成文档描述（给 LLM 路由读的）
    doc_description = f"本文档《{title_text}》" + summary[:100]

    # 提取关键要素
    key_elements = []
    if keywords:
        key_elements = [f"涉及{kw}" for kw in keywords[:5]]

    return json.dumps({
        "summary": summary,
        "catalog": [
            {"level": 1, "title": title_text, "brief": summary[:80], "key_terms": keywords[:3]}
        ],
        "index_text": f"文档《{title_text}》 {summary} 关键词：{'、'.join(keywords[:5])}",
        "keywords": keywords[:10],
        "entities": unique[:8],
        "relations": relations[:5],
        "domain_id": domain_id,
        "doc_description": doc_description,
        "key_elements": key_elements,
    }, ensure_ascii=False)


# ── V8: 能源行业分支关系模板 ───────────────────────────
_ENERGY_RELATION_TEMPLATES: dict[str, list[tuple[str, str, str]]] = {
    "安全": [
        ("{doc_title}", "依据", "安全生产法"),
        ("安全生产部", "编制", "{doc_title}"),
        ("安全生产部", "负责", "安全生产管理"),
        ("总经理", "审批", "{doc_title}"),
        ("各部门", "执行", "{doc_title}"),
        ("安全隐患", "适用于", "{doc_title}"),
    ],
    "生产": [
        ("生产运行部", "管理", "生产设备"),
        ("{doc_title}", "规范", "操作流程"),
        ("班组长", "执行", "日常巡检"),
        ("生产运行部", "编制", "{doc_title}"),
        ("调度中心", "协调", "生产计划"),
        ("生产运行部", "负责", "生产管理"),
    ],
    "环保": [
        ("环保管理部", "监督", "排放达标"),
        ("{doc_title}", "依据", "环境保护法"),
        ("环保管理部", "编制", "{doc_title}"),
        ("各生产车间", "执行", "环保要求"),
        ("在线监测系统", "监控", "排放指标"),
        ("环保管理部", "负责", "环保管理"),
    ],
    "设备": [
        ("设备管理部", "管理", "设备档案"),
        ("维修班组", "执行", "设备维护"),
        ("{doc_title}", "规范", "设备检修"),
        ("设备管理部", "编制", "{doc_title}"),
        ("技术负责人", "审核", "维修方案"),
        ("设备管理部", "负责", "设备管理"),
    ],
    "应急": [
        ("应急管理部", "编制", "{doc_title}"),
        ("{doc_title}", "依据", "突发事件应对法"),
        ("应急指挥部", "指挥", "应急救援"),
        ("各部门", "参与", "应急演练"),
        ("消防队", "执行", "现场处置"),
        ("应急管理部", "负责", "应急管理"),
    ],
    "物流": [
        ("物流管理部", "编制", "{doc_title}"),
        ("仓库管理员", "执行", "出入库管理"),
        ("{doc_title}", "规范", "物流流程"),
        ("物流管理部", "负责", "物流管理"),
        ("运输车辆", "执行", "配送任务"),
    ],
    "采购": [
        ("采购管理部", "编制", "{doc_title}"),
        ("采购员", "执行", "采购流程"),
        ("{doc_title}", "规范", "供应商管理"),
        ("采购管理部", "负责", "采购管理"),
        ("财务部", "审核", "采购申请"),
    ],
}


def _mock_generate_energy_relations(doc_title: str, content: str, domain_id: str) -> list[dict]:
    """V8: 为能源行业文档生成分支关系（Mock模式）。确保每篇文档≥5条关系。"""
    for keyword, templates in _ENERGY_RELATION_TEMPLATES.items():
        if keyword in domain_id or keyword in doc_title or keyword in content[:500]:
            return [
                {
                    "source": t[0].replace("{doc_title}", doc_title),
                    "relation": t[1],
                    "target": t[2].replace("{doc_title}", doc_title),
                }
                for t in templates
            ]
    # 默认通用模板
    return [
        {"source": "管理部门", "relation": "编制", "target": doc_title},
        {"source": doc_title, "relation": "规范", "target": "业务流程"},
        {"source": "相关人员", "relation": "执行", "target": doc_title},
        {"source": "负责人", "relation": "审批", "target": doc_title},
        {"source": doc_title, "relation": "适用于", "target": "相关部门"},
    ]


def _mock_skills_router(prompt: str) -> str:
    """V8: 模拟 SkillsRouter Stage 2 的 LLM 路径定位。"""
    # 从候选路径中选第一个
    candidates = re.findall(r"\[([^\]]+)\]", prompt)
    domain_path = candidates[0] if candidates else ""
    return json.dumps({
        "domain_path": domain_path,
        "reasoning": f"Mock: 选择第一个候选路径 {domain_path}",
    }, ensure_ascii=False)


def _mock_router(prompt: str) -> str:
    """模拟 LLM 知识路由 — 基于关键词匹配知识域，并尝试定位具体文档。"""
    query_lower = prompt.lower()

    # 关键词 → 知识域映射（适配通用企业模板）
    _ROUTE_RULES: list[tuple[list[str], str]] = [
        (["prd", "需求文档", "产品需求", "功能规格"], "product/prd"),
        (["路线图", "用户故事", "产品规划"], "product/roadmap"),
        (["竞品", "竞争", "对比", "市场分析"], "product/competitive"),
        (["架构", "选型", "技术方案"], "tech/architecture"),
        (["部署", "docker", "运维", "安装", "服务器", "现场部署"], "tech/deploy"),
        (["api", "接口文档", "接口"], "tech/api"),
        (["sprint", "迭代", "评审"], "project/sprint"),
        (["里程碑", "okr", "项目计划"], "project/milestone"),
        (["测试计划", "测试报告", "bug", "缺陷", "测试"], "quality/testing"),
        (["验收", "验收标准", "验收测试"], "quality/acceptance"),
        (["客户需求", "客户反馈", "需求对接", "反馈意见"], "customer/requirements"),
        (["销售", "周报", "市场需求", "商机"], "customer/sales"),
        (["报销", "费用", "差旅", "采购", "财务"], "regulation/finance"),
        (["入职", "离职", "考勤", "人事"], "regulation/hr"),
        (["制度", "规定", "管理办法"], "regulation"),
        (["产品", "功能", "需求"], "product"),
        (["技术", "代码", "开发"], "tech"),
        (["项目", "会议", "纪要", "进展"], "project"),
        (["质量", "准确率"], "quality"),
        (["客户", "市场"], "customer"),
    ]

    selected = []
    for keywords, domain_id in _ROUTE_RULES:
        if any(kw in query_lower for kw in keywords):
            if not any(domain_id.startswith(s + "/") or s.startswith(domain_id + "/") for s in selected):
                selected.append(domain_id)
            if len(selected) >= 3:
                break

    if not selected:
        selected = ["regulation"]

    # 尝试从目录树文本中提取具体文档 ID
    doc_ids = []
    # 在 prompt 中查找 [doc_id] 格式的文档引用，匹配与查询关键词相关的
    import re
    doc_entries = re.findall(r'\[(\w+_doc_\d+)\]\s*(.+?)(?:\n|$)', prompt)
    for doc_id, doc_context in doc_entries:
        doc_text = doc_context.lower()
        if any(kw in query_lower and kw in doc_text for kw in
               ["报销", "费用", "入职", "部署", "产品", "会议", "培训", "流程", "制度",
                "安全", "设备", "生产", "物流", "审批", "docker", "技术", "okr"]):
            doc_ids.append(doc_id)
        if len(doc_ids) >= 5:
            break

    return json.dumps({
        "selected_domains": selected,
        "selected_doc_ids": doc_ids,
        "reasoning": f"根据关键词匹配，选择了 {', '.join(selected)}，定位到 {len(doc_ids)} 篇文档。",
    }, ensure_ascii=False)


def _mock_qa(prompt: str) -> str:
    """模拟 QA 回答生成。"""
    if "参考资料" in prompt:
        # 提取参考资料内容
        refs = re.findall(r"\[\d+\]\s*来源：(.+?)\n\s*内容：(.+?)(?=\n\[|\n##|$)", prompt, re.DOTALL)
        if refs:
            source_titles = [r[0].strip() for r in refs]
            answer = f"根据检索到的资料（{', '.join(source_titles[:3])}），"
            # 从参考资料中提取关键信息
            all_content = " ".join(r[1].strip()[:200] for r in refs)
            answer += all_content[:300]
            return answer

    return "根据企业知识库中的资料，暂未找到与您问题完全匹配的内容。建议查阅相关部门的最新文档。"


# ── 对外接口 ──────────────────────────────────────────

def _has_valid_api_key() -> bool:
    """检查当前 provider 是否配置了有效的 API Key。"""
    provider = settings.llm_provider
    if provider == "openai":
        return bool(settings.openai_api_key and settings.openai_api_key.strip())
    elif provider == "anthropic":
        return bool(settings.anthropic_api_key and settings.anthropic_api_key.strip())
    return False


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> str:
    """调用大模型并返回文本响应。

    当 provider 为 mock 或 API Key 未配置时，自动使用 Mock 模式。
    当 API 调用失败时，降级到 Mock 模式并记录警告。
    """
    provider = settings.llm_provider
    model = model or settings.llm_model

    # Mock 模式：显式配置或无有效 API Key
    if provider == "mock" or not _has_valid_api_key():
        if provider != "mock":
            log.warning("llm_no_api_key_fallback_mock", provider=provider)
        else:
            log.debug("llm_mock_call")
        return _mock_llm_call(system_prompt, user_prompt)

    try:
        if provider == "openai":
            client = _get_openai()
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=60,
            )
            return resp.choices[0].message.content or ""

        elif provider == "anthropic":
            client = _get_anthropic()
            resp = client.messages.create(
                model=model,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=10,
            )
            return resp.content[0].text

        else:
            raise LLMCallError(f"不支持的 LLM provider: {provider}")

    except Exception as e:
        log.warning(
            "llm_call_failed_fallback_mock",
            provider=provider,
            model=model,
            error=str(e),
        )
        return _mock_llm_call(system_prompt, user_prompt)


def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.1,
) -> dict:
    """调用大模型并解析 JSON 响应。"""
    raw = call_llm(system_prompt, user_prompt, model=model, temperature=temperature)
    try:
        return _extract_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("llm_json_parse_failed", raw_length=len(raw), error=str(e))
        raise LLMCallError(f"JSON 解析失败: {e}\n原始回复: {raw[:500]}") from e
