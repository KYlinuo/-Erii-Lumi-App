"""环境自检：确认本机具备运行/构建 LUMI 的前提条件。

用法: python scripts/check_env.py
退出码 0 = 全部就绪；1 = 有缺失项（会打印修复建议）。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PY = (3, 11)
BACKEND_PKGS = ["fastapi", "uvicorn", "sqlalchemy", "pydantic_settings", "httpx", "pytest"]


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return p.returncode, (p.stdout or p.stderr).strip()
    except FileNotFoundError:
        return 127, "command not found"
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def check_python() -> bool:
    ok = sys.version_info >= REQUIRED_PY
    print(f"[{'OK ' if ok else 'FAIL'}] Python {sys.version.split()[0]} (>= {REQUIRED_PY[0]}.{REQUIRED_PY[1]})")
    return ok


def check_git() -> bool:
    code, out = _run(["git", "--version"])
    ok = code == 0
    print(f"[{'OK ' if ok else 'FAIL'}] Git: {out.splitlines()[0] if ok else 'not found'}")
    return ok


def check_backend_pkgs() -> bool:
    missing = []
    for pkg in BACKEND_PKGS:
        r = subprocess.run(
            [sys.executable, "-c", f"import {pkg}"], capture_output=True, text=True
        )
        if r.returncode != 0:
            missing.append(pkg)
    ok = not missing
    detail = "all present" if ok else f"missing: {', '.join(missing)}"
    print(f"[{'OK ' if ok else 'FAIL'}] 后端依赖: {detail}")
    if not ok:
        print("      修复: python -m pip install -r backend/requirements-dev.txt")
    return ok


def check_env_file() -> bool:
    env = ROOT / ".env"
    example = ROOT / ".env.example"
    ok = example.is_file()
    print(f"[{'OK ' if ok else 'FAIL'}] .env.example 存在: {example}")
    if not env.is_file():
        print(f"[WARN] .env 不存在，后端将使用默认值（无 API Key / 无 token）")
        print(f"      复制: cp .env.example .env 并填入真实值")
    else:
        print(f"[OK ] .env 已存在（内容不会被本脚本读取）")
    return ok


def check_git_ignores_env() -> bool:
    code, out = _run(["git", "check-ignore", "-q", ".env"])
    ok = code == 0
    print(f"[{'OK ' if ok else 'FAIL'}] .env 已被 git 忽略（防止密钥入库）")
    return ok


def check_dirs() -> bool:
    expected = ["frontend", "backend", "docs", "tests", "scripts", ".github/workflows"]
    missing = [d for d in expected if not (ROOT / d).is_dir()]
    ok = not missing
    print(f"[{'OK ' if ok else 'FAIL'}] 项目目录: {'齐全' if ok else '缺少 ' + ', '.join(missing)}")
    return ok


def check_xcode() -> bool:
    if shutil.which("xcodebuild"):
        code, out = _run(["xcodebuild", "-version"])
        print(f"[OK ] Xcode: {out.splitlines()[0] if code == 0 else 'unknown'}")
        return True
    print("[SKIP] xcodebuild 不存在 —— iOS 构建请在 macOS 或 GitHub Actions macOS Runner 上执行")
    return True


def main() -> int:
    print(f"Project LUMI 环境自检 ({ROOT})\n" + "-" * 60)
    results = [
        check_python(),
        check_git(),
        check_dirs(),
        check_env_file(),
        check_git_ignores_env(),
        check_backend_pkgs(),
        check_xcode(),
    ]
    print("-" * 60)
    hard_fail = not all(results[:6])
    print("结论:", "环境不完整，请先修复 FAIL 项" if hard_fail else "环境就绪")
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
