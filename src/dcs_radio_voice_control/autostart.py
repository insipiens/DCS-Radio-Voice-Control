"""Per-user Windows sign-in registration for the lightweight controller."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any

from .stt import PROJECT_ROOT


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "DCS Radio Voice Control"


def expected_command(root: Path = PROJECT_ROOT) -> str:
    return subprocess.list2cmdline(
        [str(root / "runtime" / "pythonw.exe"), "-m", "dcs_radio_voice_control.launcher", "--automatic"]
    )


def registration_status(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    expected = expected_command(root)
    if os.name != "nt":
        return {"registered": False, "current": False, "command": None, "expected": expected}
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            command, _ = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        command = None
    return {
        "registered": command is not None,
        "current": command == expected,
        "command": command,
        "expected": expected,
    }


def set_enabled(enabled: bool, root: Path = PROJECT_ROOT) -> dict[str, Any]:
    if not isinstance(enabled, bool):
        raise ValueError("Start when DCS starts must be enabled or disabled.")
    if os.name != "nt":
        raise OSError("Start when DCS starts is available only on Windows.")
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, expected_command(root))
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
    return registration_status(root)
