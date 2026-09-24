"""Atomic storage for DRVC installation locations.

This record is DRVC-managed state, not user configuration.  It lets later
launch, status, repair, and uninstall operations return to the exact DCS
installation selected during setup instead of rediscovering it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any


SCHEMA = 1
FILENAME = "installation.json"


def installation_state_path() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        raise OSError("Windows LOCALAPPDATA is not available.")
    return Path(root) / "DCSRadioVoiceControl" / FILENAME


def load_installation_state(path: Path | None = None) -> dict[str, Any]:
    target = path or installation_state_path()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OSError(f"Cannot read DCS Radio Voice Control installation state {target}: {exc}") from exc

    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise OSError(f"DCS Radio Voice Control installation state is invalid: {target}")

    for name in ("program_root", "dcs_install", "saved_games"):
        item = value.get(name)
        if not isinstance(item, str) or not item or not Path(item).is_absolute():
            raise OSError(
                f"DCS Radio Voice Control installation state field {name!r} is invalid: {target}"
            )
    return value


def save_installation_state(
    program_root: Path,
    dcs_install: Path,
    saved_games: Path,
    path: Path | None = None,
) -> Path:
    target = path or installation_state_path()
    value = {
        "schema": SCHEMA,
        "program_root": str(program_root.resolve()),
        "dcs_install": str(dcs_install.resolve()),
        "saved_games": str(saved_games.resolve()),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=target.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, target)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return target
