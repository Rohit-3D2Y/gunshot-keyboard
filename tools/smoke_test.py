"""Smoke test for CI: exercise the real OS integrations without a human.

Runs on GitHub's Windows and macOS machines after the build:
  1. every sound pack loads and plays through the real audio backend;
  2. the global keyboard listener starts and stops without crashing
     (on CI macOS it has no Input Monitoring permission, which is fine:
     we're checking it doesn't take the process down);
  3. settings and start-at-login paths resolve.
Exit code 0 = pass.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gunshot import sounds, system  # noqa: E402
from gunshot.app import make_listener  # noqa: E402
from gunshot.audio import create_player  # noqa: E402

player = create_player(sounds.load_pack(sounds.DEFAULT_PACK), 0.2)
time.sleep(0.5)
device = getattr(player, "device_open", "n/a")
# CI machines may have no sound card: the app must keep running silently.
print(f"audio backend: {type(player).__name__} (output device open: {device})")
for name in sounds.available_packs():
    player.set_pack(sounds.load_pack(name))
    for key in (None, None, "enter"):
        player.fire(key)
        time.sleep(0.05)
    print(f"  played {name}")
time.sleep(0.5)
player.close()

presses = []
listener = make_listener(on_press=presses.append, on_release=lambda k: None)
listener.start()
listener.wait()
time.sleep(2)
print(f"keyboard listener ran (trusted={getattr(listener, 'IS_TRUSTED', 'n/a')})")
listener.stop()
listener.join(timeout=5)

print(f"config dir: {system.config_dir()}")
print(f"autostart enabled: {system.autostart_enabled()}")
print("SMOKE TEST PASSED")
