"""V15 代码知识图谱扫描器 (借鉴 GitNexus).

Python AST 扫描 packages/ + api/ 模块级依赖.
不依赖 Tree-sitter, 用标准库 ast, 零外部依赖.

输出: 节点=Python 模块, 边=import 关系
应用:
  • blast_radius(target): 改 target 模块时, 谁会受影响 (反向 import 图 BFS)
  • dead_code: 入度=0 且非顶层 entry 的模块
  • centrality: 模块重要性
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator

from packages.common import get_logger

log = get_logger("governance.code_graph")


# 项目内可识别的顶层包 (扫描时仅保留指向这些的 import 边)
PROJECT_PACKAGES = {"api", "packages"}

# 入口模块 (即使入度=0 也不应标 dead_code)
ENTRY_MODULES = {
    "api.main",
    "packages.distillation.llm_client",
    "packages.governance",
}


def _module_name_from_path(repo_root: Path, file_path: Path) -> str:
    """E:/.../bookworm-agent/packages/governance/agents/auditor.py
       → packages.governance.agents.auditor"""
    rel = file_path.relative_to(repo_root)
    parts = rel.with_suffix("").parts
    # __init__.py → 包名
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve_relative_import(current_module: str, level: int, module: str | None) -> str | None:
    """from . import x → 解析为绝对模块名。"""
    if level == 0:
        return module
    parts = current_module.split(".")
    if level > len(parts):
        return None
    base = ".".join(parts[:-level]) if level <= len(parts) else ""
    if module:
        return f"{base}.{module}" if base else module
    return base or None


def _iter_python_files(repo_root: Path) -> Iterator[Path]:
    """生成 packages/* 和 api/* 下的 .py 文件 (跳过 __pycache__ / tests)。"""
    for pkg in PROJECT_PACKAGES:
        pkg_dir = repo_root / pkg
        if not pkg_dir.is_dir():
            continue
        for f in pkg_dir.rglob("*.py"):
            if "__pycache__" in f.parts or "tests" in f.parts:
                continue
            yield f


def _extract_imports(tree: ast.AST, current_module: str) -> set[str]:
    """从 AST 提取所有 import 目标模块名 (绝对+相对都解析为绝对)。"""
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            target = _resolve_relative_import(current_module, node.level or 0, node.module)
            if target:
                imports.add(target)
                # 关键: from packages.x import y 也加 packages.x.y 候选
                # 因为 y 可能是子模块 (auditor / standardizer 等), 也可能是类/函数
                # _norm_module 会回退到真实存在的层级
                for alias in node.names:
                    if alias.name and alias.name != '*':
                        imports.add(f"{target}.{alias.name}")
    return imports


def _is_project_module(name: str) -> bool:
    """是否项目内模块 (vs 标准库 / 第三方)。"""
    head = name.split(".", 1)[0]
    return head in PROJECT_PACKAGES


def _norm_module(name: str, all_modules: set[str]) -> str | None:
    """把 import 目标归一化为图谱里实际存在的节点名。

    例如 import packages.governance.agents.auditor.AuditorAgent (类不是模块):
      逐级回退 packages.governance.agents.auditor → 命中
    """
    parts = name.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in all_modules:
            return candidate
        parts.pop()
    return None


def build_code_graph(repo_root: Path | str) -> dict:
    """扫 repo_root 下 packages/ + api/, 返回模块级依赖图。

    返回:
        {
          "nodes": [{id, package, file, classes, functions, loc, color, size}],
          "edges": [{source, target, kind: "import"}],
          "stats": {node_count, edge_count, dead_code_count, package_count, total_loc},
          "package_colors": {package: hex},
        }
    """
    repo_root = Path(repo_root).resolve()

    # ── Pass 1: 扫所有文件，建立 module → file 映射 + 节点元数据
    file_map: dict[str, Path] = {}
    node_meta: dict[str, dict] = {}
    for f in _iter_python_files(repo_root):
        try:
            mod = _module_name_from_path(repo_root, f)
        except ValueError:
            continue
        if not mod:
            continue
        file_map[mod] = f
        try:
            text = f.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(f))
        except Exception as e:
            log.warning("code_graph_parse_failed", file=str(f), error=str(e))
            node_meta[mod] = {
                "id": mod,
                "package": mod.split(".", 1)[0],
                "file": str(f.relative_to(repo_root)).replace("\\", "/"),
                "classes": [],
                "functions": [],
                "loc": 0,
                "_imports_raw": set(),
            }
            continue
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        functions = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        node_meta[mod] = {
            "id": mod,
            "package": mod.split(".", 1)[0],
            "file": str(f.relative_to(repo_root)).replace("\\", "/"),
            "classes": classes[:8],
            "functions": [n for n in functions if not n.startswith("_")][:12],
            "loc": text.count("\n") + 1,
            "_imports_raw": _extract_imports(tree, mod),
        }

    all_modules = set(node_meta.keys())

    # ── Pass 2: 解析 import 边 (仅项目内)
    edges: list[dict] = []
    in_degree: dict[str, int] = {m: 0 for m in all_modules}
    out_degree: dict[str, int] = {m: 0 for m in all_modules}
    for mod, meta in node_meta.items():
        seen: set[str] = set()
        for raw in meta["_imports_raw"]:
            if not _is_project_module(raw):
                continue
            target = _norm_module(raw, all_modules)
            if target and target != mod and target not in seen:
                edges.append({"source": mod, "target": target, "kind": "import"})
                in_degree[target] = in_degree.get(target, 0) + 1
                out_degree[mod] = out_degree.get(mod, 0) + 1
                seen.add(target)

    # ── Pass 3: 染色 (按二级包 e.g. packages.storage / packages.governance / api.routers)
    sub_pkg_palette = [
        "#88c0d0",  # frost - 主
        "#a3be8c",  # aurora green
        "#bf616a",  # aurora red
        "#ebcb8b",  # aurora yellow
        "#b48ead",  # purple
        "#d08770",  # orange
        "#5e81ac",  # frost dark
        "#8fbcbb",  # cyan
        "#a3b1c4",  # ice
    ]
    sub_pkgs = sorted({_subpackage(m) for m in all_modules})
    pkg_colors = {p: sub_pkg_palette[i % len(sub_pkg_palette)] for i, p in enumerate(sub_pkgs)}

    # ── 装配最终节点
    nodes: list[dict] = []
    dead_code_count = 0
    for mod, meta in node_meta.items():
        sub = _subpackage(mod)
        in_deg = in_degree.get(mod, 0)
        out_deg = out_degree.get(mod, 0)
        is_dead = (in_deg == 0 and mod not in ENTRY_MODULES and not mod.endswith(".__main__"))
        if is_dead:
            dead_code_count += 1
        nodes.append({
            "id": mod,
            "package": meta["package"],
            "subpackage": sub,
            "file": meta["file"],
            "classes": meta["classes"],
            "functions": meta["functions"],
            "loc": meta["loc"],
            "in_degree": in_deg,
            "out_degree": out_deg,
            "color": pkg_colors[sub],
            "size": 5 + min(20, in_deg + out_deg),
            "is_entry": mod in ENTRY_MODULES,
            "is_dead": is_dead,
        })

    log.info("code_graph_built",
             nodes=len(nodes), edges=len(edges),
             dead=dead_code_count, packages=len(sub_pkgs))

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "dead_code_count": dead_code_count,
            "package_count": len(sub_pkgs),
            "total_loc": sum(n["loc"] for n in nodes),
        },
        "package_colors": pkg_colors,
    }


def _subpackage(module: str) -> str:
    """packages.governance.agents.auditor → packages.governance"""
    parts = module.split(".")
    if len(parts) >= 2:
        return ".".join(parts[:2])
    return module


def blast_radius(graph: dict, target: str, max_hops: int = 3) -> dict:
    """改动 target 模块时, 反向 BFS 找出所有受影响的上游模块。

    返回 {target, affected: [{module, hops}], stats}
    """
    # 反向邻接
    rev: dict[str, set[str]] = {}
    for e in graph["edges"]:
        rev.setdefault(e["target"], set()).add(e["source"])

    if target not in {n["id"] for n in graph["nodes"]}:
        return {"target": target, "affected": [], "stats": {"count": 0}, "error": "module not found"}

    visited: dict[str, int] = {target: 0}
    frontier = {target}
    for hop in range(1, max_hops + 1):
        next_frontier: set[str] = set()
        for node in frontier:
            for upstream in rev.get(node, set()):
                if upstream not in visited:
                    visited[upstream] = hop
                    next_frontier.add(upstream)
        frontier = next_frontier
        if not frontier:
            break

    affected = sorted(
        ({"module": m, "hops": h} for m, h in visited.items() if m != target),
        key=lambda x: (x["hops"], x["module"]),
    )
    return {
        "target": target,
        "max_hops": max_hops,
        "affected": affected,
        "stats": {
            "count": len(affected),
            "by_hop": {str(h): sum(1 for x in affected if x["hops"] == h) for h in range(1, max_hops + 1)},
        },
    }
