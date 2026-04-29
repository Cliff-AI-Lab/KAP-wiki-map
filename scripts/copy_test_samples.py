"""把 _refs/wiki-map 修复后的 48 个测试样本按行业复制到 KAP 项目内的 test-samples/。

设计：
- 能源保留版本子目录（v7-baseline / v12-revised / v15-extra）
- 制造 / 金融 / IT 直接平铺
- 每个目录复制后内容自包含，不再依赖 _refs（_refs 在 .gitignore，可被删除）
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / ".kap-delegate" / "logs" / "copy_test_samples.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
_log = open(LOG_PATH, "w", encoding="utf-8")


def out(msg: str) -> None:
    _log.write(msg + "\n")
    _log.flush()


# 源目录 → 目标目录映射
MAPPINGS = [
    ("_refs/wiki-map/bookworm-agent/test_data/energy", "test-samples/energy/v7-baseline"),
    ("_refs/wiki-map/bookworm-agent/test_data/energy_v15_extra", "test-samples/energy/v15-extra"),
    ("_refs/wiki-map/bookworm-agent/test_docs/energy_v12", "test-samples/energy/v12-revised"),
    ("_refs/wiki-map/bookworm-agent/test_docs/manufacturing", "test-samples/manufacturing"),
    ("_refs/wiki-map/bookworm-agent/test_docs/finance", "test-samples/finance"),
    ("_refs/wiki-map/bookworm-agent/test_docs/it", "test-samples/it"),
]


def main() -> int:
    total = 0
    for src_rel, dst_rel in MAPPINGS:
        src = ROOT / src_rel
        dst = ROOT / dst_rel
        if not src.exists():
            out(f"[!] 源不存在: {src}")
            continue
        dst.mkdir(parents=True, exist_ok=True)
        files = list(src.iterdir())
        for f in files:
            if not f.is_file():
                continue
            shutil.copy2(f, dst / f.name)
            total += 1
        out(f"  {src_rel} → {dst_rel} ({len([x for x in files if x.is_file()])} 文件)")
    out(f"\n[OK] 共复制 {total} 个文件")

    # 抽样验证
    import glob
    out("\n=== 抽样验证（每行业前 3）===")
    for ind in ("energy/v12-revised", "manufacturing", "finance", "it"):
        files = sorted((ROOT / "test-samples" / ind).glob("*"))
        out(f"  [{ind}]")
        for p in files[:3]:
            out(f"    - {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
