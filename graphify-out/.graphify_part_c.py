import json
from pathlib import Path
import glob

# Read AST
ast = json.loads(Path('graphify-out/.graphify_ast.json').read_text(encoding='utf-8'))
print(f'AST: {len(ast["nodes"])} nodes, {len(ast["edges"])} edges')

# Collect all semantic chunks
semantic_nodes = []
semantic_edges = []
semantic_hyperedges = []
total_in = 0
total_out = 0
chunks_processed = 0

for c in sorted(glob.glob('graphify-out/.graphify_chunk_*.json')):
    d = json.loads(Path(c).read_text(encoding='utf-8'))
    # Skip input-only chunk files (they have 'files' key but no 'nodes')
    if 'nodes' not in d:
        continue
    semantic_nodes += d.get('nodes', [])
    semantic_edges += d.get('edges', [])
    semantic_hyperedges += d.get('hyperedges', [])
    total_in += d.get('input_tokens', 0)
    total_out += d.get('output_tokens', 0)
    chunks_processed += 1

print(f'Semantic chunks processed: {chunks_processed}')
print(f'Semantic: {len(semantic_nodes)} nodes, {len(semantic_edges)} edges, {len(semantic_hyperedges)} hyperedges')

# Stamp tier provenance on semantic side
for n in semantic_nodes:
    n.setdefault('_origin', 'semantic')
for e in semantic_edges:
    e.setdefault('_origin', 'semantic')

# Merge: AST nodes first, semantic nodes deduplicated by id
seen = {n['id'] for n in ast['nodes']}
merged_nodes = list(ast['nodes'])
ast_node_count = len(ast['nodes'])
sem_new = 0
for n in semantic_nodes:
    if n['id'] not in seen:
        merged_nodes.append(n)
        seen.add(n['id'])
        sem_new += 1

merged_edges = ast['edges'] + semantic_edges
merged_hyperedges = semantic_hyperedges

merged = {
    'nodes': merged_nodes,
    'edges': merged_edges,
    'hyperedges': merged_hyperedges,
    'input_tokens': total_in,
    'output_tokens': total_out,
}
Path('graphify-out/.graphify_extract.json').write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'Merged: {len(merged_nodes)} nodes ({ast_node_count} AST + {sem_new} new semantic), {len(merged_edges)} edges ({len(ast["edges"])} AST + {len(semantic_edges)} semantic), {len(merged_hyperedges)} hyperedges')
