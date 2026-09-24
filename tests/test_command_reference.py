from __future__ import annotations

import unittest

from dcs_radio_voice_control.command_reference import (
    MetaCommand,
    function_key_item,
    list_node_children,
    parse_function_key,
    parse_meta_command,
    resolve_menu_navigation,
    resolve_guided_selection,
    spoken_listing,
)
from dcs_radio_voice_control.protocol import MenuItem
from dcs_radio_voice_control.voice_command_test import guided_menu_announcement


ITEMS = (
    MenuItem("1", "Startup", ("ATC", "Ford", "Startup")),
    MenuItem("2", "Taxi", ("ATC", "Ford", "Taxi")),
    MenuItem("3", "Inbound", ("ATC", "Tangmere", "Inbound")),
    MenuItem("4", "Engage", ("Wingman", "Engage", "Bandits")),
    MenuItem("5", "Rescue", ("Other", "Contact Air Sea Rescue")),
    MenuItem("6", "Cover", ("Flight", "Cover Me")),
    MenuItem("7", "Bandits", ("Flight", "Engage", "Engage Bandits")),
    MenuItem("8", "Bandits", ("Second Element", "Engage", "Engage Bandits")),
)

NAVIGATION_ITEMS = ITEMS + (
    MenuItem("menu.5", "ATC", ("ATC",), executable=False, slot=5),
    MenuItem("menu.5.1", "Ford", ("ATC", "Ford"), executable=False, slot=1),
    MenuItem("menu.5.2", "Tangmere", ("ATC", "Tangmere"), executable=False, slot=2),
    MenuItem("menu.10", "Other", ("Other",), executable=False, slot=10),
)


class CommandReferenceTests(unittest.TestCase):
    def test_parses_list_query(self) -> None:
        command = parse_meta_command("List ATC commands.")
        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command.kind, "list")
        self.assertEqual(command.node, "atc")

    def test_normalises_whisper_punctuation_and_singular_command(self) -> None:
        command = parse_meta_command("List, Second Element, Command.")
        self.assertEqual(command, MetaCommand("list", "second element"))

    def test_parses_safe_list_shorthand(self) -> None:
        self.assertEqual(parse_meta_command("F10 commands."), MetaCommand("list", "f10"))

    def test_parses_show_query_without_turning_it_into_a_list(self) -> None:
        for phrase in ("Show F10", "Display F10 commands", "Open F10 menu"):
            with self.subTest(phrase=phrase):
                self.assertEqual(parse_meta_command(phrase), MetaCommand("show", "f10"))

    def test_every_show_prefix_is_protected_from_action_matching(self) -> None:
        self.assertEqual(
            parse_meta_command("Show imaginary commands"),
            MetaCommand("show", "imaginary"),
        )

    def test_every_list_prefix_is_a_meta_command(self) -> None:
        self.assertEqual(parse_meta_command("List of a Command."), MetaCommand("list", "of a"))

    def test_parses_top_level_list_aliases(self) -> None:
        for phrase in (
            "List commands",
            "List all commands",
            "List categories",
            "List top-level commands",
            "List, Cabans.",
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(parse_meta_command(phrase), MetaCommand("list"))

    def test_parses_repeat_aliases(self) -> None:
        for phrase in ("repeat", "repeat please", "say again", "say again please"):
            with self.subTest(phrase=phrase):
                self.assertEqual(parse_meta_command(phrase).kind, "repeat")  # type: ignore[union-attr]

    def test_parses_previous_menu_controls(self) -> None:
        for phrase in ("Previous Menu", "F11", "F-11", "Back", "Show Previous Menu"):
            with self.subTest(phrase=phrase):
                self.assertEqual(parse_meta_command(phrase), MetaCommand("previous_menu"))

    def test_parses_exit_menu_controls(self) -> None:
        for phrase in ("Exit", "Exit Menu", "F12", "F-12", "Close Menu", "Show Exit Menu"):
            with self.subTest(phrase=phrase):
                self.assertEqual(parse_meta_command(phrase), MetaCommand("exit_menu"))

    def test_parses_bare_guided_function_keys(self) -> None:
        for phrase, expected in (("F1", 1), ("F-5", 5), ("F 10.", 10)):
            with self.subTest(phrase=phrase):
                self.assertEqual(parse_function_key(phrase), expected)
        self.assertIsNone(parse_function_key("Show F5"))
        self.assertIsNone(parse_function_key("F11"))

    def test_function_key_selects_only_the_visible_slot(self) -> None:
        root = function_key_item(NAVIGATION_ITEMS, (), 5)
        self.assertIsNotNone(root)
        self.assertEqual(root.path, ("ATC",))  # type: ignore[union-attr]
        nested = function_key_item(NAVIGATION_ITEMS, ("ATC",), 2)
        self.assertIsNotNone(nested)
        self.assertEqual(nested.path, ("ATC", "Tangmere"))  # type: ignore[union-attr]
        self.assertIsNone(function_key_item(NAVIGATION_ITEMS, ("Other",), 5))

    def test_guided_label_or_key_selects_only_immediate_visible_choice(self) -> None:
        items = NAVIGATION_ITEMS + (
            MenuItem("leaf.1", "Startup", ("ATC", "Ford", "Startup"), slot=1),
        )
        self.assertEqual(resolve_guided_selection(items, (), "F5").item.path, ("ATC",))  # type: ignore[union-attr]
        self.assertEqual(resolve_guided_selection(items, (), "ATC").item.path, ("ATC",))  # type: ignore[union-attr]
        self.assertEqual(resolve_guided_selection(items, ("ATC",), "Ford").item.path, ("ATC", "Ford"))  # type: ignore[union-attr]
        self.assertEqual(resolve_guided_selection(items, ("ATC", "Ford"), "F1").item.action_id, "leaf.1")  # type: ignore[union-attr]
        self.assertEqual(resolve_guided_selection(items, ("Other",), "ATC").status, "not_found")

    def test_guided_label_ignores_visual_trailing_dots_but_not_extra_words(self) -> None:
        items = (MenuItem("menu.atc", "ATC....", ("ATC....",), False, 5),)
        self.assertEqual(resolve_guided_selection(items, (), "ATC").item, items[0])
        for phrase in ("Go F5", "Show ATC", "Go ATC", "APC"):
            with self.subTest(phrase=phrase):
                self.assertEqual(resolve_guided_selection(items, (), phrase).status, "not_found")

    def test_guided_fuzzy_match_requires_a_unique_lead(self) -> None:
        items = (
            MenuItem("one", "Formation", ("Formation",), False, 1),
            MenuItem("two", "Formations", ("Formations",), False, 2),
        )
        selection = resolve_guided_selection(items, (), "Formationn")
        self.assertEqual(selection.status, "ambiguous")
        self.assertEqual(len(selection.choices), 2)

    def test_guided_announcement_lists_only_visible_choices(self) -> None:
        items = NAVIGATION_ITEMS + (
            MenuItem("menu.flight", "Flight....", ("Flight",), False, 2),
        )
        self.assertEqual(
            guided_menu_announcement(items, ()),
            "Radio menu. F 5: ATC. F 10: Other. F 2: Flight.",
        )

    def test_lists_immediate_children_only(self) -> None:
        listing = list_node_children(ITEMS, "ATC")
        self.assertEqual(listing.status, "found")
        self.assertEqual(listing.children, ("Ford", "Tangmere"))
        self.assertEqual(spoken_listing(listing), "Ford. Tangmere.")

    def test_compact_initialism_matches(self) -> None:
        listing = list_node_children(ITEMS, "A T C")
        self.assertEqual(listing.children, ("Ford", "Tangmere"))

    def test_lists_nested_node(self) -> None:
        listing = list_node_children(ITEMS, "Ford")
        self.assertEqual(listing.children, ("Startup", "Taxi"))

    def test_lists_full_nested_path(self) -> None:
        listing = list_node_children(ITEMS, "Second Element Engage")
        self.assertEqual(listing.children, ("Engage Bandits",))

    def test_lists_top_level_nodes(self) -> None:
        listing = list_node_children(ITEMS, None)
        self.assertEqual(listing.children, ("ATC", "Wingman", "Other", "Flight", "Second Element"))

    def test_duplicate_node_label_is_ambiguous(self) -> None:
        listing = list_node_children(ITEMS, "Engage")
        self.assertEqual(listing.status, "ambiguous")
        self.assertEqual(listing.choices, ("Wingman Engage", "Flight Engage", "Second Element Engage"))

    def test_f10_alias_resolves_dcs_other_root(self) -> None:
        listing = list_node_children(ITEMS, "F10")
        self.assertEqual(listing.status, "found")
        self.assertEqual(listing.node, "Other")
        self.assertEqual(listing.children, ("Contact Air Sea Rescue",))

    def test_f10_alias_does_not_match_nested_other(self) -> None:
        nested = ITEMS + (MenuItem("6", "Nested", ("ATC", "Other", "Nested")),)
        listing = list_node_children(nested, "F10")
        self.assertEqual(listing.children, ("Contact Air Sea Rescue",))

    def test_unknown_node_is_terse(self) -> None:
        listing = list_node_children(ITEMS, "carrier")
        self.assertEqual(spoken_listing(listing), "I didn't recognise that menu.")

    def test_known_f10_node_can_be_temporarily_empty(self) -> None:
        no_other = tuple(item for item in ITEMS if item.path[0] != "Other")
        listing = list_node_children(no_other, "F10")
        self.assertEqual(listing.status, "unavailable")
        self.assertEqual(spoken_listing(listing), "No F10 commands are currently available.")

    def test_known_radio_root_can_be_temporarily_empty(self) -> None:
        no_ground_crew = tuple(item for item in ITEMS if item.path[0] != "Ground Crew")
        listing = list_node_children(no_ground_crew, "Ground Crew")
        self.assertEqual(listing.status, "unavailable")
        self.assertEqual(
            spoken_listing(listing),
            "No Ground Crew commands are currently available.",
        )

    def test_show_f10_resolves_the_visual_other_menu(self) -> None:
        navigation = resolve_menu_navigation(NAVIGATION_ITEMS, "F10")
        self.assertEqual(navigation.status, "found")
        self.assertEqual(navigation.menu_id, "menu.10")
        self.assertEqual(navigation.path, ("Other",))

    def test_show_function_key_resolves_absolute_root_slot(self) -> None:
        navigation = resolve_menu_navigation(NAVIGATION_ITEMS, "F5")
        self.assertEqual(navigation.status, "found")
        self.assertEqual(navigation.menu_id, "menu.5")
        self.assertEqual(navigation.path, ("ATC",))

    def test_show_nested_menu_resolves_globally(self) -> None:
        navigation = resolve_menu_navigation(NAVIGATION_ITEMS, "Ford")
        self.assertEqual(navigation.menu_id, "menu.5.1")
        self.assertEqual(navigation.path, ("ATC", "Ford"))

    def test_visible_menu_limits_plain_navigation_to_immediate_children(self) -> None:
        navigation = resolve_menu_navigation(
            NAVIGATION_ITEMS,
            "Ford",
            current_path=("ATC",),
        )
        self.assertEqual(navigation.menu_id, "menu.5.1")
        leaf = resolve_menu_navigation(
            NAVIGATION_ITEMS,
            "Startup",
            current_path=("ATC", "Ford"),
        )
        self.assertEqual(leaf.status, "leaf")
        self.assertEqual(leaf.path, ("ATC", "Ford"))

    def test_guided_navigation_cannot_jump_to_another_root(self) -> None:
        navigation = resolve_menu_navigation(
            NAVIGATION_ITEMS,
            "ATC",
            current_path=("Other",),
        )
        self.assertEqual(navigation.status, "not_found")

    def test_guided_root_still_understands_f10_as_other(self) -> None:
        navigation = resolve_menu_navigation(
            NAVIGATION_ITEMS,
            "F10",
            current_path=(),
        )
        self.assertEqual(navigation.status, "found")
        self.assertEqual(navigation.path, ("Other",))

    def test_show_top_level_opens_radio_root(self) -> None:
        navigation = resolve_menu_navigation(NAVIGATION_ITEMS, None)
        self.assertEqual(navigation.menu_id, "menu.root")
        self.assertEqual(navigation.path, ())


if __name__ == "__main__":
    unittest.main()
