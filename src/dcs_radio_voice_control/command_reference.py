"""Application-side spoken queries over the live DCS menu hierarchy."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata

from .protocol import MenuItem

_REPEAT = {"repeat", "repeat please", "say again", "say again please"}
_PREVIOUS_MENU = {"back", "backmenu", "f11", "previous", "previousmenu"}
_EXIT_MENU = {"close", "closemenu", "exit", "exitmenu", "f12"}
_F10_ROOT_LABELS = {"f10", "f10other", "other"}
_F10_REQUESTS = {"f10", "f10other", "otherf10", "other"}
_KNOWN_ROOTS = {
    "wingman": "Wingman",
    "flight": "Flight",
    "secondelement": "Second Element",
    "atc": "ATC",
    "groundcrew": "Ground Crew",
}
_TOP_LEVEL_REQUESTS = {"", "all", "categories", "category", "toplevel"}
_COMMAND_WORDS = {"command", "commands", "cabans"}
_SHOW_WORDS = {"show", "display", "open"}
_MENU_WORDS = {"menu", "menus"}
_MINIMUM_NODE_SCORE = 0.72
_MINIMUM_NODE_LEAD = 0.10


@dataclass(frozen=True, slots=True)
class MetaCommand:
    kind: str
    node: str | None = None


@dataclass(frozen=True, slots=True)
class NodeListing:
    status: str
    node: str | None
    children: tuple[str, ...] = ()
    choices: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MenuNavigation:
    status: str
    menu_id: str | None = None
    path: tuple[str, ...] = ()
    choices: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GuidedSelection:
    status: str
    item: MenuItem | None = None
    choices: tuple[str, ...] = ()
    scores: tuple[tuple[str, float], ...] = ()


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _compact(text: str) -> str:
    return _normalise(text).replace(" ", "")


def parse_meta_command(transcript: str) -> MetaCommand | None:
    normalised = _normalise(transcript)
    compact = normalised.replace(" ", "")
    if normalised in _REPEAT:
        return MetaCommand("repeat")
    if compact in _PREVIOUS_MENU:
        return MetaCommand("previous_menu")
    if compact in _EXIT_MENU:
        return MetaCommand("exit_menu")

    words = normalised.split()
    if not words:
        return None

    if words[0] in _SHOW_WORDS:
        words = words[1:]
        if words and words[-1] in (_COMMAND_WORDS | _MENU_WORDS):
            words = words[:-1]
        node = " ".join(words)
        compact_node = _compact(node)
        if compact_node in _PREVIOUS_MENU:
            return MetaCommand("previous_menu")
        if compact_node in _EXIT_MENU:
            return MetaCommand("exit_menu")
        if _compact(node) in _TOP_LEVEL_REQUESTS:
            node = ""
        return MetaCommand("show", node=node or None)

    # Treat every utterance beginning with "list" as informational.  A
    # malformed list request must never fall through to live action matching.
    if words[0] == "list":
        words = words[1:]
    elif words[-1] in _COMMAND_WORDS:
        # Safe cockpit shorthand: "F10 commands" or "ATC commands".
        pass
    else:
        return None

    if words and words[-1] in _COMMAND_WORDS:
        words = words[:-1]
    node = " ".join(words)
    if _compact(node) in _TOP_LEVEL_REQUESTS:
        node = ""
    return MetaCommand("list", node=node or None)


def parse_function_key(transcript: str) -> int | None:
    """Return a bare spoken DCS function key, excluding F11/F12 controls."""
    match = re.fullmatch(r"f\s*-?\s*(10|[1-9])", _normalise(transcript))
    return int(match.group(1)) if match else None


def function_key_item(
    items: tuple[MenuItem, ...],
    current_path: tuple[str, ...],
    slot: int,
) -> MenuItem | None:
    """Resolve one exact numbered choice on the currently displayed menu."""
    candidates = tuple(
        item
        for item in items
        if item.slot == slot
        and len(item.path) == len(current_path) + 1
        and item.path[: len(current_path)] == current_path
    )
    return candidates[0] if len(candidates) == 1 else None


def visible_menu_items(
    items: tuple[MenuItem, ...], current_path: tuple[str, ...]
) -> tuple[MenuItem, ...]:
    return tuple(
        item for item in items
        if len(item.path) == len(current_path) + 1
        and item.path[: len(current_path)] == current_path
    )


def resolve_guided_selection(
    items: tuple[MenuItem, ...], current_path: tuple[str, ...], transcript: str
) -> GuidedSelection:
    """Match one complete utterance to one immediate visible option."""
    choices = visible_menu_items(items, current_path)
    slot = parse_function_key(transcript)
    if slot is not None:
        target = function_key_item(items, current_path, slot)
        return GuidedSelection("found", target) if target else GuidedSelection("not_found")

    wanted = _compact(transcript)
    if not wanted:
        return GuidedSelection("not_found")
    exact = tuple(item for item in choices if _compact(item.label) == wanted)
    if len(exact) == 1:
        return GuidedSelection("found", exact[0])
    if len(exact) > 1:
        return GuidedSelection("ambiguous", choices=tuple(item.label for item in exact))

    ranked = sorted(
        (
            (SequenceMatcher(None, _normalise(transcript), _normalise(item.label)).ratio(), item)
            for item in choices
        ),
        key=lambda entry: (-entry[0], entry[1].action_id),
    )
    scores = tuple((item.label, round(score, 4)) for score, item in ranked[:5])
    if not ranked or ranked[0][0] < _MINIMUM_NODE_SCORE:
        return GuidedSelection("not_found", scores=scores)
    best = ranked[0][0]
    contenders = tuple(item for score, item in ranked if best - score < _MINIMUM_NODE_LEAD)
    if len(contenders) > 1:
        return GuidedSelection(
            "ambiguous", choices=tuple(item.label for item in contenders), scores=scores
        )
    return GuidedSelection("found", ranked[0][1], scores=scores)


def _menu_nodes(items: tuple[MenuItem, ...]) -> dict[tuple[str, ...], tuple[str, ...]]:
    children_by_path: dict[tuple[str, ...], list[str]] = {}
    for item in items:
        for depth in range(1, len(item.path)):
            path = item.path[:depth]
            child = item.path[depth]
            children = children_by_path.setdefault(path, [])
            if _normalise(child) not in {_normalise(value) for value in children}:
                children.append(child)
    return {path: tuple(children) for path, children in children_by_path.items()}


def _display_path(path: tuple[str, ...]) -> str:
    return " ".join(path)


def _resolve_node(
    nodes: dict[tuple[str, ...], tuple[str, ...]], requested_node: str
) -> tuple[str, tuple[str, ...] | None, tuple[str, ...]]:
    wanted = _compact(requested_node)

    if wanted in _F10_REQUESTS:
        matches = [
            path
            for path in nodes
            if len(path) == 1 and _compact(path[0]) in _F10_ROOT_LABELS
        ]
        if matches:
            return "found", matches[0], ()
        return "unavailable", None, ()

    full_matches = [path for path in nodes if _compact(_display_path(path)) == wanted]
    if len(full_matches) == 1:
        return "found", full_matches[0], ()
    if len(full_matches) > 1:
        choices = tuple(_display_path(path) for path in full_matches)
        return "ambiguous", None, choices

    label_matches = [path for path in nodes if _compact(path[-1]) == wanted]
    if len(label_matches) == 1:
        return "found", label_matches[0], ()
    if len(label_matches) > 1:
        choices = tuple(_display_path(path) for path in label_matches)
        return "ambiguous", None, choices

    if wanted in _KNOWN_ROOTS:
        return "unavailable", (_KNOWN_ROOTS[wanted],), ()

    ranked: list[tuple[float, tuple[str, ...]]] = []
    normalised_wanted = _normalise(requested_node)
    for path in nodes:
        scores = (
            SequenceMatcher(None, normalised_wanted, _normalise(_display_path(path))).ratio(),
            SequenceMatcher(None, normalised_wanted, _normalise(path[-1])).ratio(),
        )
        ranked.append((max(scores), path))
    ranked.sort(key=lambda candidate: candidate[0], reverse=True)
    if not ranked or ranked[0][0] < _MINIMUM_NODE_SCORE:
        return "not_found", None, ()

    best_score = ranked[0][0]
    contenders = [path for score, path in ranked if best_score - score < _MINIMUM_NODE_LEAD]
    if len(contenders) > 1:
        choices = tuple(_display_path(path) for path in contenders)
        return "ambiguous", None, choices
    return "found", ranked[0][1], ()


def list_node_children(
    items: tuple[MenuItem, ...], requested_node: str | None
) -> NodeListing:
    """Return immediate children of a live menu node reconstructed from flattened paths."""
    if requested_node is None:
        roots: list[str] = []
        seen: set[str] = set()
        for item in items:
            root = item.path[0]
            key = _normalise(root)
            if key not in seen:
                seen.add(key)
                roots.append(root)
        return NodeListing("found", None, tuple(roots))

    nodes = _menu_nodes(items)
    status, path, choices = _resolve_node(nodes, requested_node)
    if status == "found" and path is not None:
        return NodeListing("found", _display_path(path), nodes[path])
    if status == "unavailable":
        display = path[0] if path is not None else "F10"
        return NodeListing("unavailable", display)
    return NodeListing(status, requested_node, choices=choices)


def resolve_menu_navigation(
    items: tuple[MenuItem, ...],
    requested_node: str | None,
    *,
    current_path: tuple[str, ...] | None = None,
) -> MenuNavigation:
    """Resolve a visual destination without ever executing a leaf command."""
    if requested_node is None:
        return MenuNavigation("found", "menu.root")

    menu_items = tuple(item for item in items if not item.executable)
    wanted = _compact(requested_node)

    # "Show F<n>" is an absolute visual destination, not a selection of the
    # currently displayed menu.  Bare F1-F10 remains the relative guided
    # selection syntax handled by parse_function_key()/function_key_item().
    show_slot_match = re.fullmatch(r"f(10|[1-9])", wanted)
    if current_path is None and show_slot_match is not None:
        slot = int(show_slot_match.group(1))
        slot_matches = tuple(
            item for item in menu_items if len(item.path) == 1 and item.slot == slot
        )
        if len(slot_matches) == 1:
            item = slot_matches[0]
            return MenuNavigation("found", item.action_id, item.path)
        if len(slot_matches) > 1:
            return MenuNavigation(
                "ambiguous",
                choices=tuple(_display_path(item.path) for item in slot_matches),
            )

    f10_request = wanted in _F10_REQUESTS
    if current_path is not None:
        candidates = tuple(
            item
            for item in menu_items
            if len(item.path) == len(current_path) + 1
            and item.path[: len(current_path)] == current_path
        )
        if f10_request:
            candidates = tuple(
                item for item in candidates if _compact(item.path[-1]) in _F10_ROOT_LABELS
            )
    elif f10_request:
        candidates = tuple(
            item
            for item in menu_items
            if len(item.path) == 1 and _compact(item.path[0]) in _F10_ROOT_LABELS
        )
    elif wanted in _KNOWN_ROOTS:
        candidates = tuple(
            item
            for item in menu_items
            if len(item.path) == 1 and _compact(item.path[0]) == wanted
        )
    else:
        candidates = menu_items
    if f10_request:
        exact = candidates
    else:
        exact = tuple(
            item
            for item in candidates
            if wanted in {_compact(_display_path(item.path)), _compact(item.path[-1])}
        )
    if len(exact) == 1:
        return MenuNavigation("found", exact[0].action_id, exact[0].path)
    if len(exact) > 1:
        return MenuNavigation(
            "ambiguous",
            choices=tuple(_display_path(item.path) for item in exact),
        )

    # A request such as "Show Cover Me" names an executable leaf, but Show
    # must never execute it.  Open (or retain) the leaf's parent menu instead.
    # Do this before fuzzy submenu matching so "Rejoin Formation" cannot be
    # shortened into the unrelated Formation submenu.
    if current_path is not None:
        leaf_candidates = tuple(
            item
            for item in items
            if item.executable
            and len(item.path) == len(current_path) + 1
            and item.path[: len(current_path)] == current_path
            and wanted in {_compact(_display_path(item.path)), _compact(item.path[-1])}
        )
    else:
        full_leaf_matches = tuple(
            item
            for item in items
            if item.executable and _compact(_display_path(item.path)) == wanted
        )
        leaf_candidates = full_leaf_matches or tuple(
            item
            for item in items
            if item.executable and _compact(item.path[-1]) == wanted
        )
    if len(leaf_candidates) > 1:
        return MenuNavigation(
            "ambiguous",
            choices=tuple(_display_path(item.path) for item in leaf_candidates),
        )
    if len(leaf_candidates) == 1:
        parent_path = leaf_candidates[0].path[:-1]
        if current_path is not None:
            return MenuNavigation(
                "leaf",
                path=parent_path,
                choices=(_display_path(leaf_candidates[0].path),),
            )
        if not parent_path:
            return MenuNavigation("found", "menu.root")
        parent = next(
            (item for item in menu_items if item.path == parent_path),
            None,
        )
        if parent is not None:
            return MenuNavigation("found", parent.action_id, parent.path)

    if current_path is None and wanted in _KNOWN_ROOTS:
        return MenuNavigation("unavailable", path=(_KNOWN_ROOTS[wanted],))
    if current_path is None and wanted in _F10_REQUESTS:
        return MenuNavigation("unavailable", path=("F10",))

    normalised_wanted = _normalise(requested_node)
    ranked = [
        (
            max(
                SequenceMatcher(
                    None, normalised_wanted, _normalise(_display_path(item.path))
                ).ratio(),
                SequenceMatcher(None, normalised_wanted, _normalise(item.path[-1])).ratio(),
            ),
            item,
        )
        for item in candidates
    ]
    ranked.sort(key=lambda candidate: (-candidate[0], candidate[1].action_id))
    if not ranked or ranked[0][0] < _MINIMUM_NODE_SCORE:
        return MenuNavigation("not_found")

    best_score = ranked[0][0]
    contenders = tuple(
        item for score, item in ranked if best_score - score < _MINIMUM_NODE_LEAD
    )
    if len(contenders) > 1:
        return MenuNavigation(
            "ambiguous",
            choices=tuple(_display_path(item.path) for item in contenders),
        )
    return MenuNavigation("found", contenders[0].action_id, contenders[0].path)


def spoken_listing(listing: NodeListing) -> str:
    """Format a deliberately terse cockpit response."""
    if listing.status == "ambiguous":
        return "Which menu? " + ". ".join(listing.choices) + "."
    if listing.status == "not_found":
        return "I didn't recognise that menu."
    if listing.status == "unavailable" or not listing.children:
        return f"No {listing.node} commands are currently available."
    return ". ".join(listing.children) + "."
