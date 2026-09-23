from __future__ import annotations

import unittest

from dcs_radio_voice_control.configuration_ui import PAGE


class ConfigurationUiTests(unittest.TestCase):
    def test_page_exposes_required_setup_controls(self) -> None:
        for label in (
            "Audio devices",
            "Microphone input",
            "Speech and cue output",
            "Recording device",
            "Learn a HOTAS button",
            "Minimum match",
            "Minimum lead over runner-up",
            "Installed Whisper model",
            "Use GPU acceleration",
            "Playback device",
            "Test Alan voice",
            "Recent activity",
            "Audio feedback",
            "Automatic startup",
            "Start DCS Radio Voice Control with Windows",
            "Test accepted cue",
            "Save configuration and start",
            "__TOKEN__",
            "__START_AFTER_SAVE__",
        ):
            self.assertIn(label, PAGE)
        self.assertIn("X-DCS-Radio-Voice-Control-Token", PAGE)
        self.assertNotIn("X-DCS Radio Voice Control-Token", PAGE)
        self.assertIn("startAfterSave?'/api/settings/start':'/api/settings'", PAGE)


if __name__ == "__main__":
    unittest.main()
