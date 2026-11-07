import numpy as np

from gunshot import sounds
from gunshot.audio import Player


class FakePlayer(Player):
    """Records which voice would play instead of touching the OS."""

    def _load(self, voice_files):
        self.played = []

    def _play(self, voice):
        self.played.append(voice)


def _clips(n):
    return [np.zeros(10, np.float32) for _ in range(n)]


def _fire(player, times):
    for _ in range(times):
        player.fire()
    player.close()
    return [v // Player.VOICES_PER_CLIP for v in player.played]


def test_sequence_plays_in_order_and_wraps():
    p = FakePlayer(sounds.Pack(_clips(7), sequential=True), 1.0)
    assert _fire(p, 9) == [0, 1, 2, 3, 4, 5, 6, 0, 1]


def test_random_never_repeats_back_to_back():
    p = FakePlayer(sounds.Pack(_clips(4)), 1.0)
    clips = _fire(p, 200)
    assert all(a != b for a, b in zip(clips, clips[1:]))
    assert set(clips) == {0, 1, 2, 3}


def test_sequence_restarts_after_pause(monkeypatch):
    import gunshot.audio as audio

    clock = iter([0.0, 0.1, 0.2, 5.0, 5.1])
    monkeypatch.setattr(audio.time, "monotonic", lambda: next(clock))
    p = FakePlayer(sounds.Pack(_clips(7), sequential=True), 1.0)
    assert _fire(p, 5) == [0, 1, 2, 0, 1]
