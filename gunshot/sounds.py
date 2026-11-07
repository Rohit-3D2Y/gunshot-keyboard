"""Sound packs.

A pack is a list of "variants" - short mono clips. By default a random one
plays on every keypress; a *sequential* pack instead plays them in order
(e.g. one syllable of a phrase per key). A pack can also give particular
keys their own sound (e.g. a typewriter bell on Enter). Packs come from two
places:

  * built-in synthesized packs (``SYNTH_PACKS``), generated with numpy so
    the app needs no audio files for them;
  * folders of ``.wav`` files under ``gunshot/packs/<Pack Name>/``. Adding a
    new sound to the app is just dropping a folder in there - see
    ``gunshot/packs/README.md``.
"""

from __future__ import annotations

import io
import json
import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

SAMPLE_RATE = 44100


# Keys that a pack can give their own sound, by file-name prefix
# (enter01.wav, space.wav, ...). All other keys use the regular clips.
SPECIAL_KEYS = ("enter", "space", "backspace")


@dataclass
class Pack:
    variants: list[np.ndarray]
    sequential: bool = False
    special: dict[str, list[np.ndarray]] = field(default_factory=dict)


def _lowpass(signal: np.ndarray, alpha: float) -> np.ndarray:
    """One-pole low-pass filter. Smaller alpha = darker sound."""
    out = np.empty_like(signal)
    acc = 0.0
    for i, x in enumerate(signal):
        acc += alpha * (x - acc)
        out[i] = acc
    return out


def _normalise(samples: np.ndarray) -> np.ndarray:
    peak = np.max(np.abs(samples)) if len(samples) else 0
    return (samples / peak if peak > 0 else samples).astype(np.float32)


# --- Gunshot -----------------------------------------------------------------


def synth_gunshot(seed: int = 0, duration: float = 0.45) -> np.ndarray:
    """Return one gunshot as float32 mono samples in [-1, 1].

    The shot is built from three layers:
      * crack  - a very short, bright noise burst (the supersonic snap)
      * boom   - a pitched-down sine thump for body
      * tail   - darker, slowly decaying noise for the room echo
    """
    rng = np.random.default_rng(seed)
    n = int(SAMPLE_RATE * duration)
    t = np.arange(n) / SAMPLE_RATE

    # Small per-variant randomisation so repeated keypresses don't sound robotic.
    crack_decay = rng.uniform(55, 80)
    boom_start = rng.uniform(140, 190)
    boom_end = rng.uniform(40, 55)
    tail_decay = rng.uniform(7, 10)

    noise = rng.uniform(-1, 1, n)

    crack = noise * np.exp(-t * crack_decay)

    freq = boom_end + (boom_start - boom_end) * np.exp(-t * 25)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    boom = np.sin(phase) * np.exp(-t * 14)

    tail = _lowpass(rng.uniform(-1, 1, n), 0.08) * np.exp(-t * tail_decay)

    # Near-instant attack so the transient hits right on the keypress.
    attack = np.minimum(1.0, t / 0.0008)

    shot = attack * (0.9 * crack + 0.8 * boom + 1.6 * tail)
    # Soft clip for that overdriven, punchy character.
    shot = np.tanh(shot * 2.2)
    return _normalise(shot)


def build_variants(count: int = 4) -> list[np.ndarray]:
    return [synth_gunshot(seed=i) for i in range(count)]


# --- WAV packs ---------------------------------------------------------------


def to_wav_bytes(samples: np.ndarray, volume: float = 1.0) -> bytes:
    """Encode float mono samples as a 16-bit PCM WAV file in memory."""
    pcm = (np.clip(samples * volume, -1, 1) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())
    return buf.getvalue()


def read_wav(path: Path) -> np.ndarray:
    """Load a PCM WAV as float mono at SAMPLE_RATE, trimmed and normalised.

    Leading silence is cut off because any gap before the sound feels like
    input lag; trailing silence is cut so voices aren't held for nothing.
    """
    with wave.open(str(path), "rb") as wav:
        width = wav.getsampwidth()
        channels = wav.getnchannels()
        rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if width == 1:
        data = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
    elif width == 2:
        data = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        data = ((b[:, 0] << 8 | b[:, 1] << 16 | b[:, 2] << 24) >> 8).astype(np.float32) / 8388608
    elif width == 4:
        data = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648
    else:
        raise ValueError(f"{path.name}: unsupported {width * 8}-bit WAV (use 8/16/24/32-bit PCM)")
    data = data.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE and len(data) > 1:
        n = int(len(data) * SAMPLE_RATE / rate)
        data = np.interp(np.linspace(0, len(data) - 1, n), np.arange(len(data)), data)
    data = _normalise(data)
    loud = np.flatnonzero(np.abs(data) > 0.03)
    if len(loud):
        start = max(0, loud[0] - int(SAMPLE_RATE * 0.002))
        end = min(len(data), loud[-1] + int(SAMPLE_RATE * 0.05))
        data = data[start:end]
    return data.astype(np.float32)


SYNTH_PACKS: dict[str, Callable[[], Pack]] = {
    "Gunshot": lambda: Pack(build_variants()),
}

DEFAULT_PACK = "Gunshot"


def packs_dir() -> Path:
    # PyInstaller unpacks bundled data under sys._MEIPASS.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "gunshot" / "packs"


def _wav_packs(root: Path) -> dict[str, list[Path]]:
    if not root.is_dir():
        return {}
    packs = {}
    for folder in sorted(root.iterdir()):
        files = sorted(folder.glob("*.wav")) if folder.is_dir() else []
        if files:
            packs[folder.name] = files
    return packs


def _is_sequential(folder: Path) -> bool:
    """A pack.json with {"order": "sequence"} plays files in filename order."""
    try:
        meta = json.loads((folder / "pack.json").read_text(encoding="utf-8"))
        return meta.get("order") == "sequence"
    except (OSError, ValueError, AttributeError):
        return False


def available_packs(root: Path | None = None) -> list[str]:
    names = list(SYNTH_PACKS)
    names += [n for n in _wav_packs(root or packs_dir()) if n not in SYNTH_PACKS]
    return names


def load_pack(name: str, root: Path | None = None) -> Pack:
    """Return the named pack, falling back to the default pack."""
    if name in SYNTH_PACKS:
        return SYNTH_PACKS[name]()
    root = root or packs_dir()
    files = _wav_packs(root).get(name)
    if files:
        variants: list[np.ndarray] = []
        special: dict[str, list[np.ndarray]] = {}
        for f in files:
            try:
                clip = read_wav(f)
            except (OSError, ValueError, wave.Error):
                continue  # skip a broken file rather than failing the whole pack
            key = next((k for k in SPECIAL_KEYS if f.stem.lower().startswith(k)), None)
            (special.setdefault(key, []) if key else variants).append(clip)
        if variants:
            return Pack(variants, sequential=_is_sequential(root / name), special=special)
    return SYNTH_PACKS[DEFAULT_PACK]()
