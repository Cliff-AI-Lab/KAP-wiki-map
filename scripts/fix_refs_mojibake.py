"""一次性修复 _refs 下的 Wiki-map ZIP 乱码文件名（GBK→CP437 编码错位）。

使用 zipfile.metadata_encoding='gbk' 从原始 ZIP 重新提取
test_data / test_docs 子树，覆盖之前 unzip 的乱码版本。
"""

from __future__ import annotations

import glob
import os
import sys
import zipfile
from pathlib import Path

ZIP_PATH = r"E:/Obsidian/知识PPL/raw/Wiki-map/bookworm-agent-v15.zip"
TARGET_ROOT = Path("_refs/wiki-map")
PREFIXES = ("bookworm-agent/test_data/", "bookworm-agent/test_docs/")
LOG_PATH = Path(".kap-delegate/logs/fix_refs_mojibake.log")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
_log = open(LOG_PATH, "w", encoding="utf-8")


def out(msg: str) -> None:
    _log.write(msg + "\n")
    _log.flush()


def clean_subtree(p: Path) -> None:
    if not p.exists():
        return
    rm_fails = 0
    for root, dirs, files in os.walk(p, topdown=False):
        for name in files:
            try:
                os.remove(os.path.join(root, name))
            except OSError:
                rm_fails += 1
        for name in dirs:
            try:
                os.rmdir(os.path.join(root, name))
            except OSError:
                rm_fails += 1
    try:
        os.rmdir(p)
    except OSError:
        pass
    if rm_fails:
        out(f"   [warn] {rm_fails} files/dirs 删除失败（可能锁定）")


def main() -> int:
    out("[1] 清空旧的乱码子树")
    for sub in ("bookworm-agent/test_data", "bookworm-agent/test_docs"):
        p = TARGET_ROOT / sub
        out(f"   {p} (exists={p.exists()})")
        clean_subtree(p)

    out("[2] 用 gbk metadata_encoding 重解压")
    count = 0
    with zipfile.ZipFile(ZIP_PATH, metadata_encoding="gbk") as zf:
        for info in zf.infolist():
            if not info.filename.startswith(PREFIXES):
                continue
            if info.is_dir():
                (TARGET_ROOT / info.filename).mkdir(parents=True, exist_ok=True)
                continue
            zf.extract(info, TARGET_ROOT)
            count += 1
    out(f"   解压 {count} 个文件")

    out("[3] 校验残留乱码")
    bad_chars = set("ÕÚÞµþßçèéêëìíîï")
    problem: list[str] = []
    for pattern in (
        "_refs/wiki-map/bookworm-agent/test_data/**/*",
        "_refs/wiki-map/bookworm-agent/test_docs/**/*",
    ):
        for f in glob.glob(pattern, recursive=True):
            if not os.path.isfile(f):
                continue
            if any(c in os.path.basename(f) for c in bad_chars):
                problem.append(f)
    if problem:
        out(f"   仍有 {len(problem)} 个乱码:")
        for f in problem[:5]:
            out(f"     {f}")
    else:
        out("   全部修复 OK")

    out("[4] 抽样能源测试数据（前 12）：")
    for f in sorted(glob.glob("_refs/wiki-map/bookworm-agent/test_data/energy/*"))[:12]:
        out(f"   - {os.path.basename(f)}")
    return 0 if not problem else 1


if __name__ == "__main__":
    sys.exit(main())
