"""生成 iOS 资源（App Icon PNG + Asset Catalog JSON）。

不依赖 Pillow 等第三方库，纯 zlib + struct 输出 PNG，保证任何环境都能跑。
与 LUMI/Views/LUMIAvatar.swift 的矢量形象保持同一套配色。

用法: python scripts/gen_assets.py
"""

from __future__ import annotations

import json
import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "frontend" / "LUMI" / "Resources" / "Assets.xcassets"

SIZE = 1024
C = SIZE / 100.0  # 与 SwiftUI 100x100 设计稿同一坐标系

# 100x100 设计稿 → 1024 像素
HAIR = (0.19, 0.21, 0.41)
HAIR_LIGHT = (0.26, 0.28, 0.52)
SKIN_TOP = (1.00, 0.94, 0.90)
SKIN_BOTTOM = (0.99, 0.86, 0.84)
EYE_TOP = (0.35, 0.28, 0.62)
EYE_BOTTOM = (0.16, 0.13, 0.34)
BLUSH = (1.00, 0.62, 0.70)
MOUTH = (0.72, 0.36, 0.42)
BG_TOP_LEFT = (0.98, 0.80, 0.92)
BG_MID = (0.76, 0.72, 0.98)
BG_BOTTOM_RIGHT = (0.66, 0.86, 0.98)


def _lerp(a: tuple[float, ...], b: tuple[float, ...], t: float) -> tuple[float, ...]:
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _to_bytes(color: tuple[float, ...]) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(round(c * 255)))) for c in color)


def _ellipse(x: float, y: float, cx: float, cy: float, rx: float, ry: float) -> bool:
    return ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0


def _background(x: float, y: float) -> tuple[float, float, float]:
    """紫粉渐变（左上角 → 右下角，中间过渡色）。"""
    t = (x + y) / 200.0
    if t < 0.5:
        return _lerp(BG_TOP_LEFT, BG_MID, t / 0.5)
    return _lerp(BG_MID, BG_BOTTOM_RIGHT, (t - 0.5) / 0.5)


def render_pixel(x: float, y: float) -> tuple[int, int, int]:
    """x, y 使用 100x100 设计稿坐标。"""
    color = _background(x, y)

    # 后发（大圆）
    if _ellipse(x, y, 50, 52, 48, 48):
        color = _lerp(HAIR_LIGHT, HAIR, min(1.0, max(0.0, (y - 4) / 96)))

    # 侧发缕
    if _ellipse(x, y, 17, 58, 7.5, 27) or _ellipse(x, y, 83, 58, 7.5, 27):
        color = HAIR

    # 脸
    if _ellipse(x, y, 50, 58, 29, 31):
        color = _lerp(SKIN_TOP, SKIN_BOTTOM, min(1.0, max(0.0, (y - 27) / 62)))

        # 腮红
        for bx in (32.0, 68.0):
            if _ellipse(x, y, bx, 66, 6.5, 3.5):
                d = math.hypot((x - bx) / 6.5, (y - 66) / 3.5)
                color = _lerp(color, BLUSH, 0.45 * (1.0 - min(1.0, d)))

        # 眼睛
        for ex in (38.0, 62.0):
            if _ellipse(x, y, ex, 57, 4.75, 6.25):
                color = _lerp(EYE_TOP, EYE_BOTTOM, min(1.0, max(0.0, (y - 51) / 12)))
            if _ellipse(x, y, ex - 2, 53.5, 1.7, 1.7):
                color = _lerp(color, (1.0, 1.0, 1.0), 0.9)
            if _ellipse(x, y, ex + 2.2, 60, 0.9, 0.9):
                color = _lerp(color, (1.0, 1.0, 1.0), 0.45)

        # 嘴（二次贝塞尔弧，取细带）
        mx0, my0, mx1, my1 = 45.0, 70.0, 55.0, 70.0
        cx, cy = 50.0, 76.0
        best = None
        for i in range(41):
            t = i / 40.0
            px = (1 - t) ** 2 * mx0 + 2 * (1 - t) * t * cx + t * t * mx1
            py = (1 - t) ** 2 * my0 + 2 * (1 - t) * t * cy + t * t * my1
            d = math.hypot(x - px, y - py)
            if best is None or d < best:
                best = d
        if best is not None and best <= 0.8:
            color = MOUTH

    # 刘海（压在脸上层）
    if _ellipse(x, y, 50, 32, 33, 20):
        color = HAIR
    # 斜刘海下缘
    if y > 36 and _ellipse(x, y, 50, 41, 31, 11):
        edge = 41 + 11 * math.sqrt(max(0.0, 1 - ((x - 50) / 31) ** 2))
        if y < edge + (6 if x < 50 else 0):
            color = HAIR

    return _to_bytes(color)


def write_png(path: Path, size: int) -> None:
    raw = bytearray()
    for py in range(size):
        raw.append(0)  # filter type 0
        y = (py + 0.5) / (size / 100.0)
        for px in range(size):
            x = (px + 0.5) / (size / 100.0)
            r, g, b = render_pixel(x, y)
            raw += bytes((r, g, b))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    print(f"生成 {path} ({len(png) / 1024:.0f} KB)")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"生成 {path}")


def main() -> int:
    write_json(ASSETS / "Contents.json", {"info": {"author": "xcode", "version": 1}})

    # App Icon
    icon_dir = ASSETS / "AppIcon.appiconset"
    write_png(icon_dir / "AppIcon-1024.png", 1024)
    write_json(icon_dir / "Contents.json", {
        "images": [
            {"filename": "AppIcon-1024.png", "idiom": "universal",
             "platform": "ios", "size": "1024x1024"}
        ],
        "info": {"author": "xcode", "version": 1},
    })

    # AccentColor
    write_json(ASSETS / "AccentColor.colorset" / "Contents.json", {
        "colors": [{
            "idiom": "universal",
            "color": {"color-space": "srgb", "components": {
                "red": "0.596", "green": "0.478", "blue": "0.973", "alpha": "1.000"}},
        }],
        "info": {"author": "xcode", "version": 1},
    })

    # LaunchScreen 背景色
    write_json(ASSETS / "LaunchBackground.colorset" / "Contents.json", {
        "colors": [{
            "idiom": "universal",
            "color": {"color-space": "srgb", "components": {
                "red": "0.086", "green": "0.078", "blue": "0.180", "alpha": "1.000"}},
        }],
        "info": {"author": "xcode", "version": 1},
    })

    print("完成。资源目录:", ASSETS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
