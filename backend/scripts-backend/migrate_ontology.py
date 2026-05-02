"""L2 本体迁移 CLI（M20 #2）。

支持离线导出 / 编辑 / 导入工作流：

    # 导出 p_src 的 L2 到 yaml（人友好可编辑）
    python -m scripts-backend.migrate_ontology export --project p_src --out ont.yaml

    # SME 编辑 ont.yaml 后导入到 p_tgt（默认 rename 冲突策略）
    python -m scripts-backend.migrate_ontology import --file ont.yaml --target p_tgt

    # 强制覆盖（生产慎用）
    python -m scripts-backend.migrate_ontology import --file ont.yaml --target p_tgt --conflict overwrite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from packages.ontology import (
    OntologyStore, export_to_file, import_from_file,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="导出某 project 的 L2 到文件")
    e.add_argument("--project", required=True, help="源 project_id")
    e.add_argument("--out", required=True, help="输出文件路径（.json / .yaml）")
    e.add_argument("--current-only", action="store_true",
                   help="仅导出当前生效版本（不带历史）")

    i = sub.add_parser("import", help="从文件导入到目标 project")
    i.add_argument("--file", required=True, help="输入文件（.json / .yaml）")
    i.add_argument("--target", required=True, help="目标 project_id")
    i.add_argument("--conflict", choices=["rename", "skip", "overwrite"],
                   default="rename")

    args = ap.parse_args()
    store = OntologyStore()

    if args.cmd == "export":
        out = Path(args.out)
        export_to_file(
            args.project, out, store=store,
            include_history=not args.current_only,
        )
        print(f"exported → {out}")
        return

    if args.cmd == "import":
        report = import_from_file(
            Path(args.file), args.target,
            store=store, on_conflict=args.conflict,
        )
        print(f"target_project_id  : {report.target_project_id}")
        print(f"new_version        : {report.new_version}")
        print(f"imported_versions  : {report.imported_versions}")
        print(f"skipped_versions   : {report.skipped_versions}")
        if report.renamed_types:
            print(f"renamed: {report.renamed_types}")
        if report.overwritten_types:
            print(f"overwritten: {report.overwritten_types}")
        if report.notes:
            print(f"notes: {report.notes}")
        return

    sys.exit("unknown subcommand")


if __name__ == "__main__":
    main()
