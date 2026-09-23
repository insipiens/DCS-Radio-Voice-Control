"""Persistent local speech recognition through whisper.cpp's native server."""

from __future__ import annotations

import atexit
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

from .recording_test import _wav_bytes


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_NAME = "ggml-base.en.bin"


@dataclass(frozen=True)
class TranscriptionMetrics:
    model: str
    compute: str
    audio_seconds: float
    inference_seconds: float
    real_time_factor: float
    model_load_seconds: float


def _acoustic_metrics(document: object) -> dict[str, object]:
    """Summarise whisper.cpp verbose diagnostics without treating them as a gate."""
    if not isinstance(document, dict):
        return {"available": False}
    raw_segments = document.get("segments")
    if not isinstance(raw_segments, list):
        return {"available": False}

    segments: list[dict[str, object]] = []
    all_probabilities: list[float] = []
    avg_logprobs: list[float] = []
    no_speech_probabilities: list[float] = []
    for raw_segment in raw_segments:
        if not isinstance(raw_segment, dict):
            continue
        words = raw_segment.get("words")
        probabilities = (
            [
                float(word["probability"])
                for word in words
                if isinstance(word, dict)
                and isinstance(word.get("probability"), (int, float))
            ]
            if isinstance(words, list)
            else []
        )
        avg_logprob = raw_segment.get("avg_logprob")
        no_speech = raw_segment.get("no_speech_prob")
        segment: dict[str, object] = {
            "token_count": len(probabilities),
        }
        if probabilities:
            segment.update(
                token_probability_mean=round(sum(probabilities) / len(probabilities), 6),
                token_probability_min=round(min(probabilities), 6),
            )
            all_probabilities.extend(probabilities)
        if isinstance(avg_logprob, (int, float)):
            value = float(avg_logprob)
            segment["avg_logprob"] = round(value, 6)
            avg_logprobs.append(value)
        if isinstance(no_speech, (int, float)):
            value = float(no_speech)
            segment["no_speech_probability"] = round(value, 6)
            no_speech_probabilities.append(value)
        segments.append(segment)

    result: dict[str, object] = {
        "available": bool(segments),
        "segment_count": len(segments),
        "segments": segments,
    }
    if all_probabilities:
        result.update(
            token_count=len(all_probabilities),
            token_probability_mean=round(sum(all_probabilities) / len(all_probabilities), 6),
            token_probability_min=round(min(all_probabilities), 6),
        )
    if avg_logprobs:
        result.update(
            avg_logprob_mean=round(sum(avg_logprobs) / len(avg_logprobs), 6),
            avg_logprob_min=round(min(avg_logprobs), 6),
        )
    if no_speech_probabilities:
        result.update(
            no_speech_probability_mean=round(
                sum(no_speech_probabilities) / len(no_speech_probabilities), 6
            ),
            no_speech_probability_max=round(max(no_speech_probabilities), 6),
        )
    language_probability = document.get("detected_language_probability")
    if isinstance(language_probability, (int, float)):
        result["detected_language_probability"] = round(float(language_probability), 6)
    return result


class WhisperCpp:
    """Keep one native whisper.cpp model resident and send audio from memory."""

    def __init__(
        self,
        root: Path = PROJECT_ROOT,
        *,
        model_name: str = MODEL_NAME,
        use_gpu: bool = False,
        process_factory: object = subprocess.Popen,
    ) -> None:
        self.directory = root / "stt"
        self.executable = self.directory / "dcs_radio_voice_control-whisper.exe"
        if Path(model_name).name != model_name:
            raise ValueError("Whisper model must be a filename")
        self.model = self.directory / model_name
        self.use_gpu = bool(use_gpu)
        self._process_factory = process_factory
        self._process: subprocess.Popen[bytes] | None = None
        self._port: int | None = None
        self._load_seconds = 0.0
        self.last_metrics: dict[str, object] = {}
        atexit.register(self.close)

    def validate(self) -> None:
        missing = [path for path in (self.executable, self.model) if not path.is_file()]
        if missing:
            raise OSError(
                "Local speech recognition is not installed. Run setup-stt.bat first."
            )

    def start(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        self.validate()
        self.close()
        self._port = _available_loopback_port()
        command = [
            str(self.executable),
            "--host", "127.0.0.1",
            "--port", str(self._port),
            "--model", str(self.model),
            "--language", "en",
        ]
        if not self.use_gpu:
            command.append("--no-gpu")
        started = time.monotonic()
        self._process = self._process_factory(
            command,
            cwd=self.directory,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = started + 45.0
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise OSError("whisper.cpp worker stopped during startup")
            try:
                with urlopen(f"http://127.0.0.1:{self._port}/", timeout=0.25):
                    self._load_seconds = time.monotonic() - started
                    return
            except (OSError, URLError):
                time.sleep(0.05)
        self.close()
        raise OSError("whisper.cpp worker did not become ready within 45 seconds")

    def transcribe(self, pcm: bytes, *, prompt: str | None = None) -> str:
        self.start()
        assert self._port is not None
        boundary = "DCSRadioVoiceControl-" + uuid.uuid4().hex
        fields = {
            "response_format": "verbose_json",
            # Language is fixed to English; skip the server's additional,
            # expensive language-detection pass.
            "no_language_probabilities": "true",
            "language": "en",
            "prompt": (prompt or "").strip(),
        }
        body = _multipart(boundary, fields, "audio.wav", _wav_bytes(pcm))
        request = Request(
            f"http://127.0.0.1:{self._port}/inference",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urlopen(request, timeout=60.0) as response:
                document = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, json.JSONDecodeError) as exc:
            self.close()
            raise OSError(f"whisper.cpp inference failed: {exc}") from exc
        elapsed = time.monotonic() - started
        duration = len(pcm) / (16_000 * 2)
        metrics = TranscriptionMetrics(
            model=self.model.name,
            compute="gpu" if self.use_gpu else "cpu",
            audio_seconds=round(duration, 3),
            inference_seconds=round(elapsed, 3),
            real_time_factor=round(elapsed / duration, 4) if duration else 0.0,
            model_load_seconds=round(self._load_seconds, 3),
        )
        self.last_metrics = asdict(metrics)
        self.last_metrics["acoustic"] = _acoustic_metrics(document)
        value = document.get("text", "") if isinstance(document, dict) else ""
        return " ".join(str(value).split())

    def close(self) -> None:
        process = self._process
        self._process = None
        self._port = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)

    def __enter__(self) -> "WhisperCpp":
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _multipart(
    boundary: str, fields: dict[str, str], filename: str, payload: bytes
) -> bytes:
    marker = boundary.encode("ascii")
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.extend((
            b"--" + marker + b"\r\n",
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
            value.encode("utf-8"),
            b"\r\n",
        ))
    parts.extend((
        b"--" + marker + b"\r\n",
        (
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode("utf-8"),
        payload,
        b"\r\n--" + marker + b"--\r\n",
    ))
    return b"".join(parts)
