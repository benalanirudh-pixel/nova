import json
from graphify.cache import save_semantic_cache
from pathlib import Path

SPEC_PATH = r'C:\Users\Anirudh\.agents\skills\graphify\references\extraction-spec.md'
scan_root = r'C:\Users\Anirudh\nova'

new = json.loads(Path('graphify-out/.graphify_semantic_new.json').read_text(encoding="utf-8")) if Path('graphify-out/.graphify_semantic_new.json').exists() else {'nodes':[],'edges':[],'hyperedges':[]}
uncached = [line for line in Path('graphify-out/.graphify_uncached.txt').read_text(encoding="utf-8").splitlines() if line]
partial = [line for line in Path('graphify-out/.graphify_partial.txt').read_text(encoding="utf-8").splitlines() if line] if Path('graphify-out/.graphify_partial.txt').exists() else []

saved = save_semantic_cache(new.get('nodes', []), new.get('edges', []), new.get('hyperedges', []), root=scan_root, allowed_source_files=uncached, prompt_file=SPEC_PATH, partial_source_files=partial)
note = f' ({len(partial)} left partial for retry)' if partial else ''
print(f'Cached {saved} files' + note)
