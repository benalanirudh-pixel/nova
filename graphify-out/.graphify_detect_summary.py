import json
from pathlib import Path
d = json.loads(Path("graphify-out/.graphify_detect.json").read_text(encoding="utf-8"))
print("total_files:", d.get("total_files"))
print("total_words:", d.get("total_words"))
print("skipped_sensitive:", d.get("skipped_sensitive"))
for cat in ("code", "document", "paper", "image", "video"):
    files = d.get("files", {}).get(cat, [])
    print(f"{cat}: {len(files)} files")
