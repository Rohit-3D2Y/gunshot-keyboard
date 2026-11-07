"""Download the openly licensed sound packs from Wikimedia Commons.

Every source file, its license and author is listed in MANIFEST below and
recorded in gunshot/packs/CREDITS.md, so the bundled audio is fully
attributable. Re-running the script rebuilds the packs from scratch.

Processing per pack: decode -> mono 44.1 kHz -> optionally split a recording
that contains several sounds at its silent gaps -> trim silence -> cap the
length (with a fade) so a keypress sound never drags on -> 16-bit WAV.

Windows only (MP3 decoding uses Windows' built-in Media Foundation via
tools/to_wav.ps1). Usage:
    python tools/fetch_sounds.py [Pack Name ...]   rebuild packs (default: all)
    python tools/fetch_sounds.py --credits         only regenerate CREDITS.md
"""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gunshot.sounds import SAMPLE_RATE, packs_dir, read_wav, to_wav_bytes  # noqa: E402

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "gunshot-sound-pack-builder/1.0 (open-source keyboard sound app)"}

JP = "LL-Q5287 (jpn)-Fukujinzuke-{}.wav"

# pack name -> settings and source files on Wikimedia Commons.
#   split:    cut each source at silent gaps into separate clips
#   max_len:  seconds; longer clips are faded out at this point
#   min_len:  seconds; shorter split-off pieces (breaths, clicks) are dropped
#   keystrokes: N - the source is continuous typing; cut out N single keystrokes
# A file prefix of enter/space/backspace makes that clip play only on that key.
#   sequence: play clips in order (one per keypress) instead of at random
MANIFEST: dict[str, dict] = {
    "Yamete Kudasai": {
        "sequence": True,
        "max_len": 0.6,
        "files": [
            ("01_ya", JP.format("や")),
            ("02_me", JP.format("め")),
            ("03_te", JP.format("て")),
            ("04_ku", JP.format("く")),
            ("05_da", JP.format("だ")),
            ("06_sa", JP.format("さ")),
            ("07_i", JP.format("い")),
        ],
    },
    "Moan": {
        "split": True,
        "max_len": 1.2,
        "min_len": 0.2,
        "files": [
            ("sigh", "Three sighs.ogg"),
            ("sigh", "Four sighs.ogg"),
            ("hm", "Hm and sigh.ogg"),
        ],
    },
    "Zombie": {
        "max_len": 1.5,
        "files": [("zombie", "Zombie moan.ogg")],
    },
    "Cat": {
        "max_len": 1.0,
        "files": [
            ("meow", "MeowUSA.wav"),
            ("meow", "Meow of a Siamese cat - freemaster2.wav"),
            ("meow", "Kcg-nyan (scar).ogg"),
            ("meow", "Maullido de gata hembra joven.ogg"),
            ("meow", "2015-11-24.νιαούρισμα.Νιάου.noise reduced.flac"),
        ],
    },
    "Duck": {
        "split": True,
        "max_len": 0.6,
        "files": [
            ("quack", "Mudchute duck 1.ogg"),
            ("quack", "Mudchute duck 2.ogg"),
            ("squeak", "Rubber Duck Squeaker.ogg"),
        ],
    },
    "Fart": {
        "split": True,
        "max_len": 1.0,
        "files": [
            ("fart", "Fart (avk).wav"),
            ("fart", "Human fart.wav"),
            ("fart", "Flatus.wav"),
            ("fart", "Flatulence.wav"),
        ],
    },
    "Laser": {
        "max_len": 0.5,
        "files": [
            ("laser", "Laser 1 (Gravity Sound).wav"),
            ("laser", "Laser 2 (Gravity Sound).wav"),
            ("laser", "Laser 3 (Gravity Sound).wav"),
            ("laser", "Laser 4 (Gravity Sound).wav"),
            ("laser", "Laser 5 (Gravity Sound).wav"),
        ],
    },
    "Punch": {
        "split": True,
        "max_len": 0.5,
        "files": [("punch", "Punch.wav")],
    },
    "Mechanical Keyboard": {  # Cherry MX Blue: the classic clicky mechanical sound
        "keystrokes": 12,
        "files": [("key", "Cherry mx blue sound for ncherry company gmbh.wav")],
    },
    "Thocky Keyboard": {  # linear switches: deeper, softer "thock"
        "keystrokes": 12,
        "files": [("key", "Typing on Keychron V1 Ultra (Red Linear Switch).wav")],
    },
    "IBM Model M": {  # buckling-spring keyboard from 1986
        "keystrokes": 12,
        "files": [("key", "Typing - Model M 1986.ogg")],
    },
    "Typewriter": {
        "keystrokes": 8,
        "length": 0.2,
        "files": [
            ("key", "WWS Typewriter.ogg"),
            ("key", "Smith-Corona Prestige Auto 12 typing.ogg"),
            ("enter", "406243 stubb typewriter-ding-near-mono.wav"),  # carriage-return bell
        ],
    },
}

MAX_CLIPS_PER_SOURCE = 4
CACHE = ROOT / "build" / "sound-cache"  # decoded downloads, so re-runs skip Commons


# --- Commons access ----------------------------------------------------------


def _get(url: str, binary: bool = False):
    for attempt in range(6):
        try:
            time.sleep(2)  # be polite; Commons rate-limits bursts
            data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
            return data if binary else json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"rate limited: {url}")


def file_info(title: str) -> dict:
    params = {
        "action": "query",
        "prop": "videoinfo",  # like imageinfo, plus the transcoded derivatives
        "viprop": "url|mime|extmetadata|derivatives",
        "titles": f"File:{title}",
        "format": "json",
    }
    page = next(iter(_get(API + "?" + urllib.parse.urlencode(params))["query"]["pages"].values()))
    if "videoinfo" not in page:
        raise FileNotFoundError(title)
    ii = page["videoinfo"][0]
    meta = ii.get("extmetadata", {})

    def text(key: str) -> str:
        raw = meta.get(key, {}).get("value", "")
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()

    mp3 = [d["src"] for d in ii.get("derivatives", []) if d.get("type") == "audio/mpeg"]
    return {
        "title": title,
        "url": ii["url"].split("?", 1)[0],
        "mp3_url": mp3[0].split("?", 1)[0] if mp3 else None,
        "mime": ii.get("mime", ""),
        "page": f"https://commons.wikimedia.org/wiki/File:{urllib.parse.quote(title.replace(' ', '_'))}",
        "license": text("LicenseShortName"),
        "author": text("Artist") or "unknown",
    }


def _windows_decode(src: Path, dest: Path) -> None:
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(ROOT / "tools" / "to_wav.ps1"), str(src), str(dest)],
        check=True, capture_output=True,
    )


def download_as_wav(info: dict, dest: Path) -> None:
    if info["mime"] in ("audio/wav", "audio/x-wav"):
        dest.write_bytes(_get(info["url"], binary=True))
        try:
            wave.open(str(dest)).close()
        except wave.Error:  # e.g. 32-bit float WAV: re-encode as 16-bit PCM
            original = dest.with_suffix(".orig.wav")
            dest.replace(original)
            _windows_decode(original, dest)
        return
    # Commons serves an MP3 transcode of audio files, which Windows can decode.
    if not info["mp3_url"]:
        raise RuntimeError(f"no MP3 transcode available for {info['title']}")
    mp3 = dest.with_suffix(".mp3")
    mp3.write_bytes(_get(info["mp3_url"], binary=True))
    _windows_decode(mp3, dest)


# --- audio processing --------------------------------------------------------


def split_on_silence(x: np.ndarray, gap: float = 0.12, min_len: float = 0.08) -> list[np.ndarray]:
    """Cut a recording into separate sounds wherever it goes quiet for `gap` s."""
    win = int(SAMPLE_RATE * 0.01)
    env = np.convolve(np.abs(x), np.ones(win) / win, mode="same")
    loud = env > max(0.04, env.max() * 0.08)
    clips, start, quiet = [], None, 0
    for i, on in enumerate(loud):
        if on:
            if start is None:
                start = i
            quiet = 0
        elif start is not None:
            quiet += 1
            if quiet > gap * SAMPLE_RATE:
                end = i - quiet + int(SAMPLE_RATE * 0.03)
                if end - start > min_len * SAMPLE_RATE:
                    clips.append(x[start:end])
                start, quiet = None, 0
    if start is not None and len(x) - start > min_len * SAMPLE_RATE:
        clips.append(x[start:])
    return clips or [x]


def find_onsets(x: np.ndarray, hop: float = 0.002, min_gap: float = 0.07) -> list[int]:
    """Sample positions where a new transient (e.g. a keystroke) starts."""
    h = int(SAMPLE_RATE * hop)
    frames = len(x) // h
    env = np.sqrt(np.mean(x[: frames * h].reshape(frames, h) ** 2, axis=1)) + 1e-6
    look = int(0.02 / hop)  # compare with the quietest level in the last 20 ms
    floor = np.array([env[max(0, i - look) : i].min() if i else env[0] for i in range(frames)])
    thresh = max(np.percentile(env, 60) * 2, env.max() * 0.05)
    onsets, last = [], -(10**9)
    for i in range(1, frames):
        if env[i] > thresh and env[i] > floor[i] * 4 and (i - last) * hop >= min_gap:
            onsets.append(i * h)
            last = i
    return onsets


def slice_keystrokes(x: np.ndarray, count: int, length: float = 0.16) -> list[np.ndarray]:
    """Cut `count` clean single keystrokes out of a recording of typing."""
    onsets = find_onsets(x)
    clips = []
    for k, start in enumerate(onsets):
        start = max(0, start - int(SAMPLE_RATE * 0.002))
        # Stop before the next keystroke so no clip contains two hits.
        nxt = onsets[k + 1] - int(SAMPLE_RATE * 0.005) if k + 1 < len(onsets) else len(x)
        clip = x[start : min(start + int(SAMPLE_RATE * length), nxt)].copy()
        if len(clip) < SAMPLE_RATE * 0.06:
            continue
        fade = min(len(clip) // 3, int(SAMPLE_RATE * 0.03))
        clip[-fade:] *= np.linspace(1, 0, fade)
        clips.append(clip)
    if len(clips) <= count:
        return clips
    # Rank by strike strength: skip the single loudest (often a bang or a
    # slammed key), keep firm key-downs (key-ups are quieter), then spread the
    # picks across that group so the set varies without one clip sticking out.
    ranked = sorted(clips, key=lambda c: -np.max(np.abs(c)))
    pool = ranked[1 : 1 + count * 3]
    picks = np.linspace(0, len(pool) - 1, count).round().astype(int)
    return [pool[i] for i in picks]


def cap_length(x: np.ndarray, max_len: float) -> np.ndarray:
    n = int(SAMPLE_RATE * max_len)
    if len(x) <= n:
        return x
    x = x[:n].copy()
    fade = int(SAMPLE_RATE * 0.08)
    x[-fade:] *= np.linspace(1, 0, fade)
    return x


def build_pack(name: str, spec: dict, work: Path) -> list[dict]:
    out = packs_dir() / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    credits, counter = [], {}
    for prefix, title in spec["files"]:
        info = file_info(title)
        raw = CACHE / (re.sub(r"[^\w.-]+", "_", title) + ".wav")
        if not raw.exists():
            CACHE.mkdir(parents=True, exist_ok=True)
            tmp = work / raw.name
            download_as_wav(info, tmp)
            shutil.move(str(tmp), raw)
        audio = read_wav(raw)  # mono, 44.1 kHz, normalised, trimmed
        if spec.get("keystrokes") and prefix == "key":
            clips = slice_keystrokes(audio, spec["keystrokes"], spec.get("length", 0.16))
        elif spec.get("split"):
            clips = split_on_silence(audio, min_len=spec.get("min_len", 0.08))[:MAX_CLIPS_PER_SOURCE]
        else:
            clips = [audio]
        for clip in clips:
            clip = cap_length(clip, spec.get("max_len", 1.0))
            peak = np.max(np.abs(clip))
            clip = clip / peak if peak > 0 else clip
            if spec.get("keystrokes") and prefix != "key":
                clip = clip * 0.7  # e.g. the typewriter bell: don't drown the keys
            if spec.get("sequence"):
                fname = f"{prefix}.wav"
            else:
                counter[prefix] = counter.get(prefix, 0) + 1
                fname = f"{prefix}{counter[prefix]:02d}.wav"
            (out / fname).write_bytes(to_wav_bytes(clip.astype(np.float32), 0.95))
        credits.append(info)
        print(f"  {name}: {title} -> {len(clips)} clip(s) [{info['license']}]")
    if spec.get("sequence"):
        (out / "pack.json").write_text(json.dumps({"order": "sequence"}, indent=2) + "\n")
    return credits


def write_credits(all_credits: dict[str, list[dict]]) -> None:
    path = packs_dir() / "CREDITS.md"
    lines = [
        "# Sound credits",
        "",
        "The built-in **Gunshot** is synthesized in code (`gunshot/sounds.py`).",
        "The packs below use recordings from Wikimedia Commons,",
        "trimmed and normalised by `tools/fetch_sounds.py`. Each file keeps its",
        "original license; follow the links for full terms.",
        "",
    ]
    for pack, credits in all_credits.items():
        lines += [f"## {pack}", ""]
        for c in credits:
            lines.append(f"- [{c['title']}]({c['page']}) by {c['author']} - {c['license']}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    credits_file = packs_dir() / "credits.json"
    all_credits = json.loads(credits_file.read_text(encoding="utf-8")) if credits_file.exists() else {}
    if sys.argv[1:] == ["--credits"]:
        for name, spec in MANIFEST.items():
            all_credits[name] = [file_info(title) for _, title in spec["files"]]
    else:
        with tempfile.TemporaryDirectory() as tmp:
            for name in sys.argv[1:] or list(MANIFEST):
                all_credits[name] = build_pack(name, MANIFEST[name], Path(tmp))
    all_credits = {k: all_credits[k] for k in MANIFEST if k in all_credits}
    credits_file.write_text(json.dumps(all_credits, indent=1, ensure_ascii=False), encoding="utf-8")
    write_credits(all_credits)
    print("done")


if __name__ == "__main__":
    main()
