from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from dcs_radio_voice_control.configuration_store import (
    DEFAULT_MINIMUM_LEAD,
    DEFAULT_MINIMUM_SCORE,
    load_document,
    save_document,
)


class ConfigurationStoreTests(unittest.TestCase):
    def test_legacy_microphone_configuration_gets_safe_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"schema": 1, "microphone": {"device_id": 3, "name": "VR", "channels": 1}}),
                encoding="utf-8",
            )
            document = load_document(path)
        self.assertEqual(document["schema"], 7)
        self.assertEqual(document["microphone"]["name"], "VR")
        self.assertEqual(document["matching"]["minimum_score"], DEFAULT_MINIMUM_SCORE)
        self.assertEqual(document["matching"]["minimum_lead"], DEFAULT_MINIMUM_LEAD)
        self.assertEqual(document["ptt"], {"mode": "keyboard"})
        self.assertEqual(document["feedback"], {"audio_cues": True, "cue_volume": 0.25})
        self.assertEqual(document["stt"]["use_gpu"], False)
        self.assertEqual(document["audio"], {"output_device": None})
        self.assertEqual(document["startup"], {"start_with_windows": False})
        self.assertTrue(document["setup_complete"])

    def test_new_configuration_starts_incomplete_and_persists_partial_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            document = load_document(path)
            self.assertFalse(document["setup_complete"])
            document["ptt"] = {"mode": "keyboard"}
            save_document(document, path)
            self.assertFalse(load_document(path)["setup_complete"])

    def test_audio_and_hotas_settings_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            document = load_document(path)
            document["ptt"] = {
                "mode": "hotas",
                "device_id": 7,
                "name": "Throttle",
                "guid": "0300abcd",
                "button": 47,
            }
            document["audio"] = {"output_device": "VR headset"}
            save_document(document, path)
            saved = load_document(path)
            self.assertEqual(saved["ptt"]["button"], 47)
            self.assertEqual(saved["audio"]["output_device"], "VR headset")

    def test_match_settings_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            document = load_document(path)
            document["matching"]["minimum_score"] = 0.20
            with self.assertRaisesRegex(ValueError, "between"):
                save_document(document, path)


if __name__ == "__main__":
    unittest.main()
