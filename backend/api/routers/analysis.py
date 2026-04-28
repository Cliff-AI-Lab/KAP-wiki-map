"""智能分析 API — 基于已有数据生成分析报告。"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from fastapi import APIRouter, Query

from api.deps import get_domain_store, get_graph_store, get_metadata_store

router = APIRouter(prefix="/analysis", tags=["智能分析"])


@router.get("")
async def get_analysis(
    project_id: str = Query(default="default", description="项目ID"),
) -> dict:
    """生成项目的智能分析报告。

    包含：行业识别、重复检测、版本链、质量分布、知识缺口。
    """
    meta = get_metadata_store()
    domain_store = get_domain_store()
    graph = get_graph_store()

    docs = await meta.list_documents(org_id=project_id)
    domains = domain_store.list_domains(project_id=project_id)

    # 1. 行业识别（基于项目的 industry_code）
    from api.deps import get_project_store
    ps = get_project_store()
    proj = ps._projects.get(project_id, {})
    industry_code = proj.get("industry_code", "generic")
    industry_detection = _detect_industry(docs, industry_code)

    # 2. 重复/相似文档检测
    duplicate_groups = _detect_duplicates(docs)

    # 3. 版本链识别
    version_chains = _detect_version_chains(docs)

    # 4. 质量分布
    quality_stats = _compute_quality_stats(docs)

    # 5. 知识缺口分析
    knowledge_gaps = _analyze_gaps(docs, domains)

    return {
        "industryDetection": industry_detection,
        "duplicateGroups": duplicate_groups,
        "versionChains": version_chains,
        "qualityStats": quality_stats,
        "knowledgeGaps": knowledge_gaps,
    }


def _detect_industry(docs: list[dict], industry_code: str) -> dict:
    """基于项目配置和文档内容推断行业。"""
    industry_names = {
        "energy": "能源电力", "manufacturing": "制造业",
        "it": "信息技术", "finance": "金融", "healthcare": "医疗健康",
        "generic": "通用",
    }
    detected = industry_names.get(industry_code, "通用")

    # 基于文档关键词统计各行业相关度
    industry_keywords = {
        "能源电力": ["电力", "能源", "锅炉", "发电", "变压", "电网", "输电", "新能源", "光伏"],
        "制造业": ["生产", "质检", "工艺", "设备", "模具", "制造", "产线", "良率"],
        "信息技术": ["系统", "API", "代码", "架构", "开发", "部署", "服务器", "数据库"],
        "金融": ["风险", "合规", "交易", "信贷", "保险", "基金", "证券", "银行"],
        "医疗健康": ["临床", "诊断", "药品", "护理", "患者", "医疗", "手术", "处方"],
    }

    all_text = " ".join(d.get("title", "") + " " + (d.get("summary") or "") for d in docs)
    scores = {}
    for ind, kws in industry_keywords.items():
        scores[ind] = sum(all_text.count(kw) for kw in kws)

    total = sum(scores.values()) or 1
    confidence = scores.get(detected, 0) / total if detected in scores else 0.5

    return {
        "detected": detected,
        "confidence": max(confidence, 0.5),
        "scores": {k: v for k, v in sorted(scores.items(), key=lambda x: -x[1]) if v > 0},
    }


def _detect_duplicates(docs: list[dict]) -> list[dict]:
    """基于标题相似度检测重复文档。"""
    groups = []
    seen = set()

    for i, d1 in enumerate(docs):
        if d1["id"] in seen:
            continue
        title1 = _normalize_title(d1.get("title", ""))
        cluster = [d1["title"]]
        for d2 in docs[i + 1:]:
            if d2["id"] in seen:
                continue
            title2 = _normalize_title(d2.get("title", ""))
            sim = _title_similarity(title1, title2)
            if sim >= 0.7:
                cluster.append(d2["title"])
                seen.add(d2["id"])
        if len(cluster) >= 2:
            seen.add(d1["id"])
            is_exact = all(_normalize_title(t) == title1 for t in cluster)
            groups.append({
                "id": f"dup_{len(groups)+1:03d}",
                "type": "exact" if is_exact else "similar",
                "similarity": 1.0 if is_exact else 0.85,
                "documents": cluster,
            })

    return groups


def _detect_version_chains(docs: list[dict]) -> list[dict]:
    """检测文档版本链。"""
    version_pattern = re.compile(r"[vV](\d+(?:\.\d+)*)")
    date_pattern = re.compile(r"(\d{4}[-/]?\d{2}[-/]?\d{2})")

    base_groups: dict[str, list[dict]] = defaultdict(list)
    for d in docs:
        title = d.get("title", "")
        # 去掉版本号和日期，得到基础名
        base = version_pattern.sub("", title)
        base = date_pattern.sub("", base)
        base = re.sub(r"[_\-\s.]+$", "", base).strip()
        if not base:
            continue

        ver_match = version_pattern.search(title)
        date_match = date_pattern.search(title)
        version = ver_match.group(1) if ver_match else (date_match.group(1) if date_match else "1.0")

        base_groups[base].append({
            "name": title, "version": version,
        })

    chains = []
    for base, versions in base_groups.items():
        if len(versions) < 2:
            continue
        versions.sort(key=lambda v: v["version"], reverse=True)
        for i, v in enumerate(versions):
            v["isLatest"] = (i == 0)
        chains.append({"baseName": base, "versions": versions})

    return chains


def _compute_quality_stats(docs: list[dict]) -> dict:
    """基于 KPI 分数计算质量分布。"""
    scores = []
    issues: Counter = Counter()

    for d in docs:
        kpi = d.get("kpi_retain")
        if kpi is not None:
            pct = round(kpi * 100)
            scores.append(pct)
        else:
            scores.append(50)

        summary = d.get("summary") or ""
        title = d.get("title") or ""
        if len(summary) < 20:
            issues["内容过短或无摘要"] += 1
        if not any(c.isalpha() for c in title):
            issues["标题不规范"] += 1
        if d.get("decision") == "ARCHIVE":
            issues["文档已过期或冗余"] += 1

    avg = sum(scores) / len(scores) if scores else 0
    dist = {
        "优秀(90-100)": sum(1 for s in scores if s >= 90),
        "良好(75-89)": sum(1 for s in scores if 75 <= s < 90),
        "一般(60-74)": sum(1 for s in scores if 60 <= s < 75),
        "较差(<60)": sum(1 for s in scores if s < 60),
    }

    return {
        "avgScore": round(avg, 1),
        "distribution": dist,
        "commonIssues": [{"issue": k, "count": v} for k, v in issues.most_common(5)],
    }


def _analyze_gaps(docs: list[dict], domains: list) -> list[dict]:
    """分析知识缺口：哪些域没有文档或文档很少。"""
    # 统计每个顶层域的文档数
    domain_doc_counts: Counter = Counter()
    for d in docs:
        cat = d.get("category_path", "")
        top = cat.split("/")[0] if cat else "未分类"
        domain_doc_counts[top] += 1

    # 找出有域定义但文档少的
    gaps = []
    top_domains = [d for d in domains if not d.parent_id or d.parent_id == ""]
    for dom in top_domains:
        count = dom.doc_count
        if count <= 1:
            priority = "high" if count == 0 else "medium"
            gaps.append({
                "domain": dom.name,
                "domain_id": dom.domain_id,
                "doc_count": count,
                "priority": priority,
                "suggestion": f"「{dom.name}」领域{'无文档' if count == 0 else '仅1篇文档'}，建议补充",
            })

    return sorted(gaps, key=lambda g: {"high": 0, "medium": 1, "low": 2}.get(g["priority"], 2))


def _normalize_title(title: str) -> str:
    """标题归一化：去掉版本号、日期、扩展名、特殊字符。"""
    t = re.sub(r"[vV]\d+(\.\d+)*", "", title)
    t = re.sub(r"\d{4}[-/]?\d{2}[-/]?\d{2}", "", t)
    t = re.sub(r"\.(docx?|pdf|txt|md|xlsx?)$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[\s_\-()（）\[\]]+", "", t)
    return t.lower()


def _title_similarity(a: str, b: str) -> float:
    """简单的字符级 Jaccard 相似度。"""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0
