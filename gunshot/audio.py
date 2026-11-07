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
import tempfile
import threading
from pathlib import Path

import numpy as np

from . import sounds


class Player:
    VOICES = 12

    def __init__(self, variants: list[np.ndarray], volume: float) -> None:
        self._dir = Path(tempfile.mkdtemp(prefix="gunshot-"))
        self._queue: queue.Queue = queue.Queue()
        self._variants = variants
        self._volume = volume
        self._next = 0
        self._generation = 0
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()
        self._queue.put(("load", None))

    # --- public API (any thread) --------------------------------------------

    def fire(self) -> None:
        self._queue.put(("fire", None))

    def set_volume(self, volume: float) -> None:
        self._volume = volume
        self._queue.put(("load", None))

    def set_variants(self, variants: list[np.ndarray]) -> None:
        self._variants = variants
        self._queue.put(("load", None))

    def close(self) -> None:
        self._queue.put(("stop", None))
        self._worker.join(timeout=2)

    # --- worker thread -------------------------------------------------------

    def _run(self) -> None:
        while True:
            cmd, _ = self._queue.get()
            try:
                if cmd == "fire":
                    self._play(self._next)
                    self._next = (self._next + 1) % self.VOICES
                elif cmd == "load":
                    self._reload()
                elif cmd == "stop":
                    self._unload()
                    shutil.rmtree(self._dir, ignore_errors=True)
                    return
            except Exception:  # never let one bad sound kill the audio thread
                pass

    def _reload(self) -> None:
        self._unload()
        # Fresh file names each time: the OS may still hold the old ones open.
        self._generation += 1
        files = []
        for i, variant in enumerate(self._variants):
            path = self._dir / f"shot{self._generation}_{i}.wav"
            path.write_bytes(sounds.to_wav_bytes(variant, self._volume))
            files.append(path)
        self._load([files[v % len(files)] for v in range(self.VOICES)])

    # Subclasses implement these; they always run on the worker thread.
    def _load(self, voice_files: list[Path]) -> None: ...
    def _play(self, voice: int) -> None: ...
    def _unload(self) -> None: ...


class WindowsPlayer(Player):
    _loaded = False

    @staticmethod
    def _mci(command: str) -> None:
        ctypes.windll.winmm.mciSendStringW(command, None, 0, None)

    def _load(self, voice_files: list[Path]) -> None:
        for v, path in enumerate(voice_files):
            self._mci(f'open "{path}" type waveaudio alias gunshot{v}')
        self._loaded = True

    def _play(self, voice: int) -> None:
        self._mci(f"play gunshot{voice} from 0")

    def _unload(self) -> None:
        if self._loaded:
            for v in range(self.VOICES):
                self._mci(f"close gunshot{v}")
            self._loaded = False


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


def create_player(variants: list[np.ndarray], volume: float) -> Player:
    if sys.platform == "win32":
        return WindowsPlayer(variants, volume)
    if sys.platform == "darwin":
        try:
            import AppKit  # noqa: F401

            return MacPlayer(variants, volume)
        except ImportError:
            return AfplayPlayer(variants, volume)
    raise RuntimeError("Gunshot supports Windows and macOS only.")
