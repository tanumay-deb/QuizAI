#!/usr/bin/env python
"""Build a standalone QuizAI binary for the current OS.

Just a thin wrapper around `pyinstaller quizai.spec` that prints a summary at
the end. Run this after `pip install -e .[dev]`.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    spec = root / "quizai.spec"
    if not spec.exists():
        print(f"ERROR: spec file missing at {spec}", file=sys.stderr)
        return 1

    print(f"Building QuizAI for {platform.system()} ({platform.machine()})…")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(spec), "--noconfirm"],
        cwd=root,
    )
    if result.returncode != 0:
        return result.returncode

    dist = root / "dist"
    print("\nBuild succeeded. Outputs in:", dist)
    for item in sorted(dist.iterdir()):
        size_mb = (
            sum(p.stat().st_size for p in item.rglob("*") if p.is_file()) / 1_000_000
            if item.is_dir()
            else item.stat().st_size / 1_000_000
        )
        print(f"  {item.name}  ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
