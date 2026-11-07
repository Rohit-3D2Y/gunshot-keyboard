import json

from gunshot import settings, system


def test_round_trip_and_bad_values(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "config_dir", lambda: tmp_path)
    s = settings.Settings(enabled=False, volume=0.25, pack="Shotgun")
    s.save()
    assert settings.Settings.load() == s

    (tmp_path / "settings.json").write_text(json.dumps({"volume": 9, "enabled": True}))
    assert settings.Settings.load().volume == 1.0

    (tmp_path / "settings.json").write_text("{corrupt")
    assert settings.Settings.load() == settings.Settings()


def test_launch_args_from_source():
    args = system.launch_args()
    assert args[-2:] == ["-m", "gunshot"]
