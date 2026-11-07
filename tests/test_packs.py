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
    pack = sounds.load_pack("Shotgun", tmp_path)
    assert not pack.sequential
    variants = pack.variants
    assert len(variants) == 3
    # 22.05 kHz stereo is resampled to 44.1 kHz mono and normalised.
    assert len(variants[0]) == 2000
    assert np.isclose(np.max(np.abs(variants[0])), 1.0)


def test_broken_files_are_skipped(tmp_path):
    pack = tmp_path / "Mixed"
    pack.mkdir()
    (pack / "broken.wav").write_bytes(b"not a wav")
    _write_wav(pack / "good.wav", np.linspace(0, 1, 500), rate=sounds.SAMPLE_RATE, channels=1)
    assert len(sounds.load_pack("Mixed", tmp_path).variants) == 1


def test_unknown_pack_falls_back_to_default(tmp_path):
    pack = sounds.load_pack("Does Not Exist", tmp_path)
    assert len(pack.variants) == len(sounds.build_variants())


def test_bundled_packs_folder_exists():
    assert sounds.packs_dir().is_dir()


def test_sequence_pack_and_silence_trim(tmp_path):
    pack = tmp_path / "Phrase"
    pack.mkdir()
    (pack / "pack.json").write_text('{"order": "sequence"}')
    silence = np.zeros(sounds.SAMPLE_RATE // 2)
    tone = np.sin(np.linspace(0, 200, sounds.SAMPLE_RATE // 10)) * 0.5
    clip = np.concatenate([silence, tone, silence])
    _write_wav(pack / "01.wav", clip, rate=sounds.SAMPLE_RATE, channels=1)
    loaded = sounds.load_pack("Phrase", tmp_path)
    assert loaded.sequential
    # Half a second of silence each side is trimmed down to a few ms.
    assert len(loaded.variants[0]) < len(tone) + sounds.SAMPLE_RATE * 0.06


def test_bundled_yamete_pack_is_in_order():
    pack = sounds.load_pack("Yamete Kudasai")
    assert pack.sequential and len(pack.variants) == 7


def test_typewriter_rings_on_enter():
    pack = sounds.load_pack("Typewriter")
    assert len(pack.variants) >= 8
    assert len(pack.special["enter"]) == 1


def test_special_key_files(tmp_path):
    pack = tmp_path / "Keys"
    pack.mkdir()
    for name in ["key01", "key02", "enter", "space01", "backspace"]:
        _write_wav(pack / f"{name}.wav", np.linspace(0, 1, 500), rate=sounds.SAMPLE_RATE, channels=1)
    loaded = sounds.load_pack("Keys", tmp_path)
    assert len(loaded.variants) == 2
    assert sorted(loaded.special) == ["backspace", "enter", "space"]


def test_24_bit_wav(tmp_path):
    ramp = np.linspace(-0.5, 0.5, 300)
    ints = (ramp * 8388607).astype(np.int32)
    raw = np.stack([ints & 0xFF, (ints >> 8) & 0xFF, (ints >> 16) & 0xFF], axis=1).astype(np.uint8)
    path = tmp_path / "deep.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(3)
        wav.setframerate(sounds.SAMPLE_RATE)
        wav.writeframes(raw.tobytes())
    data = sounds.read_wav(path)
    # Normalised to peak 1 with the sign preserved.
    assert np.isclose(data.min(), -1.0, atol=1e-3) and np.isclose(data.max(), 1.0, atol=1e-3)
    assert data[0] < 0 < data[-1]


def test_every_bundled_pack_loads():
    for name in sounds.available_packs():
        pack = sounds.load_pack(name)
        assert pack.variants, name
        assert all(len(v) < sounds.SAMPLE_RATE * 1.6 for v in pack.variants), name
