"""Deterministic source-package gates; never reads .env or chat contents."""
from pathlib import Path
import ast
import json
import plistlib
import sys

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT):
    problems = []
    for path in (root/'backend/app').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                names = [n.target.id for n in node.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)]
                if len(names) != len(set(names)):
                    problems.append(f'Duplicate annotated fields: {path.relative_to(root)}:{node.name}')
    plist = plistlib.loads((root/'frontend/LUMI/Info.plist').read_bytes())
    for key in ('CADisableMinimumFrameDurationOnPhone', 'NSFaceIDUsageDescription', 'UILaunchScreen'):
        if key not in plist or plist[key] is False:
            problems.append('Missing plist requirement: '+key)
    for path in (root/'frontend/LUMI/Resources/Assets.xcassets').rglob('Contents.json'):
        for image in json.loads(path.read_text()).get('images', []):
            if 'filename' in image and not (path.parent/image['filename']).is_file():
                problems.append('Missing asset: '+str(path.relative_to(root)))
    for path in root.rglob('*'):
        if path.suffix == '.ipa' or path.name in ('relay_demo.db', 'relay_transcript.json'):
            problems.append('Generated/runtime file in source package: '+str(path.relative_to(root)))
    return problems


if __name__ == '__main__':
    problems = check()
    print(json.dumps({'passed': not problems, 'problems': problems, 'scope': 'source structure only; no iOS runtime/FPS validation'}, indent=2))
    sys.exit(bool(problems))
