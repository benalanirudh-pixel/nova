import json
d = json.loads(open('graphify-out/graph.json', encoding='utf-8').read())
print(f'Keys: {list(d.keys())}')
print(f'Nodes: {len(d.get("nodes", []))}')
print(f'Edges: {len(d.get("edges", []))}')
print(f'Hyperedges: {len(d.get("graph", {}).get("hyperedges", []))}')
