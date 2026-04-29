"""为 V15 原始 .md 测试样本注入 navigation header（不改正文）。

之前 generate_sample_indexes.py 跳过了已是 .md 的文件，
保护原内容；但这导致 9 份 V15 原始 .md（02/04/06/08/10/13/14/15 + 国家电网细则）
没有反向链接，在 Obsidian 图谱里成孤岛。

本脚本：识别**没有 frontmatter** 的原始样本 .md，在文件顶部插入：
- frontmatter（type / industry / subset / source-format=md / source-file）
- navigation 行（行业 README / 总入口 / 项目首页 / 决策书）
- 配套模板链接

正文（# 标题及之后）完全保留。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / ".kap-delegate" / "logs" / "inject_sample_navigation.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
_log = open(LOG_PATH, "w", encoding="utf-8")


def out(msg: str) -> None:
    _log.write(msg + "\n")
    _log.flush()


TEMPLATE_MAP = {
    "energy": "backend/templates/energy/",
    "manufacturing": "backend/templates/manufacturing/",
    "finance": "backend/templates/_default/",
    "it": "backend/templates/_default/",
}
DECISION_SECTION = {
    "energy": "§7.2",
    "manufacturing": "§7.1",
    "finance": "§1.3",
    "it": "§7.4",
}
SUBSET_DESC = {
    "v7-baseline": "V7 早期完整集",
    "v12-revised": "V12 精简标准基线",
    "v15-extra": "V15 增补真实场景集",
}


def detect_industry_and_subset(path: Path) -> tuple[str, str]:
    parts = path.relative_to(ROOT / "test-samples").parts
    if not parts:
        return "", ""
    industry = parts[0]
    subset = parts[1] if len(parts) >= 3 and parts[1] in SUBSET_DESC else ""
    return industry, subset


def make_header(path: Path, original_first_line: str) -> str:
    """构造 frontmatter + navigation。"""
    industry, subset = detect_industry_and_subset(path)
    section = DECISION_SECTION.get(industry, "§7")
    subset_desc = SUBSET_DESC.get(subset, "")
    template_rel = TEMPLATE_MAP.get(industry, "backend/templates/_default/")

    if subset:
        ind_readme = "../README.md"
        samples_root = "../../README.md"
        proj_readme = "../../../README.md"
        decision = "../../../docs/01-技术决策书.md"
        template = f"../../../{template_rel}"
    else:
        ind_readme = "./README.md"
        samples_root = "../README.md"
        proj_readme = "../../README.md"
        decision = "../../docs/01-技术决策书.md"
        template = f"../../{template_rel}"

    title = path.stem
    fm = [
        "---",
        f"title: {title}",
        "type: kap-test-sample",
        f"industry: {industry}",
    ]
    if subset:
        fm.append(f"subset: {subset}")
    fm.extend([
        "source-format: md",
        f"source-file: {path.name}",
        "preserved: true   # V15 原始文档，正文已保留",
        "---",
        "",
        f"> 导航：[← 行业 README]({ind_readme}) · [← 测试样例总入口]({samples_root}) · "
        f"[← 项目首页]({proj_readme}) · [决策书 {section}]({decision}) · "
        f"[配套模板]({template})",
        "",
    ])
    if subset_desc:
        fm.append(f"> **子集**：{subset} · {subset_desc}")
        fm.append("")
    fm.append("---")
    fm.append("")
    return "\n".join(fm)


def main() -> int:
    test_root = ROOT / "test-samples"
    targets = []
    for p in test_root.rglob("*.md"):
        # 跳过 README
        if p.name == "README.md":
            continue
        text = p.read_text(encoding="utf-8")
        # 已有 frontmatter（含本次新加 + 之前 wrapper 生成）→ 跳过
        if text.lstrip().startswith("---"):
            continue
        targets.append((p, text))

    out(f"[1] 扫描到 {len(targets)} 份缺 frontmatter 的原始 .md")

    for p, text in targets:
        rel = p.relative_to(ROOT)
        first_line = text.split("\n", 1)[0]
        out(f"   [+] {rel}（首行：{first_line[:50]}）")

    out("\n[2] 注入 navigation header")
    for p, text in targets:
        header = make_header(p, text.split("\n", 1)[0])
        new_text = header + text
        p.write_text(new_text, encoding="utf-8")

    out(f"\n[3] 完成：{len(targets)} 份注入 navigation")

    return 0


if __name__ == "__main__":
    sys.exit(main())
