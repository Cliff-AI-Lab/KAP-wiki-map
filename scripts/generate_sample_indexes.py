"""为 test-samples/ 下所有非 .md 文件生成同名 .md 索引页。

目的：让 Obsidian 默认配置（仅索引 .md）也能看到所有 48 份测试样本作为图谱节点，
不依赖用户开启 "Detect all file extensions"。

每个索引页含：
- frontmatter（type / industry / subset / domain / source-file）
- markdown link 指向原文件（让用户从 Obsidian 直接打开）
- 反向链接到行业 README、测试样例总入口、KAP 项目首页、决策书 §7
- 主题域标注（按本子集 README 的清单）

原 .md 文件不动（用户已经能看到它们，且修改正文内容有风险）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / ".kap-delegate" / "logs" / "generate_sample_indexes.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
_log = open(LOG_PATH, "w", encoding="utf-8")


def out(msg: str) -> None:
    _log.write(msg + "\n")
    _log.flush()


# 行业 → 配套模板路径
TEMPLATE_MAP = {
    "energy": "backend/templates/energy/",
    "manufacturing": "backend/templates/manufacturing/",
    "finance": "backend/templates/_default/",  # 暂用 _default
    "it": "backend/templates/_default/",
}

# 行业 → 决策书章节
DECISION_SECTION = {
    "energy": "§7.2",
    "manufacturing": "§7.1",
    "finance": "§1.3 第二批扩展",
    "it": "§7.4",
}

# 子集说明
SUBSET_DESC = {
    "v7-baseline": "V7 早期完整集（18 份混合 txt/md/docx，覆盖能源 6 个一级业务域）",
    "v12-revised": "V12 精简标准基线（10 份，能源核心十大主题）",
    "v15-extra": "V15 增补真实场景集（5 份多格式 pdf/html/docx/md/txt）",
    "": "",  # 平铺行业（manufacturing/finance/it）
}


def detect_industry_and_subset(path: Path) -> tuple[str, str]:
    """从路径推断 industry / subset。

    test-samples/energy/v7-baseline/01_xxx.txt → ("energy", "v7-baseline")
    test-samples/manufacturing/xxx.txt → ("manufacturing", "")
    """
    parts = path.relative_to(ROOT / "test-samples").parts
    if len(parts) == 0:
        return "", ""
    industry = parts[0]
    subset = parts[1] if len(parts) >= 3 and parts[1] in SUBSET_DESC else ""
    return industry, subset


def relative_to_industry_readme(sample_path: Path) -> str:
    """从样本到行业 README.md 的相对路径（用于 markdown link）。"""
    industry, subset = detect_industry_and_subset(sample_path)
    if subset:
        # samples/energy/v7-baseline/x.txt → ../README.md
        return "../README.md"
    return "./README.md"


def relative_to_root_readme(sample_path: Path) -> str:
    """从样本到 KAP 项目首页 README.md 的相对路径。"""
    industry, subset = detect_industry_and_subset(sample_path)
    if subset:
        # 4 级深 → ../../../README.md
        return "../../../README.md"
    # 3 级深 → ../../README.md
    return "../../README.md"


def relative_to_samples_root(sample_path: Path) -> str:
    """到 test-samples/README.md 的相对路径。"""
    industry, subset = detect_industry_and_subset(sample_path)
    if subset:
        return "../../README.md"
    return "../README.md"


def relative_to_decision_book(sample_path: Path) -> str:
    """到 docs/01-技术决策书.md 的相对路径。"""
    industry, subset = detect_industry_and_subset(sample_path)
    if subset:
        return "../../../docs/01-技术决策书.md"
    return "../../docs/01-技术决策书.md"


def relative_to_template(sample_path: Path) -> str:
    """到配套行业模板目录的相对路径。"""
    industry, subset = detect_industry_and_subset(sample_path)
    template_rel = TEMPLATE_MAP.get(industry, "backend/templates/_default/")
    if subset:
        return f"../../../{template_rel}"
    return f"../../{template_rel}"


def make_wrapper(sample_path: Path) -> str:
    """生成 .md 索引页内容。"""
    name = sample_path.stem
    suffix = sample_path.suffix
    industry, subset = detect_industry_and_subset(sample_path)
    section = DECISION_SECTION.get(industry, "§7")
    subset_desc = SUBSET_DESC.get(subset, "")

    # frontmatter
    fm_lines = [
        "---",
        f"title: {name}",
        "type: kap-test-sample",
        f"industry: {industry}",
    ]
    if subset:
        fm_lines.append(f"subset: {subset}")
    fm_lines.append(f"source-format: {suffix.lstrip('.')}")
    fm_lines.append(f"source-file: {sample_path.name}")
    fm_lines.append("---")

    # navigation
    nav_links = [
        f"[← 行业 README]({relative_to_industry_readme(sample_path)})",
        f"[← 测试样例总入口]({relative_to_samples_root(sample_path)})",
        f"[← 项目首页]({relative_to_root_readme(sample_path)})",
        f"[决策书 {section}]({relative_to_decision_book(sample_path)})",
    ]

    # body
    body_lines = [
        "",
        f"# {name}",
        "",
        "> 导航：" + " · ".join(nav_links),
        "",
        f"## 文件信息",
        "",
        f"- **行业**：{industry}",
    ]
    if subset:
        body_lines.append(f"- **子集**：{subset}（{subset_desc}）")
    body_lines.extend([
        f"- **原始格式**：`{suffix}`",
        f"- **原文件**：[{sample_path.name}](./{sample_path.name})",
        "",
        "## 用途",
        "",
        f"KAP 测试样例集 · 用于 W1-W6 工位测试、行业模板验证、跨行业冲突识别等场景。",
        f"详见 [行业 README]({relative_to_industry_readme(sample_path)}) 的推荐测试组合。",
        "",
        "## 配套",
        "",
        f"- [行业模板包]({relative_to_template(sample_path)})",
        f"- [决策书 {section} 标准锚定]({relative_to_decision_book(sample_path)})",
        "",
    ])

    return "\n".join(fm_lines + body_lines)


def main() -> int:
    test_root = ROOT / "test-samples"
    if not test_root.exists():
        out("[!] test-samples/ 不存在")
        return 1

    out("[1] 扫描非 .md 样本文件")
    targets = []
    for p in test_root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix == ".md":
            continue  # 跳过已是 .md 的（含各 README + 原 .md 样本）
        targets.append(p)
    out(f"   找到 {len(targets)} 个待生成 wrapper 的样本")

    out("\n[2] 生成 .md 索引页")
    skipped = 0
    created = 0
    for p in targets:
        wrapper_path = p.parent / (p.stem + ".md")
        if wrapper_path.exists():
            # 已存在同名 .md（如 v7-baseline 里 13_xx.txt 不存在但 13_xx.md 已是原 md），跳过
            out(f"   [skip] {wrapper_path.relative_to(ROOT)} 已存在")
            skipped += 1
            continue
        wrapper_path.write_text(make_wrapper(p), encoding="utf-8")
        out(f"   [+] {wrapper_path.relative_to(ROOT)}")
        created += 1

    out(f"\n[3] 完成：创建 {created} 个、跳过 {skipped} 个")

    # 抽样验证
    out("\n[4] 抽样验证（前 3 个）")
    import glob
    new_wrappers = sorted(test_root.rglob("*.md"))
    for w in new_wrappers[:3]:
        out(f"   {w.relative_to(ROOT)}: {w.stat().st_size} bytes")

    return 0


if __name__ == "__main__":
    sys.exit(main())
