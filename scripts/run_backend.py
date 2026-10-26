"""启动 LUMI 后端（自动加载 .env、切换工作目录）。

用法:
    python scripts/run_backend.py            # 开发模式（热重载）
    python scripts/run_backend.py --prod     # 生产模式（无热重载）
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod", action="store_true")
    ap.add_argument("--host", default=os.getenv("LUMI_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("LUMI_PORT", "8000")))
    args = ap.parse_args()

    env_file = ROOT / ".env"
    if env_file.is_file():
        print(f"加载环境变量: {env_file}")
    else:
        print(f"[WARN] 未找到 {env_file}，将使用默认值（模型调用会返回 503）")

    cmd = [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", args.host, "--port", str(args.port),
    ]
    if not args.prod:
        cmd.append("--reload")

    print("启动命令:", " ".join(cmd))
    print(f"健康检查: http://{args.host}:{args.port}/api/v1/health")
    print(f"接口文档: http://{args.host}:{args.port}/docs")
    return subprocess.run(cmd, cwd=BACKEND, env={**os.environ, "PYTHONPATH": str(BACKEND)}).returncode


if __name__ == "__main__":
    raise SystemExit(main())
