from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from dcs_radio_voice_control.alias_store import (
    record_pending_alias,
    record_pending_meta_alias,
    reviewed_alias,
    reviewed_aliases,
    reviewed_meta_alias,
)


class AliasStoreTests(unittest.TestCase):
    def test_new_alias_is_null(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pending_aliases.json"
            self.assertTrue(record_pending_alias("Contact R C Rescue", path))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"contact r c rescue": None})

    def test_existing_reviewed_mapping_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pending_aliases.json"
            path.write_text('{"contact rescue": "Contact Air Sea Rescue"}\n', encoding="utf-8")
            self.assertFalse(record_pending_alias("Contact rescue", path))
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"contact rescue": "Contact Air Sea Rescue"},
            )

    def test_meta_aliases_use_a_separate_store(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pending_meta_aliases.json"
            self.assertTrue(record_pending_meta_alias("List of a Command", path))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"list of a command": None})

    def test_reviewed_alias_is_loaded_but_null_candidate_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pending_aliases.json"
            path.write_text(
                json.dumps(
                    {
                        "flight rejoin": "Flight > Rejoin Formation",
                        "flight rejoyed": None,
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                reviewed_alias("Flight, rejoin.", path),
                "Flight > Rejoin Formation",
            )
            self.assertIsNone(reviewed_alias("Flight, rejoyed.", path))

    def test_all_reviewed_aliases_are_normalized_and_nulls_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pending_aliases.json"
            path.write_text(
                json.dumps(
                    {
                        "Two!": "Wingman",
                        "Element": "Second Element",
                        "unused": None,
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                reviewed_aliases(path),
                {"two": "Wingman", "element": "Second Element"},
            )

    def test_reviewed_meta_alias_uses_meta_store(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pending_meta_aliases.json"
            path.write_text('{"list over": "List Other commands"}\n', encoding="utf-8")
            self.assertEqual(
                reviewed_meta_alias("List over.", path),
                "List Other commands",
            )


if __name__ == "__main__":
    unittest.main()
