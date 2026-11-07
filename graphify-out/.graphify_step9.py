import json
from pathlib import Path
from datetime import datetime, timezone

# Save manifest for --update
detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text(encoding="utf-8"))
extract = json.loads(Path('graphify-out/.graphify_extract.json').read_text(encoding="utf-8"))

corpus = detect.get('all_files') or detect['files']
partial = {l.strip() for l in Path('graphify-out/.graphify_partial.txt').read_text(encoding="utf-8").splitlines() if l.strip()} if Path('graphify-out/.graphify_partial.txt').exists() else set()

# Use a simplified manifest save - just stamp all code files and semantic files that produced output
manifest_files = {}
for cat, flist in detect.get('files', {}).items():
    for f in flist:
        manifest_files.setdefault(cat, []).append(f)

scan_corpus = {f for fl in corpus.values() for f in fl}

# Simple manifest save
from graphify.detect import save_manifest
save_manifest(manifest_files, root='C:\\Users\\Anirudh\\nova', scan_corpus=scan_corpus, clear_semantic=None)

# Update cost tracker
input_tok = extract.get('input_tokens', 0)
output_tok = extract.get('output_tokens', 0)
cost_path = Path('graphify-out/cost.json')
if cost_path.exists():
    cost = json.loads(cost_path.read_text(encoding="utf-8"))
else:
    cost = {'runs': [], 'total_input_tokens': 0, 'total_output_tokens': 0}
cost['runs'].append({
    'date': datetime.now(timezone.utc).isoformat(),
    'input_tokens': input_tok,
    'output_tokens': output_tok,
    'files': detect.get('total_files', 0),
})
cost['total_input_tokens'] += input_tok
cost['total_output_tokens'] += output_tok
cost_path.write_text(json.dumps(cost, indent=2, ensure_ascii=False), encoding="utf-8")
print(f'This run: {input_tok:,} input tokens, {output_tok:,} output tokens')
print(f'All time: {cost["total_input_tokens"]:,} input, {cost["total_output_tokens"]:,} output ({len(cost["runs"])} runs)')

# Clean up temp files
for f in ['.graphify_detect.json', '.graphify_extract.json', '.graphify_ast.json', '.graphify_semantic.json', '.graphify_analysis.json', '.graphify_partial.txt']:
    Path('graphify-out', f).unlink(missing_ok=True)
for stale in Path('graphify-out').glob('.graphify_chunk_*.json'):
    stale.unlink()
Path('graphify-out/.needs_update').unlink(missing_ok=True)
print('Cleanup complete')
