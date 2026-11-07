import wave

import numpy as np

from gunshot import sounds


def _write_wav(path, samples, rate=22050, channels=2):
    pcm = (np.repeat(samples[:, None], channels, axis=1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())


def test_wav_folder_becomes_a_pack(tmp_path):
    pack = tmp_path / "Shotgun"
    pack.mkdir()
    for i in range(3):
        _write_wav(pack / f"take{i}.wav", np.linspace(0, 0.5, 1000))
    (tmp_path / "Empty").mkdir()

    assert sounds.available_packs(tmp_path) == ["Gunshot", "Shotgun"]
    variants = sounds.load_pack("Shotgun", tmp_path)
    assert len(variants) == 3
    # 22.05 kHz stereo is resampled to 44.1 kHz mono and normalised.
    assert len(variants[0]) == 2000
    assert np.isclose(np.max(np.abs(variants[0])), 1.0)


def test_broken_files_are_skipped(tmp_path):
    pack = tmp_path / "Mixed"
    pack.mkdir()
    (pack / "broken.wav").write_bytes(b"not a wav")
    _write_wav(pack / "good.wav", np.linspace(0, 1, 500), rate=sounds.SAMPLE_RATE, channels=1)
    assert len(sounds.load_pack("Mixed", tmp_path)) == 1


def test_unknown_pack_falls_back_to_default(tmp_path):
    variants = sounds.load_pack("Does Not Exist", tmp_path)
    assert len(variants) == len(sounds.build_variants())


def test_bundled_packs_folder_exists():
    assert sounds.packs_dir().is_dir()
