import json
from graphify.build import build_from_json
from graphify.cluster import score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json
from pathlib import Path

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text(encoding="utf-8"))
detection = json.loads(Path('graphify-out/.graphify_detect.json').read_text(encoding="utf-8"))
analysis = json.loads(Path('graphify-out/.graphify_analysis.json').read_text(encoding="utf-8"))

scan_root = Path(detection.get('scan_root', '.')).resolve()

G = build_from_json(extraction, root=str(scan_root), directed=False)
communities = {int(k): v for k, v in analysis['communities'].items()}
cohesion = {int(k): v for k, v in analysis['cohesion'].items()}
tokens = {'input': extraction.get('input_tokens', 0), 'output': extraction.get('output_tokens', 0)}

# LABELS for top communities by size
labels = {
    0: "UI/UX Pro Max Tests",
    1: "Design Token System",
    2: "Market Data Engine",
    3: "Context Model Layer",
    4: "Search Brief Results",
    5: "Engine History Session",
    6: "Datetime Inspect Icons",
    7: "BM25 Search Core",
    8: "BM25 Search Core",
    9: "HTML History Session",
    10: "Market Feed Tool",
    11: "Async Cron Init",
    12: "Analysis Lab Block",
    13: "SVG Color Generate",
    14: "Voice Whisper NDArray",
    15: "Type Value System",
    16: "Type Value System",
    17: "Market Scanner Breadth",
    18: "Dashboard Panels",
    19: "UI System Palette",
}
# All other communities keep placeholder "Community N" labels
for cid in communities:
    if cid not in labels:
        labels[cid] = f'Community {cid}'

# Regenerate questions with real community labels
questions = suggest_questions(G, communities, labels)

report = generate(G, communities, cohesion, labels, analysis['gods'], analysis['surprises'], detection, tokens, str(scan_root), suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report, encoding="utf-8")
Path('graphify-out/.graphify_labels.json').write_text(json.dumps({str(k): v for k, v in labels.items()}, ensure_ascii=False), encoding="utf-8")

# Re-export graph.json with community labels
wrote = to_json(G, communities, 'graphify-out/graph.json', community_labels=labels)
if not wrote:
    print('ERROR: refused to shrink graphify-out/graph.json (#479).')
print('Report updated with community labels')
