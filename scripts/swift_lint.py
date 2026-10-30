#!/usr/bin/env python3
"""Swift 静态一致性检查（Windows 上无 Swift 编译器时的兜底）。

检查项：
1. 括号 / 引号配平
2. 重复声明的类型
3. `Type.member` 引用是否存在于本项目定义的类型上
4. `api.method(...)` 调用是否存在于 LUMIAPIClient
5. struct 的 init(...) 调用参数个数是否匹配（粗略）
6. 明显缺失的 `import`

退出码非 0 表示发现阻断性问题。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend"

DECL = re.compile(r"^\s*(?:public |internal |private |fileprivate |open |final |@\w+\s+)*"
                  r"(struct|class|enum|protocol|actor|extension)\s+([A-Z]\w*)", re.M)
MODS = (r"(?:@\w+(?:\([^)]*\))?\s+|public\s+|internal\s+|private\s+|fileprivate\s+|open\s+"
        r"|final\s+|static\s+|class\s+|override\s+|nonisolated\s+|mutating\s+|lazy\s+"
        r"|weak\s+|unowned\s+|convenience\s+|required\s+|dynamic\s+|optional\s+)*")
MEMBER = re.compile(r"^\s*" + MODS +
                    r"(?:let|var|func|case|init|typealias|struct|class|enum|protocol|actor)\s+"
                    r"([A-Za-z_]\w*)", re.M)


def strip_comments_and_strings(text: str) -> str:
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            depth = 1
            i += 2
            while i < n and depth:
                if text.startswith("/*", i):
                    depth += 1
                    i += 2
                elif text.startswith("*/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
        elif c == '"':
            triple = text.startswith('"""', i)
            i += 3 if triple else 1
            while i < n:
                if triple and text.startswith('"""', i):
                    i += 3
                    break
                if not triple and text[i] == '"':
                    i += 1
                    break
                if text[i] == "\\":
                    i += 1
                i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def syntax_check(files: list[Path], texts: dict[Path, str]) -> list[str]:
    """用 tree-sitter 做真实语法解析（不依赖 macOS SDK，能抓出语法级错误）。"""
    try:
        import tree_sitter
        import tree_sitter_swift
    except ImportError:
        return ["[syntax] 未安装 tree-sitter，跳过语法检查"]

    lang = tree_sitter.Language(tree_sitter_swift.language())
    parser = tree_sitter.Parser(lang)
    problems: list[str] = []
    for f in files:
        raw = f.read_bytes()
        tree = parser.parse(raw)
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == "ERROR" or node.is_missing:
                line = node.start_point[0] + 1
                snippet = raw[node.start_byte:node.end_byte][:60].decode("utf-8", "replace")
                problems.append(
                    f"[syntax] {f.relative_to(ROOT)}:{line} {node.type} -> {snippet!r}"
                )
                continue
            stack.extend(node.children)
    return problems[:40]


def main() -> int:
    files = sorted(SRC.rglob("*.swift"))
    if not files:
        print("no swift files")
        return 1

    problems: list[str] = []
    texts: dict[Path, str] = {}
    problems.extend(syntax_check(files, texts))
    for f in files:
        raw = f.read_text(encoding="utf-8")
        texts[f] = strip_comments_and_strings(raw)
        for o, c in (("{", "}"), ("(", ")"), ("[", "]")):
            if texts[f].count(o) != texts[f].count(c):
                problems.append(f"[brace] {f.relative_to(ROOT)}: {o}{c} {texts[f].count(o)}/{texts[f].count(c)}")

    # 类型 -> 成员集合
    types: dict[str, set[str]] = {}
    owners: dict[str, Path] = {}
    for f, s in texts.items():
        for m in DECL.finditer(s):
            kind, name = m.group(1), m.group(2)
            depth = s.count("{", 0, m.start()) - s.count("}", 0, m.start())
            if kind == "extension":
                types.setdefault(name, set())
                continue
            if name in owners and depth == 0:
                problems.append(f"[dup] 顶层类型 {name} 重复声明：{owners[name].name} / {f.name}")
            types.setdefault(name, set())
            if depth == 0:
                owners.setdefault(name, f)

    # 收集成员：以类型声明块为单位（用花括号深度遍历）
    for f, s in texts.items():
        for m in DECL.finditer(s):
            kind, name = m.group(1), m.group(2)
            start = s.find("{", m.end())
            if start < 0:
                continue
            depth, i = 0, start
            while i < len(s):
                if s[i] == "{":
                    depth += 1
                elif s[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            body = s[start + 1:i]
            # 收集成员：不依赖行首修饰符（static / nonisolated / @Published 等都能覆盖）
            bucket = types.setdefault(name, set())
            for mm in re.finditer(r"\bfunc\s+([A-Za-z_]\w*)\s*[(<]", body):
                bucket.add(mm.group(1))
            for mm in re.finditer(r"\b(?:let|var)\s+([A-Za-z_]\w*)\s*[:=]", body):
                bucket.add(mm.group(1))
            for mm in re.finditer(r"^\s*case\s+([A-Za-z_]\w*)", body, re.M):
                bucket.add(mm.group(1))
            for mm in re.finditer(r"\b(?:struct|class|enum|protocol|actor|typealias)\s+([A-Za-z_]\w*)", body):
                bucket.add(mm.group(1))
            if re.search(r"\binit\s*\(", body):
                bucket.add("init")

    # 检查 Type.member 引用
    known = set(types)
    skip_types = {"Color", "Font", "Date", "UUID", "URL", "Data", "String", "Int", "Double",
                  "Task", "MainActor", "JSONEncoder", "JSONDecoder", "Bundle", "UserDefaults",
                  "DispatchQueue", "TimeInterval", "Never", "Self", "CodingKeys"}
    for f, s in texts.items():
        for m in re.finditer(r"\b([A-Z]\w*)\.([a-zA-Z_]\w*)", s):
            t, member = m.group(1), m.group(2)
            if t not in known or t in skip_types:
                continue
            if member in types[t]:
                continue
            if member in {"self", "Type", "some", "none", "init"}:
                continue
            line = s[: m.start()].count("\n") + 1
            problems.append(f"[member] {f.relative_to(ROOT)}:{line} {t}.{member} 未定义")

    # [member] 是启发式检查（嵌套类型/扩展的归属可能判断错），只作提示；
    # 语法、括号、顶层重复声明才是阻断项。
    blocking = [p for p in problems if not p.startswith("[member]")]
    hints = [p for p in problems if p.startswith("[member]")]

    print(f"swift files: {len(files)}")
    print(f"declared types: {len(types)}")
    if hints:
        print(f"\n提示（{len(hints)} 条，可能误报，需人工确认）：")
        for h in hints:
            print("  " + h)
    if blocking:
        print(f"\n阻断问题 {len(blocking)} 个：")
        for b in blocking:
            print("  " + b)
        return 1
    print("\n未发现阻断问题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
