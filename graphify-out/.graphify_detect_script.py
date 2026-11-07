import json
from graphify.detect import detect
from pathlib import Path
from graphify.paths import out_path
from graphify.watch import _read_build_excludes, _read_build_gitignore
result = detect(Path('.'), extra_excludes=_read_build_excludes(out_path()), gitignore=_read_build_gitignore(out_path()))
Path('graphify-out/.graphify_detect.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
print(f'Detected {result["total_files"]} files')
print(f'Words: {result.get("total_words", 0)}')
for cat in ('code', 'document', 'paper', 'image', 'video'):
    n = len(result.get('files', {}).get(cat, []))
    if n:
        print(f'  {cat}: {n}')
