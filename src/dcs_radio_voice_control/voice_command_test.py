"""Run DCS Radio Voice Control's live DCS voice-control application."""

from __future__ import annotations

import argparse
import math
import sys
import time
from typing import Sequence

from .alias_store import (
    record_pending_alias,
    record_pending_meta_alias,
    reviewed_alias,
    reviewed_meta_alias,
)
from .audio_cues import play_cue
from .command_reference import (
    MenuNavigation,
    function_key_item,
    list_node_children,
    parse_function_key,
    parse_meta_command,
    resolve_menu_navigation,
    spoken_listing,
)
from .controller_state import set_state as set_controller_state
from .configuration_store import load_document
from .dcs_client import ActionResult, DcsMenuClient
from .event_log import write_event
from .hotas import HotasButton, SdlHotasInput, resolve_binding
from .matcher import (
    MatchResult,
    RankedMatch,
    RecipientScope,
    build_vocabulary_prompt,
    match_catalogue,
    match_reviewed_alias,
    recipient_scope,
    strong_semantic_match,
)
from .matching_test import _print_result
from .microphone import WinMmAudioInput, _pcm16_level, load_selection, resolve_selection
from .protocol import MenuItem, MenuSnapshot
from .recording_test import (
    SAMPLE_RATE,
    SpaceOrHotasPushToTalk,
    SpacePushToTalk,
    WindowsKeys,
    capture_while_ptt,
)
from .stt import WhisperCpp
from .tts import InterruptingPushToTalk, PiperSpeech


MINIMUM_EXECUTION_SCORE = 0.70
MINIMUM_EXECUTION_LEAD = 0.10
MINIMUM_ALIAS_CANDIDATE_SCORE = 0.50
_SHORT_CAPTURE_ERROR = "No usable audio was captured;"


def action_alias_for_transcript(transcript: str) -> tuple[RecipientScope | None, str | None]:
    """Keep scoped recipient aliases on the ordinary scored matching path."""
    recipient = recipient_scope(transcript)
    if recipient is not None and recipient.alias is not None:
        return recipient, None
    return recipient, reviewed_alias(transcript)


def execution_candidate(
    result: MatchResult,
    *,
    minimum_score: float = MINIMUM_EXECUTION_SCORE,
    minimum_lead: float = MINIMUM_EXECUTION_LEAD,
) -> RankedMatch | None:
    if result.status != "matched" or result.best is None:
        return None
    if result.best.score < minimum_score:
        return None
    if result.best.exact:
        return result.best
    ranked = result.ranked or result.candidates
    if len(ranked) > 1 and result.best.score - ranked[1].score < minimum_lead:
        return None
    if not result.best.item.executable:
        return None
    return result.best


def remember_catalogue(
    known_items: dict[tuple[str, ...], MenuItem], items: tuple[MenuItem, ...]
) -> None:
    for item in items:
        if item.executable:
            known_items[item.path] = item


def executable_catalogue(items: tuple[MenuItem, ...]) -> tuple[MenuItem, ...]:
    return tuple(item for item in items if item.executable)


def contextual_catalogue(
    items: tuple[MenuItem, ...], visible_path: tuple[str, ...] | None
) -> tuple[MenuItem, ...]:
    executable = executable_catalogue(items)
    if visible_path is None:
        return executable
    return tuple(
        item
        for item in executable
        if len(item.path) == len(visible_path) + 1
        and item.path[: len(visible_path)] == visible_path
    )


def execution_match_for_context(
    transcript: str,
    items: tuple[MenuItem, ...],
    visible_path: tuple[str, ...] | None,
    action_alias: str | None,
    *,
    minimum_score: float = MINIMUM_EXECUTION_SCORE,
    minimum_lead: float = MINIMUM_EXECUTION_LEAD,
) -> tuple[MatchResult, RankedMatch | None, bool]:
    """Prefer a safe global direct command over guided-menu context.

    The displayed menu is only a fallback disambiguation context.  If the
    utterance already identifies an executable command in the full live
    catalogue, it remains a direct command even while guided mode is open.
    """
    live_actions = executable_catalogue(items)
    direct_match = (
        match_reviewed_alias(action_alias, live_actions)
        if action_alias is not None
        else match_catalogue(transcript, live_actions)
    )
    direct_candidate = execution_candidate(
        direct_match,
        minimum_score=minimum_score,
        minimum_lead=minimum_lead,
    )
    if direct_candidate is not None or visible_path is None:
        return direct_match, direct_candidate, direct_candidate is not None

    guided_actions = contextual_catalogue(items, visible_path)
    guided_match = (
        match_reviewed_alias(action_alias, guided_actions)
        if action_alias is not None
        else match_catalogue(transcript, guided_actions)
    )
    return (
        guided_match,
        execution_candidate(
            guided_match,
            minimum_score=minimum_score,
            minimum_lead=minimum_lead,
        ),
        False,
    )


def open_live_menu(
    client: DcsMenuClient,
    snapshot: MenuSnapshot,
    requested_node: str | None,
    *,
    current_path: tuple[str, ...] | None = None,
) -> tuple[MenuNavigation, MenuSnapshot, ActionResult | None]:
    """Resolve and open a menu, retrying only the same node after a stale revision."""
    navigation = resolve_menu_navigation(
        snapshot.items,
        requested_node,
        current_path=current_path,
    )
    if navigation.status != "found" or navigation.menu_id is None:
        return navigation, snapshot, None

    request_id = client.open_menu(navigation.menu_id, snapshot.revision)
    result = client.wait_for_result(request_id)
    if result is None or result.accepted or result.code != "stale_revision":
        return navigation, snapshot, result

    refreshed = client.request_menu_and_wait(timeout=2.0)
    if refreshed is None:
        return navigation, snapshot, result
    refreshed_navigation = resolve_menu_navigation(
        refreshed.items,
        requested_node,
        current_path=current_path,
    )
    if refreshed_navigation.status != "found" or refreshed_navigation.menu_id is None:
        return refreshed_navigation, refreshed, result
    request_id = client.open_menu(refreshed_navigation.menu_id, refreshed.revision)
    return refreshed_navigation, refreshed, client.wait_for_result(request_id)


def select_visible_item(
    client: DcsMenuClient,
    snapshot: MenuSnapshot,
    item: MenuItem,
) -> tuple[MenuSnapshot, ActionResult | None]:
    """Select one displayed item; never reinterpret it as an absolute path."""
    request_id = client.select_visible(item.action_id, snapshot.revision)
    result = client.wait_for_result(request_id)
    if result is None or result.accepted or result.code != "stale_revision":
        return snapshot, result

    refreshed = client.request_menu_and_wait(timeout=2.0)
    if refreshed is None:
        return snapshot, result
    same_item = next(
        (
            current
            for current in refreshed.items
            if current.path == item.path and current.executable == item.executable
        ),
        None,
    )
    if same_item is None:
        return refreshed, result
    request_id = client.select_visible(same_item.action_id, refreshed.revision)
    return refreshed, client.wait_for_result(request_id)


def control_live_menu(
    client: DcsMenuClient,
    snapshot: MenuSnapshot,
    operation: str,
) -> tuple[MenuSnapshot, ActionResult | None]:
    """Apply one DCS menu control, retrying only after a confirmed stale revision."""
    request_id = client.control_menu(operation, snapshot.revision)
    result = client.wait_for_result(request_id)
    if result is None or result.accepted or result.code != "stale_revision":
        return snapshot, result

    refreshed = client.request_menu_and_wait(timeout=2.0)
    if refreshed is None:
        return snapshot, result
    request_id = client.control_menu(operation, refreshed.revision)
    return refreshed, client.wait_for_result(request_id)


def visible_path_after_menu_control(
    visible_path: tuple[str, ...] | None,
    operation: str,
) -> tuple[str, ...] | None:
    if operation == "exit":
        return None
    if operation == "previous" and visible_path:
        return visible_path[:-1]
    return visible_path


def unavailable_candidate(
    transcript: str,
    live_items: tuple[MenuItem, ...],
    known_items: dict[tuple[str, ...], MenuItem],
    *,
    minimum_score: float = MINIMUM_EXECUTION_SCORE,
    minimum_lead: float = MINIMUM_EXECUTION_LEAD,
) -> RankedMatch | None:
    live_paths = {item.path for item in live_items}
    historical = tuple(known_items.values())
    result = match_catalogue(transcript, historical)
    candidate = execution_candidate(
        result,
        minimum_score=minimum_score,
        minimum_lead=minimum_lead,
    )
    if candidate is None or candidate.item.path in live_paths:
        return None
    return candidate


def wait_for_catalogue(client: DcsMenuClient) -> None:
    attempts = 0
    while client.request_menu_and_wait(timeout=2.0) is None:
        attempts += 1
        if attempts == 1:
            print("DCS is not responding yet. Start DCS and enter a mission; Ctrl+C stops DCS Radio Voice Control.")
        elif attempts % 5 == 0:
            print("Still waiting for an active DCS mission ...")
    if client.hook_status is None or not client.hook_status.compatible:
        raise OSError(
            "DCS loaded an older DCS Radio Voice Control hook. Close DCS completely, run DCS Radio Voice Control "
            "once to update it, then start DCS again."
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run voice control against the live DCS command catalogue"
    )
    parser.add_argument("--maximum-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    if args.maximum_seconds <= 0:
        parser.error("--maximum-seconds must be greater than zero")

    try:
        # Keep Whisper, Piper, the microphone, and SDL unloaded until DCS has
        # actually initialized the current DCS Radio Voice Control hook for a mission.
        print("Waiting for DCS and an active mission...", flush=True)
        with DcsMenuClient() as readiness_client:
            wait_for_catalogue(readiness_client)
        audio = WinMmAudioInput()
        settings = load_document()
        microphone = resolve_selection(audio.microphones(), load_selection())
        keys = WindowsKeys()
        stt_settings = settings["stt"]
        matching_settings = settings["matching"]
        ptt_settings = settings["ptt"]
        feedback_settings = settings["feedback"]
        output_settings = settings["audio"]
        minimum_score = float(matching_settings["minimum_score"])
        minimum_lead = float(matching_settings["minimum_lead"])
        cues_enabled = bool(feedback_settings["audio_cues"])
        cue_volume = float(feedback_settings["cue_volume"])
        recognizer = WhisperCpp(
            model_name=str(stt_settings["model"]),
            use_gpu=bool(stt_settings["use_gpu"]),
        )
        recognizer.start()
        speech = PiperSpeech(output_device=output_settings["output_device"])
        speech.validate()
        if ptt_settings["mode"] == "hotas":
            hotas_source = SdlHotasInput()
            binding = resolve_binding(hotas_source.devices(), ptt_settings)
            base_ptt = SpaceOrHotasPushToTalk(keys, HotasButton(hotas_source, binding))
        else:
            base_ptt = SpacePushToTalk(keys)
        ptt = InterruptingPushToTalk(base_ptt, speech)

        print("DCS Radio Voice Control voice control")
        print(f"Microphone: {microphone.name}")
        print(f"Push to talk: {ptt.label}")
        print(f"Execution gate: {minimum_score:.0%} match, {minimum_lead:.0%} lead")
        print("Piper speech output: ready")
        print("Waiting for the live DCS radio catalogue...", flush=True)
        write_event(
            "session_started",
            microphone=microphone.name,
            ptt=ptt.label,
            model=str(stt_settings["model"]),
            minimum_score=minimum_score,
            minimum_lead=minimum_lead,
            audio_cues=cues_enabled,
            cue_volume=cue_volume,
            piper_model=str(speech.model),
            output_device=output_settings["output_device"],
            whisper_compute="gpu" if recognizer.use_gpu else "cpu",
        )
        with DcsMenuClient() as client:
            wait_for_catalogue(client)
            try:
                set_controller_state("Ready", "DCS voice control is active.")
            except OSError:
                pass
            known_items: dict[tuple[str, ...], MenuItem] = {}
            visible_menu_path: tuple[str, ...] | None = None
            last_demand_key: tuple[str, str] | None = None
            while True:
                snapshot = client.snapshot
                assert snapshot is not None
                remember_catalogue(known_items, snapshot.items)
                print(f"\nCatalogue revision {snapshot.revision}: {len(snapshot.items)} commands")
                print(f"Hold {ptt.label} and speak. Release it to execute a safe match.")
                print("Press ESC while waiting to stop.\n")
                try:
                    pcm = capture_while_ptt(
                        audio, microphone, ptt, maximum_seconds=args.maximum_seconds
                    )
                except OSError as exc:
                    if not str(exc).startswith(_SHORT_CAPTURE_ERROR):
                        raise
                    print(f"\nIgnored short PTT press: {exc}")
                    write_event(
                        "command_rejected",
                        reason="capture_too_short",
                        revision=snapshot.revision,
                        message=str(exc),
                    )
                    continue

                # A new PTT press is a new explicit pilot demand.
                last_demand_key = None
                print("Transcribing locally...", flush=True)
                started = time.monotonic()
                transcript = recognizer.transcribe(
                    pcm,
                    prompt=build_vocabulary_prompt(snapshot.items),
                )
                elapsed = time.monotonic() - started
                stt_metrics = recognizer.last_metrics
                duration = len(pcm) / (SAMPLE_RATE * 2)
                level = _pcm16_level(pcm)
                dbfs = 20 * math.log10(level) if level > 0 else None
                if not transcript:
                    print("\nNo speech was recognised. Nothing was sent to DCS.")
                    write_event(
                        "command_rejected",
                        reason="no_speech",
                        revision=snapshot.revision,
                        duration_seconds=round(duration, 3),
                        average_dbfs=round(dbfs, 2) if dbfs is not None else None,
                        transcription_seconds=round(elapsed, 3),
                        stt=stt_metrics,
                    )
                    if cues_enabled:
                        play_cue("rejected", volume=cue_volume, output=speech.output)
                    continue

                print(f"\nHeard: {transcript}")
                print(f"Transcription time: {elapsed:.2f} seconds")
                write_event(
                    "transcription_completed", transcript=transcript,
                    duration_seconds=round(duration, 3),
                    average_dbfs=round(dbfs, 2) if dbfs is not None else None,
                    transcription_seconds=round(elapsed, 3), stt=stt_metrics,
                )

                # The menu can change while the pilot is speaking.  Refresh
                # immediately before interpretation instead of matching a
                # state captured before PTT was pressed.
                latest = client.request_menu_and_wait(timeout=0.5)
                if latest is not None:
                    snapshot = latest
                    remember_catalogue(known_items, snapshot.items)
                    if visible_menu_path and not any(
                        not item.executable and item.path == visible_menu_path
                        for item in snapshot.items
                    ):
                        visible_menu_path = None

                meta_alias = reviewed_meta_alias(transcript)
                meta = parse_meta_command(meta_alias or transcript)
                if meta_alias is not None:
                    write_event(
                        "alias_applied",
                        kind="meta",
                        transcript=transcript,
                        target=meta_alias,
                        revision=snapshot.revision,
                    )
                if meta is not None:
                    if meta.kind == "repeat":
                        if speech.repeat():
                            response = speech.last_text
                            print(f"DCS Radio Voice Control: {response}")
                            write_event(
                                "meta_command",
                                command="repeat",
                                transcript=transcript,
                                response=response,
                                revision=snapshot.revision,
                            )
                        else:
                            print("Nothing spoken to repeat.")
                            write_event(
                                "meta_command",
                                command="repeat",
                                transcript=transcript,
                                reason="nothing_to_repeat",
                                revision=snapshot.revision,
                            )
                        continue

                    if meta.kind in {"previous_menu", "exit_menu"}:
                        operation = "previous" if meta.kind == "previous_menu" else "exit"
                        source_path = " > ".join(visible_menu_path or ())
                        demand_key = ("menu_control", f"{operation}:{source_path}")
                        snapshot, result = control_live_menu(client, snapshot, operation)
                        remember_catalogue(known_items, snapshot.items)
                        if result is not None and result.accepted:
                            visible_menu_path = visible_path_after_menu_control(
                                visible_menu_path,
                                operation,
                            )
                            last_demand_key = demand_key
                            detail = (
                                "DCS opened the previous menu."
                                if operation == "previous"
                                else "DCS closed the radio menu."
                            )
                            print(detail)
                            write_event(
                                "menu_control",
                                transcript=transcript,
                                operation=operation,
                                accepted=True,
                                revision=snapshot.revision,
                            )
                        else:
                            reason = result.code if result is not None else "timeout"
                            detail = (
                                f"DCS rejected the menu control: {reason}."
                                if result is not None
                                else "DCS did not acknowledge the menu control."
                            )
                            print(detail)
                            write_event(
                                "menu_control",
                                transcript=transcript,
                                operation=operation,
                                accepted=False,
                                reason=reason,
                                revision=snapshot.revision,
                            )
                        continue

                    if meta.kind == "show":
                        if visible_menu_path is None:
                            navigation, snapshot, result = open_live_menu(
                                client,
                                snapshot,
                                meta.node,
                            )
                        else:
                            if meta.node is None:
                                navigation = MenuNavigation(
                                    "found",
                                    "menu.root" if not visible_menu_path else None,
                                    visible_menu_path,
                                )
                                result = ActionResult(
                                    "local",
                                    True,
                                    "menu_already_visible",
                                    "A guided menu is already visible",
                                )
                            else:
                                navigation = resolve_menu_navigation(
                                    snapshot.items,
                                    meta.node,
                                    current_path=visible_menu_path,
                                )
                                result = None
                                if navigation.status == "leaf":
                                    result = ActionResult(
                                        "local",
                                        True,
                                        "command_visible",
                                        "The requested command is on the displayed menu",
                                    )
                            if (
                                meta.node is not None
                                and navigation.status == "found"
                                and navigation.menu_id is not None
                                and navigation.path != visible_menu_path
                            ):
                                target = next(
                                    (
                                        item
                                        for item in snapshot.items
                                        if item.action_id == navigation.menu_id
                                    ),
                                    None,
                                )
                                if target is not None:
                                    snapshot, result = select_visible_item(
                                        client,
                                        snapshot,
                                        target,
                                    )
                            elif (
                                meta.node is not None
                                and navigation.status == "found"
                                and navigation.path == visible_menu_path
                            ):
                                result = ActionResult(
                                    "local",
                                    True,
                                    "menu_already_visible",
                                    "The requested command is already shown",
                                )
                        remember_catalogue(known_items, snapshot.items)
                        if result is not None and result.accepted:
                            visible_menu_path = navigation.path
                            last_demand_key = (
                                "menu",
                                " > ".join(navigation.path),
                            )
                            shown = " > ".join(navigation.path) or "radio"
                            if result.code == "command_visible":
                                command = navigation.choices[0]
                                print(f"{command} is displayed.")
                                write_event(
                                    "menu_command_visible",
                                    transcript=transcript,
                                    command=command,
                                    visible_path=list(navigation.path),
                                    revision=snapshot.revision,
                                )
                            else:
                                print(f"DCS opened the {shown} menu.")
                                write_event(
                                    "menu_shown",
                                    transcript=transcript,
                                    node=shown,
                                    menu_id=navigation.menu_id,
                                    revision=snapshot.revision,
                                )
                        else:
                            if navigation.status == "ambiguous":
                                detail = "Which menu: " + ", ".join(navigation.choices)
                                reason = "ambiguous"
                            elif navigation.status == "unavailable":
                                detail = "That menu is not currently available"
                                reason = "not_currently_available"
                            elif navigation.status == "not_found":
                                detail = "That menu was not recognised"
                                reason = "no_match"
                            elif result is None:
                                detail = "DCS did not acknowledge the menu request"
                                reason = "timeout"
                            else:
                                detail = f"DCS rejected the menu request: {result.code}"
                                reason = result.code
                            print(detail + ".")
                            write_event(
                                "menu_show_rejected",
                                transcript=transcript,
                                reason=reason,
                                choices=list(navigation.choices),
                                revision=snapshot.revision,
                            )
                        continue

                    listing = list_node_children(snapshot.items, meta.node)
                    response = spoken_listing(listing)
                    print(f"DCS Radio Voice Control: {response}")
                    speech.speak(response)
                    meta_alias_recorded = bool(
                        listing.status == "not_found" and record_pending_meta_alias(transcript)
                    )
                    write_event(
                        "meta_command",
                        command="list_commands",
                        transcript=transcript,
                        node=meta.node,
                        resolved_node=listing.node if listing.status == "found" else None,
                        children=list(listing.children),
                        choices=list(listing.choices),
                        candidate_meta_alias_recorded=meta_alias_recorded,
                        response=response,
                        revision=snapshot.revision,
                    )
                    continue

                function_key = parse_function_key(transcript)
                if function_key is not None:
                    if visible_menu_path is None:
                        print("No guided menu is displayed. Say Show Menu first.")
                        write_event(
                            "function_key_rejected",
                            transcript=transcript,
                            function_key=function_key,
                            reason="guided_menu_not_active",
                            revision=snapshot.revision,
                        )
                        if cues_enabled:
                            play_cue("rejected", volume=cue_volume, output=speech.output)
                        continue
                    target = function_key_item(
                        snapshot.items,
                        visible_menu_path,
                        function_key,
                    )
                    if target is None:
                        print(f"F{function_key} is not an option on the displayed menu.")
                        write_event(
                            "function_key_rejected",
                            transcript=transcript,
                            function_key=function_key,
                            reason="not_on_displayed_menu",
                            visible_path=list(visible_menu_path),
                            revision=snapshot.revision,
                        )
                        if cues_enabled:
                            play_cue("rejected", volume=cue_volume, output=speech.output)
                        continue
                    snapshot, selection_result = select_visible_item(client, snapshot, target)
                    if selection_result is None or not selection_result.accepted:
                        reason = (
                            selection_result.code
                            if selection_result is not None
                            else "timeout"
                        )
                        print(f"DCS could not select F{function_key}: {reason}.")
                        write_event(
                            "function_key_rejected",
                            transcript=transcript,
                            function_key=function_key,
                            reason=reason,
                            item=" > ".join(target.path),
                            revision=snapshot.revision,
                        )
                        if cues_enabled:
                            play_cue("rejected", volume=cue_volume, output=speech.output)
                        continue
                    last_demand_key = (
                        "action" if target.executable else "menu",
                        target.action_id if target.executable else " > ".join(target.path),
                    )
                    print(f"DCS selected F{function_key}: {' > '.join(target.path)}.")
                    write_event(
                        "function_key_selected",
                        transcript=transcript,
                        function_key=function_key,
                        item=" > ".join(target.path),
                        item_id=target.action_id,
                        executable=target.executable,
                        revision=snapshot.revision,
                    )
                    if target.executable:
                        visible_menu_path = None
                        if cues_enabled:
                            play_cue("accepted", volume=cue_volume, output=speech.output)
                        wait_for_catalogue(client)
                        if client.snapshot is not None:
                            remember_catalogue(known_items, client.snapshot.items)
                    else:
                        visible_menu_path = target.path
                    continue

                recipient, action_alias = action_alias_for_transcript(transcript)
                if recipient is not None and recipient.alias is not None:
                    write_event(
                        "recipient_scope_applied", transcript=transcript,
                        alias=recipient.alias, scope=recipient.scope,
                        command=recipient.command, revision=snapshot.revision,
                    )
                if action_alias is not None:
                    write_event(
                        "alias_applied",
                        kind="action",
                        transcript=transcript,
                        target=action_alias,
                        revision=snapshot.revision,
                    )

                match, candidate, direct_execution = execution_match_for_context(
                    transcript,
                    snapshot.items,
                    visible_menu_path,
                    action_alias,
                    minimum_score=minimum_score,
                    minimum_lead=minimum_lead,
                )

                if (
                    visible_menu_path is not None
                    and not direct_execution
                    and action_alias is None
                ):
                    navigation = resolve_menu_navigation(
                        snapshot.items,
                        transcript,
                        current_path=visible_menu_path,
                    )
                    if navigation.status == "found" and navigation.menu_id is not None:
                        target = next(
                            (
                                item
                                for item in snapshot.items
                                if item.action_id == navigation.menu_id
                            ),
                            None,
                        )
                        navigation_result = None
                        if target is not None:
                            snapshot, navigation_result = select_visible_item(
                                client,
                                snapshot,
                                target,
                            )
                        if navigation_result is not None and navigation_result.accepted:
                            visible_menu_path = navigation.path
                            last_demand_key = ("menu", " > ".join(navigation.path))
                            shown = " > ".join(navigation.path)
                            print(f"DCS opened the {shown} menu.")
                            write_event(
                                "menu_navigated",
                                transcript=transcript,
                                node=shown,
                                menu_id=navigation.menu_id,
                                revision=snapshot.revision,
                            )
                        else:
                            reason = (
                                navigation_result.code
                                if navigation_result is not None
                                else "timeout"
                            )
                            print("DCS could not open that submenu.")
                            write_event(
                                "menu_show_rejected",
                                transcript=transcript,
                                reason=reason,
                                revision=snapshot.revision,
                            )
                        continue

                live_actions = executable_catalogue(snapshot.items)
                match_transcript = action_alias or transcript
                ranked = [
                    {
                        "action_id": ranked_match.item.action_id,
                        "path": list(ranked_match.item.path),
                        "score": round(ranked_match.score, 4),
                    }
                    for ranked_match in match.ranked[:5]
                ]
                if candidate is None:
                    if visible_menu_path is not None:
                        print("That is not an option on the displayed menu.")
                        write_event(
                            "command_rejected",
                            reason="not_on_displayed_menu",
                            transcript=transcript,
                            visible_path=list(visible_menu_path),
                            revision=snapshot.revision,
                            candidates=ranked,
                            duration_seconds=round(duration, 3),
                            average_dbfs=round(dbfs, 2) if dbfs is not None else None,
                            transcription_seconds=round(elapsed, 3),
                            stt=stt_metrics,
                        )
                        if cues_enabled:
                            play_cue("rejected", volume=cue_volume, output=speech.output)
                        continue
                    unavailable = unavailable_candidate(
                        match_transcript,
                        live_actions,
                        known_items,
                        minimum_score=minimum_score,
                        minimum_lead=minimum_lead,
                    )
                    if unavailable is not None:
                        response = f"{unavailable.item.label} is not currently available."
                        print(f"DCS Radio Voice Control: {response}")
                        speech.speak(response)
                        write_event(
                            "command_rejected",
                            reason="not_currently_available",
                            transcript=transcript,
                            intended_action=" > ".join(unavailable.item.path),
                            revision=snapshot.revision,
                            candidates=ranked,
                            duration_seconds=round(duration, 3),
                            average_dbfs=round(dbfs, 2) if dbfs is not None else None,
                            transcription_seconds=round(elapsed, 3),
                            stt=stt_metrics,
                        )
                        continue

                    _print_result(match)
                    if match.status == "matched" and match.best is not None:
                        if match.best.score < minimum_score:
                            reason = "below_minimum_score"
                            print(f"Match is below the configured {minimum_score:.0%} score.")
                        elif len(match.ranked) > 1:
                            lead = match.best.score - match.ranked[1].score
                            reason = "insufficient_lead"
                            runner_up = match.ranked[1]
                            print(
                                f"Best match leads the runner-up by {lead:.0%}; "
                                f"configured minimum is {minimum_lead:.0%}."
                            )
                            print(
                                "Runner-up: "
                                + " > ".join(runner_up.item.path)
                                + f" ({runner_up.score:.0%})"
                            )
                        else:
                            reason = "not_executable"
                    else:
                        reason = match.status
                    alias_recorded = bool(
                        match.best is not None
                        and match.best.score >= MINIMUM_ALIAS_CANDIDATE_SCORE
                        and action_alias is None
                        and record_pending_alias(transcript)
                    )
                    print("Nothing was sent to DCS.")
                    write_event(
                        "command_rejected",
                        reason=reason,
                        transcript=transcript,
                        revision=snapshot.revision,
                        candidates=ranked,
                        candidate_alias_recorded=alias_recorded,
                        duration_seconds=round(duration, 3),
                        average_dbfs=round(dbfs, 2) if dbfs is not None else None,
                        transcription_seconds=round(elapsed, 3),
                        stt=stt_metrics,
                    )
                    if cues_enabled:
                        play_cue("rejected", volume=cue_volume, output=speech.output)
                    continue

                demand_key = ("action", candidate.item.action_id)
                if demand_key == last_demand_key:
                    print("Repeated command ignored.")
                    write_event(
                        "command_debounced",
                        transcript=transcript,
                        action=" > ".join(candidate.item.path),
                        action_id=candidate.item.action_id,
                        revision=snapshot.revision,
                    )
                    continue
                last_demand_key = demand_key
                guided_execution = visible_menu_path is not None and not direct_execution
                _print_result(match)
                write_event(
                    "command_sent",
                    transcript=transcript,
                    action=" > ".join(candidate.item.path),
                    action_id=candidate.item.action_id,
                    score=round(candidate.score, 4),
                    revision=snapshot.revision,
                    candidates=ranked,
                    duration_seconds=round(duration, 3),
                    average_dbfs=round(dbfs, 2) if dbfs is not None else None,
                    transcription_seconds=round(elapsed, 3),
                    stt=stt_metrics,
                )
                active_candidate = candidate
                active_revision = snapshot.revision
                if guided_execution:
                    snapshot, result = select_visible_item(
                        client,
                        snapshot,
                        active_candidate.item,
                    )
                    active_revision = snapshot.revision
                else:
                    request_id = client.execute(active_candidate.item.action_id, active_revision)
                    result = client.wait_for_result(request_id)

                if (
                    not guided_execution
                    and result is not None
                    and not result.accepted
                    and result.code == "stale_revision"
                ):
                    refreshed = client.request_menu_and_wait(timeout=2.0)
                    retry_candidate = None
                    if refreshed is not None:
                        remember_catalogue(known_items, refreshed.items)
                        retry_items = (
                            executable_catalogue(refreshed.items)
                            if direct_execution
                            else contextual_catalogue(refreshed.items, visible_menu_path)
                        )
                        retry_match = (
                            match_reviewed_alias(action_alias, retry_items)
                            if action_alias is not None
                            else match_catalogue(transcript, retry_items)
                        )
                        possible_retry = execution_candidate(
                            retry_match,
                            minimum_score=minimum_score,
                            minimum_lead=minimum_lead,
                        )
                        if (
                            possible_retry is not None
                            and (
                                possible_retry.item.path == candidate.item.path
                                or strong_semantic_match(transcript, possible_retry.item)
                            )
                        ):
                            retry_candidate = possible_retry

                    if retry_candidate is not None and refreshed is not None:
                        active_candidate = retry_candidate
                        active_revision = refreshed.revision
                        print(
                            "DCS menu changed; revalidated the same command against "
                            f"catalogue revision {active_revision}."
                        )
                        write_event(
                            "command_revalidated",
                            transcript=transcript,
                            action=" > ".join(active_candidate.item.path),
                            action_id=active_candidate.item.action_id,
                            previous_revision=snapshot.revision,
                            revision=active_revision,
                        )
                        request_id = client.execute(active_candidate.item.action_id, active_revision)
                        result = client.wait_for_result(request_id)
                    else:
                        print("DCS menu changed and the command could not be safely revalidated.")

                if result is None:
                    print("DCS did not acknowledge the command; execution state is unknown.")
                    write_event("dcs_result", reason="timeout", action_id=active_candidate.item.action_id)
                    if cues_enabled:
                        play_cue("rejected", volume=cue_volume, output=speech.output)
                    continue
                if not result.accepted:
                    print(f"DCS rejected the command: {result.code}: {result.detail}")
                    write_event(
                        "dcs_result",
                        reason=result.code,
                        message=result.detail,
                        action_id=active_candidate.item.action_id,
                        revision=active_revision,
                    )
                    if cues_enabled:
                        play_cue("rejected", volume=cue_volume, output=speech.output)
                    continue
                print("DCS accepted the voice command.")
                write_event(
                    "dcs_result",
                    action_id=active_candidate.item.action_id,
                    accepted=True,
                    revision=active_revision,
                )
                if cues_enabled:
                    play_cue("accepted", volume=cue_volume, output=speech.output)
                visible_menu_path = None
                wait_for_catalogue(client)
                if client.snapshot is not None:
                    remember_catalogue(known_items, client.snapshot.items)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except OSError as exc:
        if "older DCS Radio Voice Control hook" in str(exc):
            try:
                set_controller_state("Restart DCS", str(exc))
            except OSError:
                pass
        print(f"DCS Radio Voice Control voice control failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
