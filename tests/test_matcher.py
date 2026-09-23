from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from dcs_radio_voice_control.matcher import (
    MatchResult,
    RankedMatch,
    build_vocabulary_prompt,
    critical_terms_compatible,
    match_catalogue,
    match_reviewed_alias,
    normalize_phrase,
    recipient_scope,
    strong_semantic_match,
)
from dcs_radio_voice_control.dcs_client import ActionResult
from dcs_radio_voice_control.protocol import MenuItem, MenuSnapshot
from dcs_radio_voice_control.voice_command_test import (
    MINIMUM_EXECUTION_SCORE,
    MINIMUM_EXECUTION_LEAD,
    action_alias_for_transcript,
    contextual_catalogue,
    control_live_menu,
    execution_candidate,
    remember_catalogue,
    unavailable_candidate,
    visible_path_after_menu_control,
    wait_for_catalogue,
)


ITEMS = (
    MenuItem("radio.1.4.1", "Break Right", ("Wingman", "Maneuvers", "Break Right")),
    MenuItem("radio.1.4.2", "Break Left", ("Wingman", "Maneuvers", "Break Left")),
    MenuItem("radio.2.4.1", "Break Right", ("Flight", "Maneuvers", "Break Right")),
    MenuItem("radio.2.4.2", "Break Left", ("Flight", "Maneuvers", "Break Left")),
    MenuItem(
        "radio.3.4.2",
        "Break Left",
        ("Second Element", "Maneuvers", "Break Left"),
    ),
    MenuItem(
        "radio.5.1.1",
        "Request Start-Up",
        ("ATC", "Biggin Hill", "Request Start-Up"),
    ),
    MenuItem(
        "radio.5.2.1",
        "Request Start-Up",
        ("ATC", "Kenley", "Request Start-Up"),
    ),
    MenuItem("f10.10.1", "Contact Air Sea Rescue", ("Other", "Contact Air Sea Rescue")),
    MenuItem("f10.10.2", "Stop Broadcast", ("Other", "Stop Broadcast")),
)


class MatcherTests(unittest.TestCase):
    def test_normalizes_punctuation_and_common_compounds(self) -> None:
        self.assertEqual(normalize_phrase("Request start-up!"), "request start up")
        self.assertEqual(normalize_phrase("Wing man"), "wingman")

    def test_recipient_and_leaf_select_unique_command(self) -> None:
        result = match_catalogue("Wingman, break left", ITEMS)
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.best.item.action_id, "radio.1.4.2")  # type: ignore[union-attr]

    def test_framed_recipient_command_matches(self) -> None:
        result = match_catalogue("Please tell the wingman to break right", ITEMS)
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.best.item.action_id, "radio.1.4.1")  # type: ignore[union-attr]

    def test_configured_two_alias_scopes_but_does_not_score_the_action(self) -> None:
        with patch(
            "dcs_radio_voice_control.matcher.reviewed_aliases",
            return_value={"two": "Wingman"},
        ):
            scope = recipient_scope("Two, great left")
            result = match_catalogue("Two, great left", ITEMS)
        self.assertEqual(scope.scope, "wingman")  # type: ignore[union-attr]
        self.assertEqual(scope.command, "great left")  # type: ignore[union-attr]
        self.assertEqual(scope.alias, "two")  # type: ignore[union-attr]
        wingman_items = tuple(item for item in ITEMS if item.path[0] == "Wingman")
        unscoped_score = match_catalogue("great left", wingman_items).best.score  # type: ignore[union-attr]
        self.assertEqual(result.best.item.action_id, "radio.1.4.2")  # type: ignore[union-attr]
        self.assertEqual(result.best.score, unscoped_score)  # type: ignore[union-attr]

    def test_recipient_vocabulary_is_not_hard_coded(self) -> None:
        with patch("dcs_radio_voice_control.matcher.reviewed_aliases", return_value={}):
            self.assertIsNone(recipient_scope("Two, break left"))
            self.assertIsNone(recipient_scope("2 break left"))
            self.assertIsNone(recipient_scope("Element break left"))
            self.assertIsNone(recipient_scope("Three and four, break left"))

    def test_configured_element_alias_scopes_second_element(self) -> None:
        with patch(
            "dcs_radio_voice_control.matcher.reviewed_aliases",
            return_value={"element": "Second Element"},
        ):
            result = match_catalogue("Element break left", ITEMS)
        self.assertEqual(result.best.item.action_id, "radio.3.4.2")  # type: ignore[union-attr]

    def test_configured_multiword_alias_scopes_second_element(self) -> None:
        with patch(
            "dcs_radio_voice_control.matcher.reviewed_aliases",
            return_value={"three and four": "Second Element"},
        ):
            result = match_catalogue("Three and four, break left", ITEMS)
        self.assertEqual(result.best.item.action_id, "radio.3.4.2")  # type: ignore[union-attr]

    def test_recipient_alias_alone_cannot_nominate_an_action(self) -> None:
        with patch(
            "dcs_radio_voice_control.matcher.reviewed_aliases",
            return_value={"two": "Wingman"},
        ):
            self.assertEqual(match_catalogue("Two", ITEMS).status, "no_match")

    def test_homophones_are_not_recipient_aliases(self) -> None:
        with patch(
            "dcs_radio_voice_control.matcher.reviewed_aliases",
            return_value={"two": "Wingman"},
        ):
            self.assertIsNone(recipient_scope("to break left"))
            self.assertIsNone(recipient_scope("too break left"))

    def test_scoped_alias_cannot_use_a_legacy_whole_command_override(self) -> None:
        with patch(
            "dcs_radio_voice_control.matcher.reviewed_aliases",
            return_value={"two": "Wingman"},
        ), patch(
            "dcs_radio_voice_control.voice_command_test.reviewed_alias",
            return_value="Wingman > Maneuvers > Break Left",
        ):
            recipient, target = action_alias_for_transcript("Two, great left")
        self.assertEqual(recipient.scope, "wingman")  # type: ignore[union-attr]
        self.assertIsNone(target)

    def test_leaf_without_recipient_is_ambiguous(self) -> None:
        result = match_catalogue("Break left", ITEMS)
        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(len(result.candidates), 3)

    def test_atc_location_disambiguates_repeated_command(self) -> None:
        result = match_catalogue("Biggin Hill request startup", ITEMS)
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.best.item.action_id, "radio.5.1.1")  # type: ignore[union-attr]

    def test_exact_full_path_bypasses_generic_lead_gate(self) -> None:
        result = match_catalogue("ATC Biggin Hill request startup", ITEMS)
        self.assertEqual(result.best.item.action_id, "radio.5.1.1")  # type: ignore[union-attr]
        self.assertTrue(result.best.exact)  # type: ignore[union-attr]
        self.assertIsNotNone(execution_candidate(result))

    def test_f10_leaf_matches_without_saying_other(self) -> None:
        result = match_catalogue("Contact air-sea rescue", ITEMS)
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.best.item.action_id, "f10.10.1")  # type: ignore[union-attr]

    def test_observed_biggin_hill_error_uses_full_path_evidence(self) -> None:
        result = match_catalogue("Begin hill, request startup", ITEMS)
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.best.item.action_id, "radio.5.1.1")  # type: ignore[union-attr]
        self.assertGreaterEqual(result.best.score, MINIMUM_EXECUTION_SCORE)  # type: ignore[union-attr]

    def test_misheard_recipient_without_clear_lead_is_not_executed(self) -> None:
        result = match_catalogue("Women break left", ITEMS)
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.best.item.action_id, "radio.1.4.2")  # type: ignore[union-attr]
        self.assertIsNone(execution_candidate(result))

    def test_observed_air_sea_error_finds_best_path_without_rewriting(self) -> None:
        result = match_catalogue("Contact SC Rescue", ITEMS)
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.best.item.action_id, "f10.10.1")  # type: ignore[union-attr]
        self.assertIsNotNone(execution_candidate(result))

    def test_reviewed_alias_target_requires_an_exact_unique_command(self) -> None:
        exact = match_reviewed_alias("Flight > Maneuvers > Break Left", ITEMS)
        self.assertEqual(exact.status, "matched")
        self.assertEqual(exact.best.item.action_id, "radio.2.4.2")  # type: ignore[union-attr]
        ambiguous = match_reviewed_alias("Break Left", ITEMS)
        self.assertEqual(ambiguous.status, "ambiguous")
        self.assertEqual(match_reviewed_alias("Flight Break", ITEMS).status, "no_match")

    def test_live_vocabulary_prompt_prioritizes_path_levels_and_deduplicates(self) -> None:
        prompt = build_vocabulary_prompt(ITEMS)
        self.assertTrue(prompt.startswith("DCS radio command vocabulary:"))
        self.assertIn("Wingman", prompt)
        self.assertIn("Biggin Hill", prompt)
        self.assertIn("Contact Air Sea Rescue", prompt)
        self.assertIn("Show Menu", prompt)
        self.assertIn("Previous Menu", prompt)
        self.assertIn("Exit Menu", prompt)
        self.assertIn("F1", prompt)
        self.assertIn("F10", prompt)
        self.assertIn("F11", prompt)
        self.assertIn("F12", prompt)
        self.assertEqual(prompt.count("Break Left"), 1)

    def test_live_vocabulary_prompt_respects_length_limit(self) -> None:
        prompt = build_vocabulary_prompt(ITEMS, maximum_characters=80)
        self.assertLessEqual(len(prompt), 80)
        self.assertTrue(prompt.endswith("."))

    def test_control_vocabulary_exists_without_live_actions(self) -> None:
        prompt = build_vocabulary_prompt(())
        self.assertIn("Previous Menu", prompt)
        self.assertIn("Exit Menu", prompt)

    def test_unrelated_speech_does_not_match(self) -> None:
        result = match_catalogue("What is the weather tomorrow", ITEMS)
        self.assertEqual(result.status, "no_match")

    def test_opposite_state_word_cannot_match(self) -> None:
        stop = next(item for item in ITEMS if item.action_id == "f10.10.2")
        result = match_catalogue("Start radio broadcast", (stop,))
        self.assertEqual(result.status, "no_match")
        self.assertEqual(result.ranked[0].score, 0.0)

    def test_stateful_action_requires_its_qualifier(self) -> None:
        stop = next(item for item in ITEMS if item.action_id == "f10.10.2")
        result = match_catalogue("Broadcast", (stop,))
        self.assertEqual(result.status, "no_match")
        self.assertEqual(result.ranked[0].score, 0.0)

    def test_critical_direction_terms_must_agree(self) -> None:
        self.assertFalse(critical_terms_compatible("break left", "break right"))
        self.assertTrue(critical_terms_compatible("break left", "wingman break left"))

    def test_stale_revalidation_accepts_same_semantic_action(self) -> None:
        stop = next(item for item in ITEMS if item.action_id == "f10.10.2")
        self.assertTrue(strong_semantic_match("Stop radio broadcast", stop))
        self.assertFalse(strong_semantic_match("Start radio broadcast", stop))

    def test_last_seen_command_can_be_reported_as_unavailable(self) -> None:
        broadcast = MenuItem(
            "f10.10.3",
            "Radio Broadcast",
            ("Other", "Radio Broadcast"),
        )
        known = {}
        remember_catalogue(known, (broadcast,))
        candidate = unavailable_candidate("Radio Broadcast", (), known)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.item, broadcast)  # type: ignore[union-attr]

    def test_live_command_is_not_reported_as_unavailable(self) -> None:
        broadcast = MenuItem(
            "f10.10.3",
            "Radio Broadcast",
            ("Other", "Radio Broadcast"),
        )
        known = {}
        remember_catalogue(known, (broadcast,))
        self.assertIsNone(unavailable_candidate("Radio Broadcast", (broadcast,), known))

    def test_matching_test_contains_no_execution_call(self) -> None:
        source = (
            Path(__file__).parents[1] / "src" / "dcs_radio_voice_control" / "matching_test.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn(".execute(", source)

    def test_exact_unique_match_is_eligible_for_execution(self) -> None:
        result = match_catalogue("Wingman break left", ITEMS)
        candidate = execution_candidate(result)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.item.action_id, "radio.1.4.2")  # type: ignore[union-attr]

    def test_weaker_match_is_not_eligible_for_execution(self) -> None:
        result = MatchResult(
            "matched",
            (RankedMatch(ITEMS[0], MINIMUM_EXECUTION_SCORE - 0.01),),
        )
        self.assertIsNone(execution_candidate(result))

    def test_unique_lower_score_with_clear_lead_is_eligible(self) -> None:
        best = RankedMatch(ITEMS[1], 0.89)
        runner_up = RankedMatch(ITEMS[0], 0.65)
        result = MatchResult("matched", (best,), (best, runner_up))
        self.assertEqual(execution_candidate(result), best)

    def test_observed_great_left_transcript_passes_margin_gate(self) -> None:
        result = match_catalogue("Wingman, Great Left", ITEMS)
        candidate = execution_candidate(result)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.item.action_id, "radio.1.4.2")  # type: ignore[union-attr]

    def test_lower_score_with_narrow_lead_is_not_eligible(self) -> None:
        best = RankedMatch(ITEMS[1], 0.78)
        runner_up = RankedMatch(ITEMS[0], 0.78 - MINIMUM_EXECUTION_LEAD + 0.01)
        result = MatchResult("matched", (best,), (best, runner_up))
        self.assertIsNone(execution_candidate(result))

    def test_ambiguous_match_is_not_eligible_for_execution(self) -> None:
        result = match_catalogue("Break left", ITEMS)
        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(execution_candidate(result))

    def test_display_only_item_is_not_eligible_for_execution(self) -> None:
        item = MenuItem("legacy.1", "Test", ("Test",), executable=False)
        result = MatchResult("matched", (RankedMatch(item, 1.0),))
        self.assertIsNone(execution_candidate(result))

    def test_visible_submenu_disambiguates_a_repeated_leaf(self) -> None:
        scoped = contextual_catalogue(ITEMS, ("ATC", "Biggin Hill"))
        result = match_catalogue("Request Start-Up", scoped)
        candidate = execution_candidate(result)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.item.action_id, "radio.5.1.1")  # type: ignore[union-attr]

    def test_visible_submenu_never_adds_navigation_nodes_to_action_matching(self) -> None:
        menu = MenuItem("menu.5.1", "Biggin Hill", ("ATC", "Biggin Hill"), False)
        scoped = contextual_catalogue(ITEMS + (menu,), ("ATC", "Biggin Hill"))
        self.assertTrue(scoped)
        self.assertTrue(all(item.executable for item in scoped))

    def test_menu_controls_update_only_known_visual_context(self) -> None:
        self.assertEqual(
            visible_path_after_menu_control(("ATC", "Biggin Hill"), "previous"),
            ("ATC",),
        )
        self.assertEqual(visible_path_after_menu_control(("Other",), "previous"), ())
        self.assertIsNone(visible_path_after_menu_control(None, "previous"))
        self.assertIsNone(visible_path_after_menu_control(("ATC",), "exit"))

    def test_stale_menu_control_is_retried_against_fresh_revision(self) -> None:
        initial = MenuSnapshot(3, ITEMS)
        refreshed = MenuSnapshot(4, ITEMS)

        class ControlClient:
            def __init__(self) -> None:
                self.revisions: list[int] = []
                self.results = [
                    ActionResult("first", False, "stale_revision", "changed"),
                    ActionResult("second", True, "previous_menu", ""),
                ]

            def control_menu(self, _operation: str, revision: int) -> str:
                self.revisions.append(revision)
                return str(revision)

            def wait_for_result(self, _request_id: str) -> ActionResult:
                return self.results.pop(0)

            def request_menu_and_wait(self, timeout: float) -> MenuSnapshot:
                self.assert_timeout = timeout
                return refreshed

        client = ControlClient()
        snapshot, result = control_live_menu(client, initial, "previous")  # type: ignore[arg-type]
        self.assertEqual(snapshot.revision, 4)
        self.assertIsNotNone(result)
        self.assertTrue(result.accepted)  # type: ignore[union-attr]
        self.assertEqual(client.revisions, [3, 4])

    def test_navigation_nodes_are_not_remembered_as_unavailable_actions(self) -> None:
        menu = MenuItem("menu.5", "ATC", ("ATC",), False)
        known = {}
        remember_catalogue(known, (menu, ITEMS[5]))
        self.assertNotIn(menu.path, known)
        self.assertIn(ITEMS[5].path, known)

    def test_startup_wait_retries_until_catalogue_arrives(self) -> None:
        class WaitingClient:
            def __init__(self) -> None:
                self.calls = 0
                self.hook_status = type("HookStatus", (), {"compatible": True})()

            def request_menu_and_wait(self, timeout: float) -> object | None:
                self.calls += 1
                return object() if self.calls == 3 else None

        client = WaitingClient()
        with redirect_stdout(io.StringIO()):
            wait_for_catalogue(client)  # type: ignore[arg-type]
        self.assertEqual(client.calls, 3)

    def test_startup_rejects_a_loaded_legacy_hook(self) -> None:
        class LegacyClient:
            hook_status = type("HookStatus", (), {"compatible": False})()

            def request_menu_and_wait(self, timeout: float) -> object:
                return object()

        with self.assertRaisesRegex(OSError, "older DCS Radio Voice Control hook"):
            wait_for_catalogue(LegacyClient())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
