"""语境回应（需求 12）：区分分享 / 倾诉 / 玩笑 / 认真提问 / 求建议。

设计约束（来自用户 36 项需求原文）：
1. 根据语境选择回应长度与方式，减少机械复述和连续追问，不确定时自然澄清；
2. **不能将情绪推断冒充已知事实** —— 语境判断只是「对这句话可能是什么的
   猜测」，注入 prompt 时必须显式标注为猜测，禁止模型说「我知道你很难过」
   这类把推断当事实的话；
3. 纯规则启发式：零模型调用、零费用、可离线测试；不引入新依赖；
4. 紧急求助 / 安全相关单独标注，交叉满足需求 08：重要错误与紧急求助
   不做任何装饰性延迟。

这是「提示词侧的软判断」，绝不替代服务端权限、预算与数据隔离检查。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# ---------------------------------------------------------------- 类别常量

SHARE = "share"      # 分享见闻
VENT = "vent"        # 倾诉情绪
JOKE = "joke"        # 玩笑 / 逗趣
SERIOUS = "serious"  # 认真提问
ADVICE = "advice"    # 求建议
OTHER = "other"      # 未识别

_LABELS = {
    SHARE: "分享",
    VENT: "倾诉",
    JOKE: "玩笑",
    SERIOUS: "认真提问",
    ADVICE: "求建议",
    OTHER: "普通对话",
}

# 紧急求助 / 安全相关：命中即不做装饰性延迟，且提示优先确认安全
_URGENT_WORDS = (
    "救命", "自杀", "不想活", "活不下去", "跳楼", "割腕", "伤害自己",
    "报警", "110", "120", "急救", "出事了", "快不行", "有人要", "被跟踪",
    "着火", "地震", "车祸", "吃药过量", "救我",
)

_VENT_WORDS = (
    "难过", "难受", "好累", "很累", "疲惫", "烦", "委屈", "想哭", "哭了",
    "压力", "失眠", "睡不着", "孤独", "崩溃", "焦虑", "心情不好", "被骂",
    "失恋", "撑不住", "没意思", "提不起劲", "emo", "低落", "好烦",
)
_JOKE_WORDS = (
    "哈哈", "呵呵", "笑死", "233", "逗你", "开玩笑", "闹着玩", "蚌埠住了",
    "doge", "皮一下", "开个玩笑", "🤣", "😂",
)
_ADVICE_WORDS = (
    "怎么办", "该不该", "要不要", "建议", "帮我想", "选哪个", "怎么选",
    "给个主意", "你觉得我该", "如何决定", "拿不定", "有啥办法", "指点",
)
_SERIOUS_WORDS = (
    "为什么", "怎么回事", "如何", "什么叫", "是什么", "原理", "是不是",
    "能不能解释", "区别", "定义", "求解", "怎么理解", "难道", "凭什么",
)
_SHARE_WORDS = (
    "今天", "刚刚", "刚才", "看到", "给你看", "分享", "发现", "遇到",
    "拍了", "买了", "去了", "吃了", "听说", "给你讲", "跟你说个事",
)

# 优先级（同分时靠前胜出）：玩笑优先于倾诉，避免「哈哈好累」被当成倾诉
_PRIORITY = (JOKE, ADVICE, VENT, SERIOUS, SHARE)


@dataclass(frozen=True)
class ContextSense:
    """一次语境判断的结果。`confidence` 固定为 guess，强调这是猜测。"""

    kind: str
    label: str
    urgent: bool
    confidence: str = "guess"
    hint: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def detect_urgent(text: str) -> bool:
    """安全 / 紧急求助关键词检测（命中即 True，宁可多标不可漏标）。"""
    t = text or ""
    return any(w in t for w in _URGENT_WORDS)


def _hits(text: str, words: tuple[str, ...]) -> int:
    return sum(1 for w in words if w in text)


def classify(text: str) -> ContextSense:
    """对用户输入做一次语境判断。永远返回猜测，不宣称已知事实。"""
    t = (text or "").strip()
    urgent = detect_urgent(t)

    scores = {
        JOKE: _hits(t, _JOKE_WORDS),
        ADVICE: _hits(t, _ADVICE_WORDS),
        VENT: _hits(t, _VENT_WORDS),
        SERIOUS: _hits(t, _SERIOUS_WORDS),
        SHARE: _hits(t, _SHARE_WORDS),
    }
    # 问号 / 长句给「认真提问」加权，但只有 1 分，不足以压过明确的情绪词
    if "?" in t or "？" in t:
        scores[SERIOUS] += 1
    if len(t) >= 40:
        scores[SERIOUS] += 1

    best = OTHER
    best_score = 0
    for kind in _PRIORITY:
        if scores[kind] > best_score:
            best, best_score = kind, scores[kind]
    if best_score == 0:
        best = OTHER

    hints = {
        SHARE: (
            "对方像是在分享见闻：顺着具体内容接话，说出你真正感兴趣的那个点，"
            "最多问一个具体细节，不要连续追问，也不要把话复述一遍。"
        ),
        VENT: (
            "对方可能想倾诉：先接住，不要急着给建议或讲道理，篇幅短一些；"
            "最多一个温柔的问题。不要说「我知道你很难过」——这是猜测，"
            "可以说「听起来像是……」这类不确定的表达。"
        ),
        JOKE: (
            "对方像是在开玩笑：可以轻松接梗，别突然严肃说教，也别把玩笑"
            "当成需要安慰的求助。"
        ),
        SERIOUS: (
            "对方像是在认真提问：把话说清楚，给依据；不确定的地方直接说不确定，"
            "不要编造来源，也不要预设「你一定不懂」。"
        ),
        ADVICE: (
            "对方似乎在求建议：先确认他想要的是安慰还是办法，再给少量可执行的"
            "建议，不替他做决定，不连续追问细节。"
        ),
        OTHER: (
            "语境不明确：正常自然地回应，不要机械复述对方的话，不要为了凑内容"
            "连续追问；真没听懂就用一句话自然澄清。"
        ),
    }
    hint = hints[best]
    if urgent:
        hint = (
            "【安全优先】这句话可能涉及紧急求助或危险：立刻直接回应，"
            "不做任何节奏延迟；不冒充专业救援，可以建议联系身边的人或紧急服务。"
            + hint
        )
    return ContextSense(kind=best, label=_LABELS[best], urgent=urgent, hint=hint)


def to_prompt(sense: ContextSense, *, style_length: str = "medium") -> str:
    """把语境判断转成一小段 system 提示，叠加在人格设定之后。

    明确写出「这是猜测」，避免模型把情绪推断当成用户已确认的事实。
    """
    length_hint = {
        "short": "这次回复再短一点，一两句即可。",
        "medium": "这次回复长度适中。",
        "long": "这次可以稍微展开，但别刻意凑字数。",
    }.get(style_length, "这次回复长度适中。")

    return (
        "【这句话的语境判断（重要：这只是对「可能是什么」的猜测，不是已知事实）】\n"
        f"- 猜测类别：{sense.label}（confidence={sense.confidence}，未经用户确认）\n"
        f"- 回应方式：{sense.hint}\n"
        f"- {length_hint}\n"
        "- 不要把上面的猜测说成事实，不要说「我知道你……」「你一定……」；\n"
        "- 不确定时用「听起来像是……」「是不是……」自然澄清，不要连续追问。"
    )
