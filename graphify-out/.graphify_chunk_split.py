import json
from pathlib import Path
from collections import defaultdict

uncached = [l.strip() for l in Path('graphify-out/.graphify_uncached.txt').read_text(encoding='utf-8').splitlines() if l.strip()]

images = [f for f in uncached if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'))]
texts = [f for f in uncached if f not in images]

# Line counts
text_info = []
for f in texts:
    p = Path(f)
    try:
        lines = sum(1 for _ in p.open(encoding='utf-8', errors='replace'))
    except Exception:
        lines = -1
    text_info.append((f, lines))

big = [(f, l) for f, l in text_info if l > 2000]
small = [(f, l) for f, l in text_info if l <= 2000 and l >= 0]

# Build chunks: images first (1 each), then big text (1 each), then small text grouped
chunks = []
chunk_num = 1

for f in images:
    chunks.append({'num': chunk_num, 'files': [f]})
    chunk_num += 1

for f, l in big:
    chunks.append({'num': chunk_num, 'files': [f]})
    chunk_num += 1

# Group small text by top-level directory, then pack into chunks of <=20 files and <=6000 lines
by_dir = defaultdict(list)
for f, l in small:
    p = Path(f)
    top = str(Path(*p.parts[:2])) if len(p.parts) >= 2 else str(p.parts[0])
    by_dir[top].append((f, l))

# Flatten all small files, sorted by directory then by line count desc
all_small = []
for top in sorted(by_dir.keys()):
    for f, l in sorted(by_dir[top], key=lambda x: -x[1]):
        all_small.append((f, l))

# Pack into chunks
current = []
current_lines = 0
for f, l in all_small:
    if len(current) >= 20 or current_lines + l > 6000:
        if current:
            chunks.append({'num': chunk_num, 'files': [f for f, _ in current]})
            chunk_num += 1
        current = [(f, l)]
        current_lines = l
    else:
        current.append((f, l))
        current_lines += l
if current:
    chunks.append({'num': chunk_num, 'files': [f for f, _ in current]})

total = len(chunks)
print(f'Total chunks: {total}')
for c in chunks:
    lines = 0
    for f in c['files']:
        for ff, ll in text_info:
            if ff == f:
                lines += ll
                break
    print(f'  Chunk {c["num"]:02d}: {len(c["files"])} files, ~{lines} lines')

# Write chunk input files
for c in chunks:
    chunk_path = f'graphify-out/.graphify_chunk_{c["num"]:02d}.json'
    data = {
        'chunk_num': c['num'],
        'total_chunks': total,
        'deep_mode': False,
        'files': c['files']
    }
    Path(chunk_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')

print(f'\nWrote {total} chunk input files')
