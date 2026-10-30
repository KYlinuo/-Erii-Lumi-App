"""端到端冒烟测试：同时对**真实运行的后端**发请求。

与 pytest 单元测试的区别：
- 单元测试注入桩模型，永不联网；
- 本脚本打真实 HTTP 接口，用于部署后验证（可选验证真实模型）。

用法:
    python scripts/smoke_test.py --base-url http://127.0.0.1:8000
    python scripts/smoke_test.py --base-url https://lumi.example.com --token <token> --real-model
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_TIMEOUT = 10.0

# 本机 / 内网地址必须绕过 HTTP_PROXY，否则会被代理拦截（Windows 常见坑）
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(
    url: str,
    method: str = "GET",
    body: dict | None = None,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-LUMI-TOKEN", token)
    try:
        with _NO_PROXY_OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return resp.status, parsed, dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return e.code, parsed, dict(e.headers)


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append((name, ok, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    @property
    def failed(self) -> int:
        return sum(1 for _, ok, _ in self.rows if not ok)

    def summary(self) -> int:
        total = len(self.rows)
        print("-" * 60)
        print(f"共 {total} 项，失败 {self.failed} 项")
        return 1 if self.failed else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--token", default=None)
    ap.add_argument("--real-model", action="store_true", help="真的调用一次模型（会产生费用）")
    ap.add_argument("--timeout", type=float, default=60.0)
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    rpt = Report()
    print(f"LUMI 冒烟测试 → {base}\n" + "-" * 60)

    status, health, _ = request(f"{base}/api/v1/health", timeout=args.timeout)
    rpt.add("GET /api/v1/health", status == 200, json.dumps(health, ensure_ascii=False)[:160])
    if status != 200:
        print("后端不可达，后续检查跳过。请确认 backend 已启动。")
        return 1

    rpt.add("database == ok", health.get("database") == "ok", str(health.get("database")))

    status, persona, _ = request(f"{base}/api/v1/persona", timeout=args.timeout)
    rpt.add("GET /api/v1/persona", status == 200 and persona.get("name") == "LUMI",
            persona.get("name", ""))

    status, _, _ = request(f"{base}/api/v1/conversations", token=args.token, timeout=args.timeout)
    rpt.add("GET /conversations 鉴权", status in (200, 401), f"status={status}")
    if status == 401:
        print("      提示：服务端开启了访问认证但未传 --token。")

    if args.real_model:
        t0 = time.time()
        status, body, headers = request(
            f"{base}/api/v1/chat",
            method="POST",
            body={"message": "用一句话自我介绍一下。"},
            token=args.token,
            timeout=args.timeout,
        )
        cost = int((time.time() - t0) * 1000)
        if status == 200:
            reply = body.get("reply", "")
            rpt.add("POST /api/v1/chat 真实模型", True, f"{cost}ms model={body.get('model')}")
            print(f"      回复: {reply[:200]}")
            conv = body.get("conversation_id")
            s2, msgs, _ = request(f"{base}/api/v1/conversations/{conv}/messages",
                                  token=args.token, timeout=args.timeout)
            rpt.add("历史消息可恢复", s2 == 200 and len(msgs) == 2, f"messages={len(msgs) if s2 == 200 else s2}")
        else:
            code = body.get("error", {}).get("code")
            rpt.add("POST /api/v1/chat 真实模型", False, f"status={status} code={code}")
            if code == "provider_not_configured":
                print("      后端未配置 LUMI_API_KEY —— 这是真实状态，不是冒烟脚本的问题。")
    else:
        print("[SKIP] 真实模型调用（加 --real-model 启用）")

    return rpt.summary()


if __name__ == "__main__":
    sys.exit(main())
