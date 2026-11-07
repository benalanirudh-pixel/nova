import json
from pathlib import Path
from collections import Counter

analysis = json.loads(Path('graphify-out/.graphify_analysis.json').read_text(encoding="utf-8"))
communities = analysis['communities']

# Count nodes per community
sizes = {int(k): len(v) for k, v in communities.items()}
sorted_sizes = sorted(sizes.items(), key=lambda x: -x[1])

print(f'Total communities: {len(sizes)}')
print(f'Top 20 communities by size:')
for cid, size in sorted_sizes[:20]:
    # Get first few node labels as hints
    nodes = communities[str(cid)]
    hints = [n.split('_')[-1] for n in nodes[:5]]
    print(f'  Community {cid}: {size} nodes, e.g. {hints}')

print(f'\nCommunities with >10 nodes: {sum(1 for s in sizes.values() if s > 10)}')
print(f'Communities with >50 nodes: {sum(1 for s in sizes.values() if s > 50)}')
print(f'Communities with >100 nodes: {sum(1 for s in sizes.values() if s > 100)}')
print(f'Single-node communities: {sum(1 for s in sizes.values() if s == 1)}')
