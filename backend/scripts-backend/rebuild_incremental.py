"""M22 #7 · 增量重抽 CLI — 基于本体 diff 输出 RebuildPlan dry-run。

用法:
    python scripts-backend/rebuild_incremental.py \
        --project p_src --from v1.0 --to v1.1 \
        --doc-to-types doc_types.json --dry-run

doc_to_types.json 格式: {"doc_id_1": ["E_DEVICE", "E_DOCUMENT"], ...}

输出 RebuildPlan: full_docs / partial_docs / skipped_docs + 成本估算。

M22 #7 lite 仅做 dry-run（plan 输出）；实际执行（接 rebuild_orchestrator +
影子库 + 灰度切换）留 M23。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 让脚本能 import packages
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.common.types import OntologyDiff  # noqa: E402
from packages.rebuild.incremental import analyze_impact  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description="增量重抽 lite — 基于本体 diff 输出 RebuildPlan",
    )
    ap.add_argument("--project", required=True, help="项目 id")
    ap.add_argument("--from", dest="version_from", required=True,
                    help="from 本体版本 id (如 ont-v1.0.0)")
    ap.add_argument("--to", dest="version_to", required=True,
                    help="to 本体版本 id (如 ont-v1.1.0)")
    ap.add_argument("--doc-to-types", required=True,
                    help="doc → type_ids JSON 索引文件路径")
    ap.add_argument("--l1-changed", action="store_true",
                    help="L1 行业本体变更（强制全量重抽）")
    ap.add_argument("--added-entity-types", nargs="*", default=[],
                    help="新增的实体类型 type_ids")
    ap.add_argument("--removed-entity-types", nargs="*", default=[])
    ap.add_argument("--modified-entity-types", nargs="*", default=[])
    ap.add_argument("--added-relation-types", nargs="*", default=[])
    ap.add_argument("--removed-relation-types", nargs="*", default=[])
    ap.add_argument("--modified-relation-types", nargs="*", default=[])
    ap.add_argument("--out", default="", help="输出文件路径（默认 stdout）")
    ap.add_argument("--dry-run", action="store_true",
                    help="仅算 plan, 不实际执行（M22 #7 lite 必填）")
    args = ap.parse_args()

    if not args.dry_run:
        print("warn: M22 #7 lite 仅支持 --dry-run；实际执行未实现。",
              file=sys.stderr)
        # 仍生成 plan 给 caller 参考

    doc_to_types_path = Path(args.doc_to_types)
    if not doc_to_types_path.exists():
        print(f"error: doc-to-types 文件不存在: {doc_to_types_path}",
              file=sys.stderr)
        return 2

    doc_to_types_raw = json.loads(doc_to_types_path.read_text(encoding="utf-8"))
    doc_to_types = {k: set(v) for k, v in doc_to_types_raw.items()}

    diff = OntologyDiff(
        from_version=args.version_from, to_version=args.version_to,
        added_entity_types=args.added_entity_types,
        removed_entity_types=args.removed_entity_types,
        modified_entity_types=args.modified_entity_types,
        added_relation_types=args.added_relation_types,
        removed_relation_types=args.removed_relation_types,
        modified_relation_types=args.modified_relation_types,
    )

    plan = analyze_impact(
        diff=diff, doc_to_types=doc_to_types,
        project_id=args.project, l1_changed=args.l1_changed,
    )

    out_text = json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(out_text, encoding="utf-8")
        print(f"plan 已写入 {args.out}", file=sys.stderr)
    else:
        print(out_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
