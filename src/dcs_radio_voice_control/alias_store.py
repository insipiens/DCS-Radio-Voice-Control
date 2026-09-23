"""Editable speech aliases and unresolved recognition candidates."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re


DEFAULT_ALIASES: dict[str, str] = {
    "2": "Wingman",
    "two": "Wingman",
    "number two": "Wingman",
    "3": "Second Element",
    "three": "Second Element",
    "element": "Second Element",
    "join up": "Rejoin Formation",
    "rejoin": "Rejoin Formation",
    "abreast": "Go Line Abreast",
    "line abreast": "Go Line Abreast",
    "trail": "Go Trail",
    "echelon trail": "Go Trail",
}


def _state_directory() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / ".dcs_radio_voice_control"
    return base / "DCSRadioVoiceControl"


def aliases_path() -> Path:
    return _state_directory() / "aliases.json"


def pending_alias_path() -> Path:
    """Compatibility name for callers; action aliases now live in aliases.json."""
    return aliases_path()


def _legacy_pending_alias_path() -> Path:
    return _state_directory() / "pending_aliases.json"


def pending_meta_alias_path() -> Path:
    return _state_directory() / "pending_meta_aliases.json"


def _key(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold())).strip()


def _read_alias_document(path: Path) -> dict[str, str | None]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {
        _key(str(name)): value.strip() if isinstance(value, str) else None
        for name, value in loaded.items()
        if _key(str(name)) and (value is None or isinstance(value, str))
    }


def _write_alias_document(path: Path, data: dict[str, str | None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def ensure_alias_file(path: Path | None = None) -> Path:
    """Create the one editable action-alias file without overwriting user changes.

    On first use, an existing pending_aliases.json is migrated into aliases.json.
    The small shipped defaults fill only keys absent from that legacy file. Once
    aliases.json exists, releases never rewrite or merge it automatically.
    """
    target = path or aliases_path()
    if target.exists():
        return target
    data: dict[str, str | None] = dict(DEFAULT_ALIASES)
    if path is None:
        legacy = _legacy_pending_alias_path()
        if legacy.exists():
            data.update(_read_alias_document(legacy))
    _write_alias_document(target, data)
    return target


def reviewed_aliases(path: Path | None = None) -> dict[str, str]:
    """Return all non-null mappings from the editable action-alias file."""
    target = path or ensure_alias_file()
    return {
        name: value
        for name, value in _read_alias_document(target).items()
        if isinstance(value, str) and value
    }


def reviewed_alias(transcript: str, path: Path | None = None) -> str | None:
    """Return an exact, human-reviewed alias mapping; ignore null candidates."""
    return reviewed_aliases(path).get(_key(transcript))


def reviewed_meta_alias(transcript: str, path: Path | None = None) -> str | None:
    """Return a reviewed alias for an application-side spoken command."""
    target = path or pending_meta_alias_path()
    return reviewed_alias(transcript, target)


def record_pending_alias(transcript: str, path: Path | None = None) -> bool:
    """Add a phrase with a null mapping; never overwrite a reviewed mapping."""
    key = _key(transcript)
    if not key:
        return False
    target = path or ensure_alias_file()
    data = _read_alias_document(target)
    if key in data:
        return False
    data[key] = None
    try:
        _write_alias_document(target, data)
    except OSError:
        return False
    return True


def record_pending_meta_alias(transcript: str, path: Path | None = None) -> bool:
    """Record an unresolved application command separately from DCS action aliases."""
    return record_pending_alias(transcript, path or pending_meta_alias_path())
