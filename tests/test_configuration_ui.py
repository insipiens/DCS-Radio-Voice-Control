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
            "Windows integration",
            "Create a Desktop shortcut",
            "Start when DCS starts",
            "Test accepted cue",
            "Save configuration and close",
            "__TOKEN__",
            "__CLOSE_AFTER_SAVE__",
        ):
            self.assertIn(label, PAGE)
        self.assertIn("X-DCS-Radio-Voice-Control-Token", PAGE)
        self.assertNotIn("X-DCS Radio Voice Control-Token", PAGE)
        self.assertIn("closeAfterSave?'/api/settings/close':'/api/settings'", PAGE)
        self.assertIn("desktop_shortcut:$('desktopShortcut').checked", PAGE)


if __name__ == "__main__":
    unittest.main()
