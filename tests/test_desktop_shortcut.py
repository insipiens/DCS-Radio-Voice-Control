from __future__ import annotations

import unittest

from dcs_radio_voice_control.desktop_shortcut import SHORTCUT_NAME


class DesktopShortcutTests(unittest.TestCase):
    def test_shortcut_has_stable_user_facing_name(self) -> None:
        self.assertEqual(SHORTCUT_NAME, "DCS Radio Voice Control.lnk")


if __name__ == "__main__":
    unittest.main()
