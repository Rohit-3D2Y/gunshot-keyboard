"""Low-latency, overlapping playback using each OS's built-in audio.

No third-party audio library is needed: Windows uses MCI (winmm.dll) and
macOS uses AppKit's NSSound. Either way a pool of "voices" is used
round-robin so fast typing gets overlapping shots instead of each one
cutting off the last. All OS calls happen on one worker thread so the
keyboard hook never blocks.
"""

from __future__ import annotations

import ctypes
import queue
import shutil
import subprocess
import sys
import random
import tempfile
import threading
import time
from pathlib import Path

from . import sounds


class Player:
    # Voices per clip: how many copies of one clip can overlap at once.
    VOICES_PER_CLIP = 3
    # A sequential pack starts over from its first clip after this pause.
    SEQUENCE_RESET_SECONDS = 2.0

    def __init__(self, pack: sounds.Pack, volume: float) -> None:
        self._dir = Path(tempfile.mkdtemp(prefix="gunshot-"))
        self._queue: queue.Queue = queue.Queue()
        self._pack = pack
        self._volume = volume
        self._clip = -1
        self._last_fire = 0.0
        self._voice_cursor: list[int] = []
        self._special_clips: dict[str, list[int]] = {}
        self._generation = 0
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()
        self._queue.put(("load", None))

    # --- public API (any thread) --------------------------------------------

    def fire(self, key: str | None = None) -> None:
        """Play a sound; `key` ("enter", "space", ...) picks that key's own sound."""
        self._queue.put(("fire", key))

    def set_volume(self, volume: float) -> None:
        self._volume = volume
        self._queue.put(("load", None))

    def set_pack(self, pack: sounds.Pack) -> None:
        self._pack = pack
        self._queue.put(("load", None))

    def close(self) -> None:
        self._queue.put(("stop", None))
        self._worker.join(timeout=2)

    # --- worker thread -------------------------------------------------------

    def _run(self) -> None:
        while True:
            cmd, arg = self._queue.get()
            try:
                if cmd == "fire":
                    clip = self._pick_clip(arg)
                    cursor = self._voice_cursor[clip]
                    self._voice_cursor[clip] = (cursor + 1) % self.VOICES_PER_CLIP
                    self._play(clip * self.VOICES_PER_CLIP + cursor)
                elif cmd == "load":
                    self._reload()
                elif cmd == "stop":
                    self._unload()
                    shutil.rmtree(self._dir, ignore_errors=True)
                    return
            except Exception:  # never let one bad sound kill the audio thread
                pass

    def _pick_clip(self, key: str | None) -> int:
        if key in self._special_clips:
            return random.choice(self._special_clips[key])
        count = len(self._pack.variants)
        now = time.monotonic()
        if self._pack.sequential:
            if now - self._last_fire > self.SEQUENCE_RESET_SECONDS:
                self._clip = -1
            self._clip = (self._clip + 1) % count
        elif count > 1:
            # Random, but never the same clip twice in a row.
            self._clip = random.choice([c for c in range(count) if c != self._clip])
        else:
            self._clip = 0
        self._last_fire = now
        return self._clip

    def _reload(self) -> None:
        self._unload()
        # Fresh file names each time: the OS may still hold the old ones open.
        self._generation += 1
        # Clip indexes: regular variants first, then each special key's clips.
        clips = list(self._pack.variants)
        self._special_clips = {}
        for key, special in self._pack.special.items():
            self._special_clips[key] = list(range(len(clips), len(clips) + len(special)))
            clips += special
        voice_files = []
        for i, clip in enumerate(clips):
            path = self._dir / f"clip{self._generation}_{i}.wav"
            path.write_bytes(sounds.to_wav_bytes(clip, self._volume))
            voice_files += [path] * self.VOICES_PER_CLIP
        self._clip = -1
        self._voice_cursor = [0] * len(clips)
        self._load(voice_files)

    # Subclasses implement these; they always run on the worker thread.
    def _load(self, voice_files: list[Path]) -> None: ...
    def _play(self, voice: int) -> None: ...
    def _unload(self) -> None: ...


class WindowsPlayer(Player):
    _voices = 0

    @staticmethod
    def _mci(command: str) -> None:
        ctypes.windll.winmm.mciSendStringW(command, None, 0, None)

    def _load(self, voice_files: list[Path]) -> None:
        for v, path in enumerate(voice_files):
            self._mci(f'open "{path}" type waveaudio alias gunshot{v}')
        self._voices = len(voice_files)

    def _play(self, voice: int) -> None:
        self._mci(f"play gunshot{voice} from 0")

    def _unload(self) -> None:
        for v in range(self._voices):
            self._mci(f"close gunshot{v}")
        self._voices = 0


class MacPlayer(Player):
    _voices: list = []

    def _load(self, voice_files: list[Path]) -> None:
        from AppKit import NSSound  # ships with pyobjc, which pystray needs on macOS

        self._voices = [
            NSSound.alloc().initWithContentsOfFile_byReference_(str(p), False) for p in voice_files
        ]

    def _play(self, voice: int) -> None:
        sound = self._voices[voice]
        sound.stop()
        sound.play()

    def _unload(self) -> None:
        for sound in self._voices:
            sound.stop()
        self._voices = []


class AfplayPlayer(Player):
    """Fallback for macOS without AppKit: higher latency, but always present."""

    _files: list[Path] = []

    def _load(self, voice_files: list[Path]) -> None:
        self._files = voice_files

    def _play(self, voice: int) -> None:
        subprocess.Popen(["afplay", str(self._files[voice])])


def create_player(pack: sounds.Pack, volume: float) -> Player:
    if sys.platform == "win32":
        return WindowsPlayer(pack, volume)
    if sys.platform == "darwin":
        try:
            import AppKit  # noqa: F401

            return MacPlayer(pack, volume)
        except ImportError:
            return AfplayPlayer(pack, volume)
    raise RuntimeError("Gunshot supports Windows and macOS only.")
