"""Validated, atomic storage for user-facing DCS Radio Voice Control settings."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping


SCHEMA = 7
DEFAULT_MINIMUM_SCORE = 0.70
DEFAULT_MINIMUM_LEAD = 0.10
MINIMUM_SCORE_RANGE = (0.60, 0.95)
MINIMUM_LEAD_RANGE = (0.02, 0.30)
CUE_VOLUME_RANGE = (0.05, 1.00)


def config_path() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        raise OSError("Windows LOCALAPPDATA is not available.")
    return Path(root) / "DCSRadioVoiceControl" / "config.json"


def default_document() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "setup_complete": False,
        "matching": {
            "minimum_score": DEFAULT_MINIMUM_SCORE,
            "minimum_lead": DEFAULT_MINIMUM_LEAD,
        },
        "stt": {"model": "ggml-base.en.bin", "use_gpu": False},
        "audio": {"output_device": None},
        "ptt": {"mode": "keyboard"},
        "feedback": {"audio_cues": True, "cue_volume": 0.25},
        "startup": {"start_with_windows": False},
    }


def load_document(path: Path | None = None) -> dict[str, Any]:
    target = path or config_path()
    document = default_document()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return document
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OSError(f"Cannot read DCS Radio Voice Control configuration {target}: {exc}") from exc
    if not isinstance(raw, dict):
        raise OSError(f"DCS Radio Voice Control configuration is not a JSON object: {target}")
    document.update(raw)
    document["schema"] = SCHEMA
    # Configurations written before schema 7 predate the explicit first-run
    # marker and therefore represent completed existing installations.
    document["setup_complete"] = _validated_setup_complete(
        raw.get("setup_complete", True)
    )
    document["matching"] = _validated_matching(raw.get("matching"))
    document["stt"] = _validated_stt(raw.get("stt"))
    document["ptt"] = _validated_ptt(raw.get("ptt"))
    document["feedback"] = _validated_feedback(raw.get("feedback"))
    document["audio"] = _validated_audio(raw.get("audio"))
    document["startup"] = _validated_startup(raw.get("startup"))
    return document


def save_document(document: Mapping[str, Any], path: Path | None = None) -> Path:
    target = path or config_path()
    validated = load_document_from_mapping(document)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".new")
    try:
        temporary.write_text(json.dumps(validated, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise OSError(f"Cannot save DCS Radio Voice Control configuration {target}: {exc}") from exc
    return target


def load_document_from_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["schema"] = SCHEMA
    result["setup_complete"] = _validated_setup_complete(
        value.get("setup_complete", False)
    )
    result["matching"] = _validated_matching(value.get("matching"))
    result["stt"] = _validated_stt(value.get("stt"))
    result["ptt"] = _validated_ptt(value.get("ptt"))
    result["feedback"] = _validated_feedback(value.get("feedback"))
    result["audio"] = _validated_audio(value.get("audio"))
    result["startup"] = _validated_startup(value.get("startup"))
    microphone = value.get("microphone")
    if microphone is not None and not isinstance(microphone, dict):
        raise ValueError("microphone must be an object")
    return result


def setup_complete(path: Path | None = None) -> bool:
    """Return whether first-run configuration was explicitly completed.

    Legacy configuration files predate this marker and are treated as complete.
    A new partial configuration created while learning PTT contains the explicit
    false marker, so closing the wizard cannot accidentally suppress first run.
    """
    target = path or config_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    if not isinstance(raw, dict):
        return False
    return raw.get("setup_complete", True) is True


def update_settings(
    document: Mapping[str, Any],
    *,
    minimum_score: float,
    minimum_lead: float,
    model: str,
    use_gpu: bool,
    output_device: str | None,
    microphone: Mapping[str, Any] | None,
    audio_cues: bool,
    cue_volume: float,
    start_with_windows: bool,
) -> dict[str, Any]:
    updated = dict(document)
    updated["matching"] = {
        "minimum_score": minimum_score,
        "minimum_lead": minimum_lead,
    }
    updated["stt"] = {"model": model, "use_gpu": use_gpu}
    updated["audio"] = {"output_device": output_device}
    updated["feedback"] = {"audio_cues": audio_cues, "cue_volume": cue_volume}
    updated["startup"] = {"start_with_windows": start_with_windows}
    if microphone is not None:
        updated["microphone"] = dict(microphone)
    return load_document_from_mapping(updated)


def _validated_setup_complete(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("setup_complete must be true or false")
    return value


def _validated_matching(value: object) -> dict[str, float]:
    source = value if isinstance(value, dict) else {}
    score = _bounded_float(
        source.get("minimum_score", DEFAULT_MINIMUM_SCORE),
        "minimum_score",
        *MINIMUM_SCORE_RANGE,
    )
    lead = _bounded_float(
        source.get("minimum_lead", DEFAULT_MINIMUM_LEAD),
        "minimum_lead",
        *MINIMUM_LEAD_RANGE,
    )
    return {"minimum_score": score, "minimum_lead": lead}


def _validated_stt(value: object) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    model = source.get("model", "ggml-base.en.bin")
    if not isinstance(model, str) or not model.startswith("ggml-") or not model.endswith(".bin"):
        raise ValueError("stt.model must be an installed ggml-*.bin filename")
    if Path(model).name != model:
        raise ValueError("stt.model must be a filename, not a path")
    use_gpu = source.get("use_gpu", False)
    if not isinstance(use_gpu, bool):
        raise ValueError("stt.use_gpu must be true or false")
    return {"model": model, "use_gpu": use_gpu}


def _validated_audio(value: object) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    output_device = source.get("output_device")
    if output_device is not None and (not isinstance(output_device, str) or not output_device):
        raise ValueError("audio.output_device must be a device name or null")
    return {"output_device": output_device}


def _validated_ptt(value: object) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    mode = source.get("mode", "keyboard")
    if mode == "keyboard":
        return {"mode": "keyboard"}
    if mode != "hotas":
        raise ValueError("ptt.mode must be keyboard or hotas")
    device_id = source.get("device_id")
    button = source.get("button")
    name = source.get("name")
    guid = source.get("guid")
    if not isinstance(device_id, int) or device_id < 0:
        raise ValueError("ptt.device_id must be a non-negative integer")
    if not isinstance(button, int) or button < 1:
        raise ValueError("ptt.button must be a positive integer")
    if not isinstance(name, str) or not name:
        raise ValueError("ptt.name must identify the controller")
    if not isinstance(guid, str) or not guid:
        raise ValueError("ptt.guid must identify the SDL controller")
    return {
        "mode": "hotas",
        "device_id": device_id,
        "name": name,
        "guid": guid,
        "button": button,
    }


def _validated_feedback(value: object) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    enabled = source.get("audio_cues", True)
    if not isinstance(enabled, bool):
        raise ValueError("feedback.audio_cues must be true or false")
    volume = _bounded_float(
        source.get("cue_volume", 0.25), "cue_volume", *CUE_VOLUME_RANGE
    )
    return {"audio_cues": enabled, "cue_volume": volume}


def _validated_startup(value: object) -> dict[str, bool]:
    source = value if isinstance(value, dict) else {}
    enabled = source.get("start_with_windows", False)
    if not isinstance(enabled, bool):
        raise ValueError("startup.start_with_windows must be true or false")
    return {"start_with_windows": enabled}


def _bounded_float(value: object, name: str, lower: float, upper: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    result = float(value)
    if not lower <= result <= upper:
        raise ValueError(f"{name} must be between {lower:.2f} and {upper:.2f}")
    return result
