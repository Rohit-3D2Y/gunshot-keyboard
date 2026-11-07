"""Persistent user settings."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .sounds import DEFAULT_PACK
from .system import config_dir


@dataclass
class Settings:
    enabled: bool = True
    volume: float = 0.6
    pack: str = DEFAULT_PACK

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads((config_dir() / "settings.json").read_text())
            return cls(
                enabled=bool(data.get("enabled", True)),
                volume=min(1.0, max(0.0, float(data.get("volume", 0.6)))),
                pack=str(data.get("pack", DEFAULT_PACK)),
            )
        except (OSError, ValueError, TypeError, AttributeError):
            return cls()

    def save(self) -> None:
        (config_dir() / "settings.json").write_text(json.dumps(asdict(self), indent=2))
