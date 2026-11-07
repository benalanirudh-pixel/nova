import json, glob
from pathlib import Path

chunks = sorted(glob.glob('graphify-out/.graphify_chunk_*.json'))
print(f'Found {len(chunks)} chunk files on disk')

all_nodes, all_edges, all_hyperedges = [], [], []
total_in, total_out = 0, 0
missing = []

for c in chunks:
    try:
        d = json.loads(Path(c).read_text(encoding="utf-8"))
        nodes = d.get('nodes', [])
        edges = d.get('edges', [])
        if not isinstance(nodes, list) or not isinstance(edges, list):
            missing.append(c)
            continue
        all_nodes += nodes
        all_edges += edges
        all_hyperedges += d.get('hyperedges', [])
        total_in += d.get('input_tokens', 0)
        total_out += d.get('output_tokens', 0)
        print(f'  {c}: {len(nodes)} nodes, {len(edges)} edges, {len(d.get("hyperedges", []))} hyperedges')
    except Exception as e:
        missing.append(c)
        print(f'  {c}: INVALID - {e}')

if missing:
    print(f'\nWARNING: {len(missing)} chunk(s) missing or invalid:')
    for m in missing:
        print(f'  {m}')

Path('graphify-out/.graphify_semantic_new.json').write_text(json.dumps({
    'nodes': all_nodes, 'edges': all_edges, 'hyperedges': all_hyperedges,
    'input_tokens': total_in, 'output_tokens': total_out,
}, indent=2, ensure_ascii=False), encoding="utf-8")
print(f'\nMerged {len(chunks)} chunks: {total_in:,} in / {total_out:,} out tokens')
print(f'Total: {len(all_nodes)} nodes, {len(all_edges)} edges, {len(all_hyperedges)} hyperedges')
