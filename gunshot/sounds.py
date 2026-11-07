"""Sound packs.

A pack is a named list of "variants" - short mono clips, one of which is
picked at random for every keypress. Packs come from two places:

  * built-in synthesized packs (``SYNTH_PACKS``), generated with numpy so
    the app needs no audio files for them;
  * folders of ``.wav`` files under ``gunshot/packs/<Pack Name>/``. Adding a
    new sound to the app is just dropping a folder in there - see
    ``gunshot/packs/README.md``.
"""

from __future__ import annotations

import io
import sys
import wave
from pathlib import Path
from typing import Callable

import numpy as np

SAMPLE_RATE = 44100


def _lowpass(signal: np.ndarray, alpha: float) -> np.ndarray:
    """One-pole low-pass filter. Smaller alpha = darker sound."""
    out = np.empty_like(signal)
    acc = 0.0
    for i, x in enumerate(signal):
        acc += alpha * (x - acc)
        out[i] = acc
    return out


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
    shot /= np.max(np.abs(shot))
    return shot.astype(np.float32)


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


def build_variants(count: int = 4) -> list[np.ndarray]:
    return [synth_gunshot(seed=i) for i in range(count)]


def read_wav(path: Path) -> np.ndarray:
    """Load a PCM WAV as float mono at SAMPLE_RATE, normalised to peak 1."""
    with wave.open(str(path), "rb") as wav:
        width = wav.getsampwidth()
        channels = wav.getnchannels()
        rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if width == 1:
        data = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
    elif width == 2:
        data = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
    elif width == 4:
        data = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648
    else:
        raise ValueError(f"{path.name}: unsupported {width * 8}-bit WAV (use 8/16/32-bit PCM)")
    data = data.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE and len(data) > 1:
        n = int(len(data) * SAMPLE_RATE / rate)
        data = np.interp(np.linspace(0, len(data) - 1, n), np.arange(len(data)), data)
    peak = np.max(np.abs(data)) if len(data) else 0
    if peak > 0:
        data = data / peak
    return data.astype(np.float32)


SYNTH_PACKS: dict[str, Callable[[], list[np.ndarray]]] = {
    "Gunshot": build_variants,
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


def available_packs(root: Path | None = None) -> list[str]:
    names = list(SYNTH_PACKS)
    names += [n for n in _wav_packs(root or packs_dir()) if n not in SYNTH_PACKS]
    return names


def load_pack(name: str, root: Path | None = None) -> list[np.ndarray]:
    """Return the variants for a pack, falling back to the default pack."""
    if name in SYNTH_PACKS:
        return SYNTH_PACKS[name]()
    files = _wav_packs(root or packs_dir()).get(name)
    if files:
        variants = []
        for f in files:
            try:
                variants.append(read_wav(f))
            except (OSError, ValueError, wave.Error):
                continue  # skip a broken file rather than failing the whole pack
        if variants:
            return variants
    return SYNTH_PACKS[DEFAULT_PACK]()
