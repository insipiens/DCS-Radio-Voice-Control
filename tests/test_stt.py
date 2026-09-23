from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from dcs_radio_voice_control.stt import MODEL_NAME, WhisperCpp, _acoustic_metrics, _multipart


class SttTests(unittest.TestCase):
    def test_installed_model_filename_is_configurable(self) -> None:
        recognizer = WhisperCpp(Path("test-root"), model_name="ggml-small.en.bin")
        self.assertEqual(recognizer.model.name, "ggml-small.en.bin")

    def test_missing_worker_or_model_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recognizer = WhisperCpp(Path(directory))
            with self.assertRaisesRegex(OSError, "setup-stt.bat"):
                recognizer.validate()

    def test_worker_and_model_are_validated_without_temp_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stt = root / "stt"
            stt.mkdir()
            (stt / "dcs_radio_voice_control-whisper.exe").write_bytes(b"test")
            (stt / MODEL_NAME).write_bytes(b"test")
            WhisperCpp(root).validate()
            self.assertEqual(list(root.glob("**/DCSRadioVoiceControl-*.wav")), [])

    def test_multipart_frames_prompt_and_in_memory_wave(self) -> None:
        body = _multipart(
            "boundary",
            {"response_format": "json", "prompt": "Wingman, Biggin Hill"},
            "audio.wav",
            b"RIFF-test",
        )
        self.assertIn(b'name="prompt"', body)
        self.assertIn(b"Wingman, Biggin Hill", body)
        self.assertIn(b"RIFF-test", body)
        self.assertTrue(body.endswith(b"--boundary--\r\n"))

    def test_multipart_requests_verbose_diagnostics(self) -> None:
        body = _multipart(
            "boundary",
            {
                "response_format": "verbose_json",
                "no_language_probabilities": "true",
            },
            "audio.wav",
            b"RIFF-test",
        )
        self.assertIn(b"verbose_json", body)
        self.assertIn(b"no_language_probabilities", body)

    def test_acoustic_metrics_summarise_verbose_response(self) -> None:
        metrics = _acoustic_metrics({
            "detected_language_probability": 0.98,
            "segments": [{
                "avg_logprob": -0.25,
                "no_speech_prob": 0.04,
                "words": [
                    {"word": " two", "probability": 0.9},
                    {"word": " cover", "probability": 0.7},
                    {"word": " me", "probability": 0.8},
                ],
            }],
        })
        self.assertTrue(metrics["available"])
        self.assertEqual(metrics["token_count"], 3)
        self.assertEqual(metrics["token_probability_mean"], 0.8)
        self.assertEqual(metrics["token_probability_min"], 0.7)
        self.assertEqual(metrics["avg_logprob_mean"], -0.25)
        self.assertEqual(metrics["no_speech_probability_max"], 0.04)

    def test_acoustic_metrics_report_unavailable_for_basic_json(self) -> None:
        self.assertEqual(_acoustic_metrics({"text": "Cover me"}), {"available": False})


if __name__ == "__main__":
    unittest.main()
