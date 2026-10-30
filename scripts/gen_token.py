"""生成单用户访问令牌，并写入 .env（若已存在则提示手动替换）。

用法:
    python scripts/gen_token.py            # 打印新 token
    python scripts/gen_token.py --write    # 写入 .env 的 LUMI_ACCESS_TOKEN
"""

from __future__ import annotations

import argparse
import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
EXAMPLE_FILE = ROOT / ".env.example"


def generate() -> str:
    return secrets.token_urlsafe(32)


def write_env(token: str) -> None:
    if not ENV_FILE.is_file():
        ENV_FILE.write_text(EXAMPLE_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"已由 .env.example 创建 {ENV_FILE}")

    text = ENV_FILE.read_text(encoding="utf-8")
    line = f"LUMI_ACCESS_TOKEN={token}"
    if re.search(r"^LUMI_ACCESS_TOKEN=.*$", text, flags=re.M):
        text = re.sub(r"^LUMI_ACCESS_TOKEN=.*$", line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    ENV_FILE.write_text(text, encoding="utf-8")
    print(f"已写入 {ENV_FILE} 的 LUMI_ACCESS_TOKEN")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 LUMI 访问令牌")
    parser.add_argument("--write", action="store_true", help="写入 .env")
    args = parser.parse_args()

    token = generate()
    print(f"新令牌: {token}")
    if args.write:
        write_env(token)
    else:
        print("（未写入文件。加 --write 可自动写入 .env）")
    print("把该令牌填入 iOS 客户端设置页，或由 Keychain 首次配对时保存。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
