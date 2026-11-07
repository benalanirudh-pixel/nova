import json, glob
from pathlib import Path

covered = {}
for c in sorted(glob.glob('graphify-out/.graphify_chunk_*.json')):
    d = json.loads(Path(c).read_text(encoding="utf-8"))
    for src, n in (d.get('coverage') or {}).items():
        if isinstance(n, dict):
            n = n.get('lines', n.get('count', 0))
        covered[src] = max(covered.get(src, 0), int(n))

partial = []
for src, n in sorted(covered.items()):
    p = Path(src)
    if not p.is_absolute():
        p = Path('.') / src
    if not p.is_file():
        continue
    total = sum(1 for _ in p.open(encoding='utf-8', errors='replace'))
    if total and n < total:
        partial.append((src, n, total))

Path('graphify-out/.graphify_partial.txt').write_text('\n'.join(s for s, _, _ in partial), encoding="utf-8")
if partial:
    print(f'WARNING: {len(partial)} file(s) were only partly read:')
    for src, n, total in partial:
        print(f'  {src}: read {n} of {total} lines')
else:
    print('Coverage OK - every file a subagent reported was read to its last line')
