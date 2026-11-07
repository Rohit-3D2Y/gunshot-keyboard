"""OS integration: config location, start-at-login, single instance, permissions."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

APP_NAME = "Gunshot"
BUNDLE_ID = "com.gunshot.keyboard"
WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def config_dir() -> Path:
    if sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        path = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def launch_args() -> list[str]:
    """Command Windows/macOS should run at login to start Gunshot."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return [str(pythonw if pythonw.exists() else exe), "-m", "gunshot"]


# --- start at login ----------------------------------------------------------


def _mac_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{BUNDLE_ID}.plist"


def autostart_enabled() -> bool:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY) as key:
                winreg.QueryValueEx(key, APP_NAME)
                return True
        except FileNotFoundError:
            return False
    if sys.platform == "darwin":
        return _mac_agent_path().exists()
    return False


def set_autostart(enabled: bool) -> None:
    if sys.platform == "win32":
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                command = " ".join(f'"{a}"' if " " in a else a for a in launch_args())
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
    elif sys.platform == "darwin":
        agent = _mac_agent_path()
        if enabled:
            agent.parent.mkdir(parents=True, exist_ok=True)
            agent.write_bytes(
                plistlib.dumps(
                    {"Label": BUNDLE_ID, "ProgramArguments": launch_args(), "RunAtLoad": True}
                )
            )
        else:
            agent.unlink(missing_ok=True)


# --- single instance ---------------------------------------------------------

_instance_handle = None  # kept alive for the life of the process


def already_running() -> bool:
    """True if another copy of Gunshot is running (so shots aren't doubled)."""
    global _instance_handle
    if sys.platform == "win32":
        import ctypes

        _instance_handle = ctypes.windll.kernel32.CreateMutexW(None, False, "GunshotKeyboardApp")
        return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    import fcntl

    _instance_handle = open(config_dir() / "gunshot.lock", "w")
    try:
        fcntl.flock(_instance_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False
    except OSError:
        return True


# --- macOS keyboard permission ----------------------------------------------


def needs_input_permission(listener) -> bool:
    """macOS only delivers keystrokes once the user allows Input Monitoring."""
    return sys.platform == "darwin" and not getattr(listener, "IS_TRUSTED", True)


def open_input_permission_settings() -> None:
    if sys.platform == "darwin":
        subprocess.Popen(
            ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"]
        )
