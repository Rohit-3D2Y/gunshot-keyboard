"""Low-latency, overlapping playback using each OS's built-in audio.

No third-party audio library is needed.

* Windows: one continuous waveOut stream fed by our own mixer. Every
  keypress adds a "voice" to the mix, so any number of sounds can overlap
  and none is ever restarted or cut off - which is what fast typing needs.
* macOS: AppKit's NSSound with a pool of pre-loaded copies per clip.
"""

from __future__ import annotations

import collections
import ctypes
import queue
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

from . import sounds


class ClipPicker:
    """Decides which clip of a pack plays for each keypress."""

    # A sequential pack starts over from its first clip after this pause.
    SEQUENCE_RESET_SECONDS = 2.0

    def __init__(self, pack: sounds.Pack) -> None:
        self.pack = pack
        # Clip indexes: regular variants first, then each special key's clips.
        self.clips: list[np.ndarray] = list(pack.variants)
        self.special: dict[str, list[int]] = {}
        for key, special in pack.special.items():
            self.special[key] = list(range(len(self.clips), len(self.clips) + len(special)))
            self.clips += special
        self._last = -1
        self._last_time = 0.0

    def pick(self, key: str | None = None) -> int:
        if key in self.special:
            return random.choice(self.special[key])
        count = len(self.pack.variants)
        now = time.monotonic()
        if self.pack.sequential:
            if now - self._last_time > self.SEQUENCE_RESET_SECONDS:
                self._last = -1
            self._last = (self._last + 1) % count
        elif count > 1:
            # Random, but never the same clip twice in a row.
            self._last = random.choice([c for c in range(count) if c != self._last])
        else:
            self._last = 0
        self._last_time = now
        return self._last


class Player:
    """Public API shared by all backends; every method is safe from any thread."""

    def fire(self, key: str | None = None) -> None:
        """Play a sound; `key` ("enter", "space", ...) picks that key's own sound."""

    def set_volume(self, volume: float) -> None: ...

    def set_pack(self, pack: sounds.Pack) -> None: ...

    def close(self) -> None: ...


# --- mixer (Windows) -----------------------------------------------------------


def _soft_limit(x: np.ndarray) -> np.ndarray:
    """Transparent below 0.8; above that, ease into +-1 instead of hard clipping
    (many overlapping sounds would otherwise crackle)."""
    over = np.abs(x) > 0.8
    if over.any():
        x = x.copy()
        x[over] = np.sign(x[over]) * (0.8 + 0.2 * np.tanh((np.abs(x[over]) - 0.8) / 0.2))
    return x


class Mixer:
    """Sums every currently playing sound into one output stream."""

    MAX_VOICES = 48  # beyond this the oldest sounds are dropped

    def __init__(self, pack: sounds.Pack, volume: float) -> None:
        self._picker = ClipPicker(pack)
        self._volume = volume
        self._pending: collections.deque = collections.deque()
        self._voices: list[list] = []  # [clip, position]

    def fire(self, key: str | None = None) -> None:
        self._pending.append(key)  # deque.append is thread-safe

    def set_volume(self, volume: float) -> None:
        self._volume = volume

    def set_pack(self, pack: sounds.Pack) -> None:
        self._picker = ClipPicker(pack)  # sounds already playing finish naturally

    def discard(self) -> None:
        """Forget pending and playing sounds (used while no device is open)."""
        self._pending.clear()
        self._voices = []

    def render(self, frames: int) -> np.ndarray:
        picker = self._picker
        while self._pending:
            key = self._pending.popleft()
            self._voices.append([picker.clips[picker.pick(key)], 0])
        out = np.zeros(frames, np.float32)
        alive = []
        for voice in self._voices[-self.MAX_VOICES :]:
            clip, pos = voice
            n = min(frames, len(clip) - pos)
            out[:n] += clip[pos : pos + n]
            voice[1] = pos + n
            if voice[1] < len(clip):
                alive.append(voice)
        self._voices = alive
        return _soft_limit(out * self._volume)


class _WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", ctypes.c_ushort),
        ("nChannels", ctypes.c_ushort),
        ("nSamplesPerSec", ctypes.c_uint32),
        ("nAvgBytesPerSec", ctypes.c_uint32),
        ("nBlockAlign", ctypes.c_ushort),
        ("wBitsPerSample", ctypes.c_ushort),
        ("cbSize", ctypes.c_ushort),
    ]


class _WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", ctypes.c_uint32),
        ("dwBytesRecorded", ctypes.c_uint32),
        ("dwUser", ctypes.c_size_t),
        ("dwFlags", ctypes.c_uint32),
        ("dwLoops", ctypes.c_uint32),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_size_t),
    ]


class WaveOutPlayer(Player):
    """Streams the mixer to the default Windows output device."""

    # 6 buffers x 256 frames (~5.8 ms each): ~35 ms worst-case latency, with
    # enough queued audio that a busy moment in Python doesn't cause a gap.
    BUFFER_FRAMES = 256
    BUFFERS = 6

    _WAVE_MAPPER = 0xFFFFFFFF
    _CALLBACK_EVENT = 0x00050000
    _WHDR_DONE = 0x1

    # With no usable output device (none plugged in, Bluetooth disconnected)
    # the app keeps running silently and tries again this often.
    RETRY_SECONDS = 2.0

    def __init__(self, pack: sounds.Pack, volume: float) -> None:
        self.mixer = Mixer(pack, volume)
        self.device_open = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="gunshot-audio", daemon=True)
        self._thread.start()

    def fire(self, key: str | None = None) -> None:
        self.mixer.fire(key)

    def set_volume(self, volume: float) -> None:
        self.mixer.set_volume(volume)

    def set_pack(self, pack: sounds.Pack) -> None:
        self.mixer.set_pack(pack)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        winmm = ctypes.windll.winmm
        kernel32 = ctypes.windll.kernel32
        winmm.waveOutOpen.argtypes = [
            ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint, ctypes.POINTER(_WAVEFORMATEX),
            ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint32,
        ]
        for fn in (winmm.waveOutPrepareHeader, winmm.waveOutWrite, winmm.waveOutUnprepareHeader):
            fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(_WAVEHDR), ctypes.c_uint]
        winmm.waveOutReset.argtypes = [ctypes.c_void_p]
        winmm.waveOutClose.argtypes = [ctypes.c_void_p]
        kernel32.CreateEventW.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

        # Audio must never wait behind the rest of the app: high thread priority,
        # and 1 ms timer resolution (Windows' default ~15.6 ms wakes us too late).
        kernel32.SetThreadPriority(kernel32.GetCurrentThread(), 2)  # THREAD_PRIORITY_HIGHEST
        winmm.timeBeginPeriod(1)
        event = kernel32.CreateEventW(None, False, False, None)
        try:
            while not self._stop.is_set():
                handle = ctypes.c_void_p()
                fmt = _WAVEFORMATEX(1, 1, sounds.SAMPLE_RATE, sounds.SAMPLE_RATE * 2, 2, 16, 0)
                result = winmm.waveOutOpen(
                    ctypes.byref(handle), self._WAVE_MAPPER, ctypes.byref(fmt), event, 0,
                    self._CALLBACK_EVENT,
                )
                if result != 0:
                    # No device right now: drop keypresses instead of replaying
                    # a backlog later, and look again shortly.
                    self.mixer.discard()
                    self._stop.wait(self.RETRY_SECONDS)
                    continue
                self.device_open = True
                try:
                    self._stream(winmm, kernel32, handle, event)
                finally:
                    self.device_open = False
        finally:
            kernel32.CloseHandle(event)
            winmm.timeEndPeriod(1)

    def _stream(self, winmm, kernel32, handle, event) -> None:
        """Feed the open device until we're stopped or the device goes away."""
        hdr_size = ctypes.sizeof(_WAVEHDR)
        buffers = [(ctypes.c_int16 * self.BUFFER_FRAMES)() for _ in range(self.BUFFERS)]
        headers = []
        for buf in buffers:
            hdr = _WAVEHDR()
            hdr.lpData = ctypes.addressof(buf)
            hdr.dwBufferLength = self.BUFFER_FRAMES * 2
            winmm.waveOutPrepareHeader(handle, ctypes.byref(hdr), hdr_size)
            winmm.waveOutWrite(handle, ctypes.byref(hdr), hdr_size)  # start with silence
            headers.append(hdr)

        nxt = 0
        try:
            while not self._stop.is_set():
                kernel32.WaitForSingleObject(event, 20)
                # Refill finished buffers strictly in order to keep the stream continuous.
                while headers[nxt].dwFlags & self._WHDR_DONE:
                    try:
                        samples = self.mixer.render(self.BUFFER_FRAMES)
                    except Exception:  # a bad clip must never kill the audio stream
                        samples = np.zeros(self.BUFFER_FRAMES, np.float32)
                    pcm = np.frombuffer(buffers[nxt], dtype=np.int16)
                    pcm[:] = (samples * 32767).astype(np.int16)
                    headers[nxt].dwFlags &= ~self._WHDR_DONE
                    if winmm.waveOutWrite(handle, ctypes.byref(headers[nxt]), hdr_size) != 0:
                        return  # device was unplugged/disabled: reopen
                    nxt = (nxt + 1) % self.BUFFERS
        finally:
            winmm.waveOutReset(handle)
            for hdr in headers:
                winmm.waveOutUnprepareHeader(handle, ctypes.byref(hdr), hdr_size)
            winmm.waveOutClose(handle)


# --- macOS ---------------------------------------------------------------------


class FilePoolPlayer(Player):
    """Backends that play clips from WAV files with a pool of pre-loaded copies.

    Each clip gets VOICES_PER_CLIP copies used round-robin, so a clip only
    restarts after that many newer presses of the same clip.
    """

    VOICES_PER_CLIP = 6

    def __init__(self, pack: sounds.Pack, volume: float) -> None:
        self._dir = Path(tempfile.mkdtemp(prefix="gunshot-"))
        self._queue: queue.Queue = queue.Queue()
        self._picker = ClipPicker(pack)
        self._volume = volume
        self._voice_cursor: list[int] = []
        self._generation = 0
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()
        self._queue.put(("load", None))

    def fire(self, key: str | None = None) -> None:
        self._queue.put(("fire", key))

    def set_volume(self, volume: float) -> None:
        self._volume = volume
        self._queue.put(("load", None))

    def set_pack(self, pack: sounds.Pack) -> None:
        self._picker = ClipPicker(pack)
        self._queue.put(("load", None))

    def close(self) -> None:
        self._queue.put(("stop", None))
        self._worker.join(timeout=2)

    def _run(self) -> None:
        while True:
            cmd, arg = self._queue.get()
            try:
                if cmd == "fire":
                    clip = self._picker.pick(arg)
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

    def _reload(self) -> None:
        self._unload()
        # Fresh file names each time: the OS may still hold the old ones open.
        self._generation += 1
        voice_files = []
        for i, clip in enumerate(self._picker.clips):
            path = self._dir / f"clip{self._generation}_{i}.wav"
            path.write_bytes(sounds.to_wav_bytes(clip, self._volume))
            voice_files += [path] * self.VOICES_PER_CLIP
        self._voice_cursor = [0] * len(self._picker.clips)
        self._load(voice_files)

    # Subclasses implement these; they always run on the worker thread.
    def _load(self, voice_files: list[Path]) -> None: ...
    def _play(self, voice: int) -> None: ...
    def _unload(self) -> None: ...


class MacPlayer(FilePoolPlayer):
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


class AfplayPlayer(FilePoolPlayer):
    """Fallback for macOS without AppKit: higher latency, but always present."""

    _files: list[Path] = []

    def _load(self, voice_files: list[Path]) -> None:
        self._files = voice_files

    def _play(self, voice: int) -> None:
        subprocess.Popen(["afplay", str(self._files[voice])])


def create_player(pack: sounds.Pack, volume: float) -> Player:
    if sys.platform == "win32":
        return WaveOutPlayer(pack, volume)
    if sys.platform == "darwin":
        try:
            import AppKit  # noqa: F401

            return MacPlayer(pack, volume)
        except ImportError:
            return AfplayPlayer(pack, volume)
    raise RuntimeError("Gunshot supports Windows and macOS only.")
