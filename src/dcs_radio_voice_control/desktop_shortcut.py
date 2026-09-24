"""Optional per-user Desktop shortcut for starting DCS Radio Voice Control."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any

from .stt import PROJECT_ROOT


SHORTCUT_NAME = "DCS Radio Voice Control.lnk"
USER_SHELL_FOLDERS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"


def desktop_directory() -> Path:
    if os.name != "nt":
        raise OSError("Desktop shortcuts are available only on Windows.")
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, USER_SHELL_FOLDERS) as key:
            value, _ = winreg.QueryValueEx(key, "Desktop")
    except (FileNotFoundError, OSError) as exc:
        raise OSError("Windows Desktop folder could not be located.") from exc
    return Path(os.path.expandvars(str(value)))


def shortcut_path() -> Path:
    return desktop_directory() / SHORTCUT_NAME


def shortcut_status(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    if os.name != "nt":
        return {"exists": False, "path": None}
    path = shortcut_path()
    return {"exists": path.is_file(), "path": str(path)}


def set_enabled(enabled: bool, root: Path = PROJECT_ROOT) -> dict[str, Any]:
    if not isinstance(enabled, bool):
        raise ValueError("Desktop shortcut must be enabled or disabled.")
    if os.name != "nt":
        raise OSError("Desktop shortcuts are available only on Windows.")

    path = shortcut_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return shortcut_status(root)

    target = (root / "runtime" / "pythonw.exe").resolve()
    if not target.is_file():
        raise OSError(f"DCS Radio Voice Control launcher was not found: {target}")
    path.parent.mkdir(parents=True, exist_ok=True)

    def ps(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    script = (
        "$shell=New-Object -ComObject WScript.Shell;"
        f"$shortcut=$shell.CreateShortcut({ps(str(path))});"
        f"$shortcut.TargetPath={ps(str(target))};"
        f"$shortcut.Arguments={ps("-m dcs_radio_voice_control.launcher --tray")};"
        f"$shortcut.WorkingDirectory={ps(str(root.resolve()))};"
        "$shortcut.Description='Start DCS Radio Voice Control';"
        "$shortcut.Save()"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not path.is_file():
        detail = result.stderr.strip() or result.stdout.strip() or "Windows did not create the shortcut."
        raise OSError(f"Could not create Desktop shortcut: {detail}")
    return shortcut_status(root)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    try:
        set_enabled(not args.remove)
    except (OSError, ValueError) as exc:
        print(f"DCS Radio Voice Control: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
