import json, os
from pathlib import Path

detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text(encoding='utf-8'))
scan_root = Path(detect['scan_root']).resolve()
all_files = []
for cat in ('code', 'document', 'paper', 'image', 'video'):
    all_files.extend(detect.get('files', {}).get(cat, []))

gfx = scan_root / 'graphify-out'
counts = {}
for f in all_files:
    p = Path(f)
    if not p.is_absolute():
        p = scan_root / p
    try:
        p.resolve().relative_to(gfx.resolve())
        continue  # skip graphify-out sidecars
    except ValueError:
        pass
    try:
        rel = p.resolve().relative_to(scan_root.resolve())
    except ValueError:
        continue
    parts = rel.parts
    if len(parts) == 1:
        key = '(root)'
    else:
        key = parts[0]
    counts[key] = counts.get(key, 0) + 1

for key, n in sorted(counts.items(), key=lambda x: -x[1])[:5]:
    print(f'{key}: {n} files')
