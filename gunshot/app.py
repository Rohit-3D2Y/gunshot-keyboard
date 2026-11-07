"""Gunshot: every keypress fires a gunshot.

Runs as a system-tray (Windows) / menu-bar (macOS) app. A global keyboard
listener plays a sound on each key-down. Keys are never logged, stored or
sent anywhere - the listener only uses them to tell a fresh press from an
auto-repeat. The app makes no network connections.
"""

from __future__ import annotations

import threading

import pystray
from pynput import keyboard

from . import sounds
from .audio import create_player
from .icon import GREY, RED, crosshair
from .settings import Settings
from .system import (
    APP_NAME,
    already_running,
    autostart_enabled,
    needs_input_permission,
    open_input_permission_settings,
    open_text_file,
    set_autostart,
)

TOGGLE_HOTKEY = "<ctrl>+<alt>+g"
VOLUME_LEVELS = {"Quiet": 0.1, "Low": 0.3, "Medium": 0.6, "High": 0.85, "Max": 1.0}


class GunshotApp:
    def __init__(self) -> None:
        self.settings = Settings.load()
        self.packs = sounds.available_packs()
        if self.settings.pack not in self.packs:
            self.settings.pack = sounds.DEFAULT_PACK
        self.player = create_player(sounds.load_pack(self.settings.pack), self.settings.volume)
        self._held: set = set()
        self._lock = threading.Lock()
        self._hotkey = keyboard.HotKey(keyboard.HotKey.parse(TOGGLE_HOTKEY), self.toggle)
        self.listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self.icon = pystray.Icon(APP_NAME, self._make_icon(), self._tooltip(), self._make_menu())

    # --- keyboard -----------------------------------------------------------

    def _on_press(self, key) -> None:
        self._hotkey.press(self.listener.canonical(key))
        with self._lock:
            if key in self._held:  # auto-repeat from holding a key down
                return
            self._held.add(key)
        if self.settings.enabled:
            self.player.fire()

    def _on_release(self, key) -> None:
        self._hotkey.release(self.listener.canonical(key))
        with self._lock:
            self._held.discard(key)

    # --- actions ------------------------------------------------------------

    def toggle(self, *_args) -> None:
        self.settings.enabled = not self.settings.enabled
        self.settings.save()
        self._refresh()

    def _set_volume(self, level: float):
        def handler(*_args) -> None:
            self.settings.volume = level
            self.settings.save()
            self.player.set_volume(level)
            self.player.fire()  # preview the new volume

        return handler

    def _set_pack(self, name: str):
        def handler(*_args) -> None:
            self.settings.pack = name
            self.settings.save()
            self.player.set_pack(sounds.load_pack(name))
            self.player.fire()  # preview the new sound

        return handler

    def _toggle_autostart(self, *_args) -> None:
        set_autostart(not autostart_enabled())

    def _quit(self, *_args) -> None:
        self.listener.stop()
        self.player.close()
        self.icon.stop()

    # --- tray ---------------------------------------------------------------

    def _tooltip(self) -> str:
        state = "armed" if self.settings.enabled else "safety on"
        return f"{APP_NAME} - {state} (Ctrl+Alt+G to toggle)"

    def _make_icon(self):
        return crosshair(64, RED if self.settings.enabled else GREY)

    def _make_menu(self) -> pystray.Menu:
        volume_items = [
            pystray.MenuItem(
                name,
                self._set_volume(level),
                checked=lambda _item, lv=level: abs(self.settings.volume - lv) < 1e-6,
                radio=True,
            )
            for name, level in VOLUME_LEVELS.items()
        ]
        pack_items = [
            pystray.MenuItem(
                name,
                self._set_pack(name),
                checked=lambda _item, n=name: self.settings.pack == n,
                radio=True,
            )
            for name in self.packs
        ]
        return pystray.Menu(
            pystray.MenuItem(
                "Enabled (Ctrl+Alt+G)",
                self.toggle,
                checked=lambda _item: self.settings.enabled,
                default=True,
            ),
            pystray.MenuItem("Sound", pystray.Menu(*pack_items)),
            pystray.MenuItem("Volume", pystray.Menu(*volume_items)),
            pystray.MenuItem(
                "Start at login",
                self._toggle_autostart,
                checked=lambda _item: autostart_enabled(),
            ),
            pystray.MenuItem(
                "Allow keyboard access...",
                lambda *_: open_input_permission_settings(),
                visible=lambda _item: needs_input_permission(self.listener),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Sound credits",
                lambda *_: open_text_file(sounds.packs_dir() / "CREDITS.md"),
            ),
            pystray.MenuItem("Quit", self._quit),
        )

    def _refresh(self) -> None:
        self.icon.icon = self._make_icon()
        self.icon.title = self._tooltip()
        self.icon.update_menu()

    def _on_tray_ready(self, icon: pystray.Icon) -> None:
        icon.visible = True
        if needs_input_permission(self.listener):
            open_input_permission_settings()
            try:
                icon.notify(
                    "Allow Gunshot under Input Monitoring, then quit and reopen it.",
                    "Gunshot needs keyboard access",
                )
            except NotImplementedError:
                pass

    def run(self) -> None:
        self.listener.start()
        self.listener.wait()  # so IS_TRUSTED is known before the tray appears
        self.icon.run(setup=self._on_tray_ready)


def main() -> None:
    if already_running():
        return
    GunshotApp().run()
