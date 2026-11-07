import numpy as np

from gunshot import audio, sounds
from gunshot.audio import ClipPicker, Mixer


def _clips(n, length=10):
    return [np.zeros(length, np.float32) for _ in range(n)]


def test_sequence_plays_in_order_and_wraps():
    picker = ClipPicker(sounds.Pack(_clips(7), sequential=True))
    assert [picker.pick() for _ in range(9)] == [0, 1, 2, 3, 4, 5, 6, 0, 1]


def test_random_never_repeats_back_to_back():
    picker = ClipPicker(sounds.Pack(_clips(4)))
    clips = [picker.pick() for _ in range(200)]
    assert all(a != b for a, b in zip(clips, clips[1:]))
    assert set(clips) == {0, 1, 2, 3}


def test_sequence_restarts_after_pause(monkeypatch):
    clock = iter([0.0, 0.1, 0.2, 5.0, 5.1])
    monkeypatch.setattr(audio.time, "monotonic", lambda: next(clock))
    picker = ClipPicker(sounds.Pack(_clips(7), sequential=True))
    assert [picker.pick() for _ in range(5)] == [0, 1, 2, 0, 1]


def test_special_key_uses_its_own_clip():
    picker = ClipPicker(sounds.Pack(_clips(3), special={"enter": _clips(1)}))
    assert picker.pick("enter") == 3  # first clip after the 3 regular ones
    assert picker.pick("a-key-with-no-special-sound") in (0, 1, 2)


def test_fast_typing_overlaps_instead_of_cutting_off():
    """100 WPM is ~8 keys/s: a new press must never stop an earlier sound."""
    rate = sounds.SAMPLE_RATE
    long_clip = np.full(int(rate * 0.45), 0.1, np.float32)  # gunshot-length
    mixer = Mixer(sounds.Pack([long_clip]), volume=1.0)
    block = 256
    keystroke_every = int(rate / 8 / block)  # blocks between presses
    levels = []
    for b in range(int(rate * 0.5 / block)):
        if b % keystroke_every == 0 and b < keystroke_every * 3:
            mixer.fire()
        levels.append(mixer.render(block).mean())
    # Three overlapping shots: the level steps up 0.1 -> 0.2 -> 0.3 instead of
    # resetting, and the first shot plays its full length.
    assert np.isclose(levels[0], 0.1, atol=1e-3)
    assert np.isclose(levels[keystroke_every], 0.2, atol=1e-3)
    assert np.isclose(levels[keystroke_every * 2], 0.3, atol=1e-3)
    first_end = int(rate * 0.45 / block)
    assert levels[first_end - 1] > 0.25


def test_mixer_volume_limit_and_finish():
    clip = np.full(1000, 0.6, np.float32)
    mixer = Mixer(sounds.Pack([clip]), volume=0.5)
    mixer.fire()
    assert np.isclose(mixer.render(100).max(), 0.3)
    mixer.set_volume(1.0)
    for _ in range(5):
        mixer.fire()
    loud = mixer.render(100)
    assert loud.max() <= 1.0  # five stacked sounds are soft-limited, not clipped
    for _ in range(20):
        mixer.render(100)
    assert not mixer.render(100).any()  # everything finished -> silence


def test_pack_switch_keeps_playing_sounds():
    a = np.full(1000, 0.2, np.float32)
    b = np.full(1000, 0.4, np.float32)
    mixer = Mixer(sounds.Pack([a]), volume=1.0)
    mixer.fire()
    mixer.render(100)
    mixer.set_pack(sounds.Pack([b]))
    mixer.fire()
    assert np.isclose(mixer.render(100).mean(), 0.6)


def test_discard_drops_backlog():
    mixer = Mixer(sounds.Pack([np.full(1000, 0.5, np.float32)]), volume=1.0)
    mixer.fire()
    mixer.render(10)
    mixer.fire()
    mixer.discard()
    assert not mixer.render(100).any()


def test_no_audio_device_keeps_app_alive(monkeypatch):
    """With no output device the player must not raise; it keeps retrying."""
    import sys
    import time

    if sys.platform != "win32":
        return
    import ctypes

    from gunshot.audio import WaveOutPlayer

    real = ctypes.windll.winmm
    attempts = []

    class NoDevice:
        """winmm with every output device missing."""

        def __getattr__(self, name):
            return getattr(real, name)

    class FailingOpen:
        argtypes = None

        def __call__(self, *args):
            attempts.append(1)
            return 2  # MMSYSERR_BADDEVICEID

    fake = NoDevice()
    fake.waveOutOpen = FailingOpen()
    monkeypatch.setattr(ctypes.windll, "winmm", fake)
    monkeypatch.setattr(WaveOutPlayer, "RETRY_SECONDS", 0.05)
    player = WaveOutPlayer(sounds.Pack(_clips(2)), 0.5)
    player.fire()
    time.sleep(0.3)
    assert player._thread.is_alive()  # still running, not crashed
    assert player.device_open is False
    assert len(attempts) >= 3  # and it keeps looking for a device
    player.close()
    assert not player._thread.is_alive()
