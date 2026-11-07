import numpy as np

from gunshot import sounds


def test_shot_is_normalised_mono_float():
    shot = sounds.synth_gunshot(seed=1)
    assert shot.dtype == np.float32
    assert shot.ndim == 1
    assert np.isclose(np.max(np.abs(shot)), 1.0)


def test_shot_hits_fast_and_fades_out():
    shot = sounds.synth_gunshot(seed=2)
    rate = sounds.SAMPLE_RATE
    peak_at = np.argmax(np.abs(shot))
    assert peak_at < rate * 0.02  # loudest point within 20 ms of the keypress
    tail = np.abs(shot[-int(rate * 0.02):]).max()
    assert tail < 0.2


def test_variants_differ():
    a, b = sounds.build_variants(2)
    assert not np.allclose(a, b)


def test_wav_encoding():
    import io
    import wave

    shot = sounds.synth_gunshot()
    with wave.open(io.BytesIO(sounds.to_wav_bytes(shot, volume=0.5))) as wav:
        assert wav.getframerate() == sounds.SAMPLE_RATE
        assert wav.getsampwidth() == 2
        assert wav.getnframes() == len(shot)
