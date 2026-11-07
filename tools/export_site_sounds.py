"""Export short preview clips of every sound pack for the website (site/).

The landing page lets visitors try each sound in the browser, so it needs a
few clips per pack. Re-run after changing packs:  python tools/export_site_sounds.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from gunshot import sounds  # noqa: E402

CLIPS_PER_PACK = 5
out = root / "site" / "sounds"
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True)

manifest = []
for i, name in enumerate(sounds.available_packs()):
    pack = sounds.load_pack(name)
    slug = name.lower().replace(" ", "-")
    folder = out / slug
    folder.mkdir()
    # Sequential packs need every clip to make sense (ya-me-te-ku-da-sa-i).
    variants = pack.variants if pack.sequential else pack.variants[:CLIPS_PER_PACK]
    files = []
    for j, clip in enumerate(variants):
        (folder / f"{j}.wav").write_bytes(sounds.to_wav_bytes(clip, 0.9))
        files.append(f"sounds/{slug}/{j}.wav")
    special = {}
    for key, clips in pack.special.items():
        (folder / f"{key}.wav").write_bytes(sounds.to_wav_bytes(clips[0], 0.9))
        special[key] = f"sounds/{slug}/{key}.wav"
    manifest.append({"name": name, "slug": slug, "sequential": pack.sequential,
                     "clips": files, "special": special})

(out / "packs.json").write_text(json.dumps(manifest, indent=1))
size = sum(f.stat().st_size for f in out.rglob("*.wav"))
print(f"{len(manifest)} packs, {size / 1e6:.1f} MB of previews -> {out}")
