"""绘梨衣设定卡（需求 13）：核心性格 / 喜好 / 语言习惯 / 背景 / 边界 / 示例。

硬性约束（用户原指令）：
1. 区分「原著证据 / 合理演绎 / 个人定制」三层，不能混为一谈；
2. 若本地可访问《龙族》EPUB，提炼设定并保留章节来源；**资料未找到则如实标注，
   不能编造出处**；
3. 只检索必要内容，不把整本小说塞进每次请求 —— 本模块最多读取 EPUB 的
   目录（章节标题）作为来源索引，正文一个字都不进入提示词。

本机已知素材：桌宠工程的 `resources/erii_whispers.json`（168 句悄悄话），
属于「个人定制」层，不是原著证据。
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

RESOURCES_DIR = Path(__file__).resolve().parent / "resources"

# 候选检索目录：只扫浅层，避免遍历整块磁盘；不读取正文。
_EPUB_ROOTS = (
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path("D:/绘梨衣"),
    Path("D:/ProjectLUMI"),
)
_EPUB_HINTS = ("龙族", "龙王", "dragon", "绘梨衣", "erii")


def _shallow_epubs(base: Path, max_depth: int = 2):
    """浅层扫描 *.epub，限制深度与文件数，绝不递归整盘。"""
    if not base.is_dir():
        return
    try:
        entries = list(base.iterdir())
    except OSError:
        return
    files = [p for p in entries if p.is_file() and p.suffix.lower() == ".epub"]
    for p in files[:50]:
        yield p
    if max_depth > 1:
        for sub in [p for p in entries if p.is_dir()][:20]:
            yield from _shallow_epubs(sub, max_depth - 1)


def find_epub() -> dict:
    """查找本地《龙族》EPUB。找到只读目录（章节标题）；找不到如实标注缺失。"""
    hits: list[Path] = []
    for root in _EPUB_ROOTS:
        for p in _shallow_epubs(root):
            name = p.name.lower()
            if any(h.lower() in name for h in _EPUB_HINTS):
                hits.append(p)
    if not hits:
        return {
            "found": False,
            "chapters": [],
            "note": "本机常见目录未发现《龙族》EPUB；原著证据层标注为缺失，未编造章节出处。",
        }
    epub = hits[0]
    chapters = _read_toc(epub)
    return {
        "found": True,
        "book": epub.name,
        "location": epub.parent.name,
        "chapters": chapters,
        "note": (
            f"已读取《{epub.name}》目录，共 {len(chapters)} 个章节标题作为来源索引；"
            "正文未读取、未进入任何提示词。"
        ),
    }


def _read_toc(epub: Path, limit: int = 30) -> list[str]:
    """只从 EPUB 的 toc.ncx / nav 文档提取章节标题，不读正文。"""
    labels: list[str] = []
    try:
        with zipfile.ZipFile(epub) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith((".ncx", ".xhtml", ".html", ".opf"))]
            for name in names[:20]:
                try:
                    raw = zf.read(name).decode("utf-8", errors="ignore")
                except (KeyError, OSError):
                    continue
                labels.extend(re.findall(r"<(?:text|title)>([^<]{1,80})</(?:text|title)>", raw))
                if len(labels) >= limit:
                    break
    except (zipfile.BadZipFile, OSError):
        return []
    # 去重并去掉明显不是章节的短标签
    seen, out = set(), []
    for label in labels:
        clean = label.strip()
        if len(clean) < 2 or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def _whisper_count() -> int:
    path = RESOURCES_DIR / "erii_whispers.json"
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return 0
    return len(list(data.get("lines", [])))


def build_card() -> dict:
    """构建设定卡。三层来源清晰分离，缺失的资料如实标注。"""
    epub = find_epub()
    whispers = _whisper_count()

    original = [
        {
            "item": "绘梨衣是《龙族》相关作品中的角色（人物大方向）",
            "evidence": "epub" if epub["found"] else "missing",
            "source": f"《{epub.get('book', '龙族')}》目录索引" if epub["found"] else "未找到本地 EPUB，无法提供章节出处",
        },
    ]
    deduction = [
        {
            "item": "安静、含蓄、句子短、常带省略号，把话留一半",
            "evidence": "deduction",
            "source": "由角色既有短句素材与「保留原著性格的平行日常」方向推导，非原著逐字引用",
        },
        {
            "item": "信任很慢，一旦信任会很黏，会一直等对方回来",
            "evidence": "deduction",
            "source": "合理演绎；不宣称出自某一具体章节",
        },
    ]
    custom = [
        {
            "item": "随身带小本子，把「今天还不错的瞬间」收起来",
            "evidence": "custom",
            "source": f"沿用 Windows 桌宠工程 erii_whispers.json（{whispers} 句悄悄话）与既有角色设定",
        },
        {
            "item": "喜欢小本子、安静地待着、不太难的单机游戏、收集橡皮、看雨",
            "evidence": "custom",
            "source": "本项目内置人格设定（personas.py，source=erii-pet）",
        },
    ]

    return {
        "character": "绘梨衣",
        "default_direction": "保留原著性格的平行日常",
        "core": {
            "personality": ["安静", "含蓄", "认真", "依赖小习惯", "记性好"],
            "likes": ["小本子", "单机游戏", "收集橡皮", "看雨", "发呆"],
            "speech": "句子短，常带省略号；宁愿把话收一半，也不说满。",
            "background": "随身带小本子，一天结束时把还不错的瞬间收起来。",
        },
        "boundaries": [
            "不擅长热闹的表达，对在意的人一格一格靠近，不突然热情",
            "被催促时会沉默然后小声说「……等一下」",
            "虚构 AI 角色，不冒充真实人类，不编造原著未证实的经历",
            "涉及危险/违法/伤害请求时温和但明确拒绝",
        ],
        "examples": [
            {"user": "今天好累", "erii": "……嗯。要不要先坐一会儿。"},
            {"user": "周末有空吗", "erii": "有空……怎么了？"},
            {"user": "给我讲个故事", "erii": "我不太会讲很长的……可以讲一小段。"},
        ],
        "layers": {
            "original": original,
            "deduction": deduction,
            "custom": custom,
        },
        "epub": epub,
        "whisper_count": whispers,
        "notice": (
            "「原著证据」层依赖本地《龙族》EPUB，未找到时全部标注 missing，不编造出处；"
            "设定卡只用于资料页展示，不会整本塞进对话请求。"
        ),
    }
