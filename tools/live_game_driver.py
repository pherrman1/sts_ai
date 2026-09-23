#!/usr/bin/env python3
"""Drive a live Slay the Spire run through MCPTheSpire.

The MCP server is the only game-control boundary. Silver supplies structured
combat actions and the native policy provider supplies structured OOC actions.
Only explicit UNSUPPORTED results may use the deterministic fallback.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import itertools
import json
import os
import math
import shlex
import subprocess
from collections import Counter, deque
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Mapping, Sequence

DEFAULT_MCP_URL = "http://127.0.0.1:8080/mcp"
DEFAULT_INSPECTOR = Path.home() / ".cache" / "sts-model-inspector" / "latest.json"
DEFAULT_TRACE_DIR = Path.home() / ".cache" / "sts-live-driver"
READ_TOOLS = {"get_screen_state", "get_available_commands"}
EXPECTED_TOOLS = READ_TOOLS | {
    "get_game_state", "get_card_info", "play_card", "end_turn", "use_potion",
    "discard_potion", "choose", "skip", "proceed", "cancel", "confirm",
    "select_cards", "start_game", "continue_game",
}
ACTION_TOOLS = EXPECTED_TOOLS - READ_TOOLS - {"get_game_state", "get_card_info"}
MAX_CANDIDATES = 128
SILVER_END_TURN_FINGERPRINT = "sa/t=5/s=0/c=0_0_0_0_0_0_0_0/o=0/p=0_-1/x=-1/d=0/k=0/task=0/sel="


class DriverError(RuntimeError):
    """A fail-closed driver error."""


class CandidateEnumerationError(DriverError):
    pass


class IntegrationFailure(DriverError):
    def __init__(self, reason: str, *, matches: Sequence[Any] = ()):
        super().__init__(reason)
        self.matches = list(matches)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_mapping(*values: Any) -> Mapping[str, Any]:
    for value in values:
        if isinstance(value, Mapping):
            return value
    return {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _text(value: Any) -> str:
    return str(value) if value is not None else ""


def _tool_names(commands: Any) -> list[str]:
    commands = _mapping(commands)
    raw = commands.get("available_tools", commands.get("tools", commands.get("commands", [])))
    names: list[str] = []
    for item in _list(raw):
        name = item if isinstance(item, str) else _mapping(item).get("tool", _mapping(item).get("name"))
        if name and str(name) not in names:
            names.append(str(name))
    return names


def _unwrap_mcp_result(result: Any) -> Any:
    if isinstance(result, Mapping):
        if result.get("isError") or result.get("is_error"):
            raise DriverError(str(result))
        for key in ("structuredContent", "structured_content", "data", "result"):
            if key in result and result[key] is not None:
                return result[key]
        return result
    if getattr(result, "isError", False) or getattr(result, "is_error", False):
        raise DriverError(str(result))
    for key in ("structuredContent", "structured_content"):
        value = getattr(result, key, None)
        if value is not None:
            return value
    content = getattr(result, "content", None)
    if content is not None:
        parts: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if text is None and isinstance(item, Mapping):
                text = item.get("text")
            if text is not None:
                parts.append(text)
        joined = "\n".join(parts)
        if joined:
            try:
                return json.loads(joined)
            except json.JSONDecodeError:
                return {"text": joined}
    return result


def _exception_text(error: BaseException) -> str:
    nested_errors = getattr(error, "exceptions", None)
    if nested_errors is not None:
        nested = "; ".join(_exception_text(item) for item in nested_errors)
        return nested or error.__class__.__name__
    return str(error) or error.__class__.__name__


def _compact(value: Any, limit: int = 12000) -> Any:
    if isinstance(value, Mapping):
        result = {str(k): _compact(v, limit) for k, v in value.items()}
    elif isinstance(value, list):
        result = [_compact(v, limit) for v in value]
    else:
        return value
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), default=str)
    if len(encoded) <= limit:
        return result
    return {"truncated": True, "sha256": hashlib.sha256(encoded.encode()).hexdigest(), "bytes": len(encoded)}


def _without_readiness(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _without_readiness(item) for key, item in value.items()
                if key not in {"ready_for_command", "readyForCommand"}}
    if isinstance(value, list):
        return [_without_readiness(item) for item in value]
    return value


def state_identity(state: Mapping[str, Any]) -> str:
    """Return state identity while ignoring only ephemeral command readiness."""
    explicit = {key: state[key] for key in ("session", "sequence", "observationHash") if key in state}
    if len(explicit) == 3:
        return json.dumps(explicit, sort_keys=True, separators=(",", ":"))
    payload = _compact(_without_readiness(dict(state)), 50000)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _canonical_combat_piles(state: Mapping[str, Any]) -> dict[str, Any]:
    """Keep intrinsic pile stats stable across Soul.clearPowers animations.

    MCP emits positive derived stats and includes base_* only when different.
    Soul completion resets those cached display values in draw/discard piles.
    Canonicalize to the explicitly known positive base value, never drop the
    stat itself; changed base stats, costs, identity, ordering and hand values
    therefore remain observable. Ambiguous zero/absent values remain strict.
    """
    result = dict(state)
    for pile in ("draw_pile", "discard_pile"):
        if not isinstance(state.get(pile), list):
            continue
        cards = []
        for raw in state[pile]:
            if not isinstance(raw, Mapping):
                cards.append(raw)
                continue
            card = dict(raw)
            for stat in ("damage", "block", "magic_number"):
                base = "base_" + stat
                if (type(card.get(base)) is int and card[base] > 0
                        and type(card.get(stat)) is int and card[stat] > 0):
                    card[stat] = card.pop(base)
            cards.append(card)
        result[pile] = cards
    for key in ("combat_state", "combatState"):
        if isinstance(state.get(key), Mapping):
            result[key] = _canonical_combat_piles(state[key])
    return result


def transition_identity(screen: Mapping[str, Any], game_state: Mapping[str, Any] | None = None) -> str:
    """Hash decision state, excluding readiness and qualified pile display resets."""
    screen_state = dict(screen)
    game = normalize_game_state(game_state or {})
    if _is_combat(screen):
        screen_state = _canonical_combat_piles(screen_state)
        game = _canonical_combat_piles(game)
    payload = {"screen": _without_readiness(screen_state),
               "game_state": _without_readiness(game)}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _same_mcp_boundary(screen: Mapping[str, Any], game_state: Mapping[str, Any]) -> bool:
    """Reject snapshots split across a combat-to-reward or similar transition."""
    for key in ("screen_type", "room_phase"):
        screen_value = screen.get(key)
        game_value = game_state.get(key)
        if screen_value is not None and game_value is not None and screen_value != game_value:
            return False
    return True


def _ready(value: Any) -> bool:
    data = _mapping(value)
    return data.get("ready_for_command", data.get("readyForCommand", True)) is True


def normalize_game_state(value: Any) -> dict[str, Any]:
    """Flatten nested MCP `game_state` and `combat_state` fields."""
    outer = dict(_mapping(value))
    nested = dict(_mapping(outer.get("game_state")))
    combat = dict(_mapping(nested.get("combat_state", nested.get("combatState"))))
    result = {key: item for key, item in outer.items() if key != "game_state"}
    result.update(nested)
    result.update(combat)
    return result


def _is_live_target(monster: Any) -> bool:
    monster = _mapping(monster)
    if monster.get("is_gone") or monster.get("isGone") or monster.get("gone"):
        return False
    if monster.get("half_dead") or monster.get("halfDead"):
        return False
    hp = monster.get("current_hp", monster.get("currentHp", monster.get("hp")))
    return hp is None or hp > 0


def _card_uuid(card: Mapping[str, Any]) -> str:
    return _text(card.get("uuid", card.get("unique_id", card.get("uniqueId", ""))))


def _card_name(card: Mapping[str, Any]) -> str:
    return _text(card.get("name", card.get("id", card.get("card_id", "card"))))


def _choice_label(choice: Any) -> str:
    if isinstance(choice, Mapping):
        return _text(choice.get("name", choice.get("label", choice.get("id", choice.get("text", choice)))))
    return _text(choice)


@dataclass(frozen=True)
class LegalAction:
    id: str
    human_description: str
    mcp_tool: str
    mcp_arguments: dict[str, Any]
    semantic: dict[str, Any] = field(default_factory=dict)
    silver_fingerprint: str | None = None

    def trace(self) -> dict[str, Any]:
        return {"id": self.id, "human_description": self.human_description,
                "mcp_tool": self.mcp_tool, "mcp_arguments": self.mcp_arguments,
                "semantic": self.semantic, "silver_fingerprint": self.silver_fingerprint}


def _append(actions: list[LegalAction], tool: str, args: dict[str, Any], description: str,
            semantic: dict[str, Any] | None = None, fingerprint: str | None = None) -> None:
    actions.append(LegalAction(f"a{len(actions)}", description, tool, args, semantic or {}, fingerprint))


def _selection_arguments(option: Any) -> dict[str, Any] | None:
    if not isinstance(option, Mapping):
        return None
    if isinstance(option.get("arguments"), Mapping):
        return dict(option["arguments"])
    for key in ("drop", "keep"):
        if key in option:
            return {key: list(option[key]) if isinstance(option[key], list) else option[key]}
    return None


def build_legal_actions(screen: Mapping[str, Any], commands: Mapping[str, Any] | Sequence[str],
                        game_state: Mapping[str, Any] | None = None, *,
                        max_candidates: int = MAX_CANDIDATES) -> list[LegalAction]:
    """Materialize concrete MCP calls from the advertised surface."""
    screen = dict(screen)
    game_state = normalize_game_state(game_state or {})
    names = _tool_names(commands) if isinstance(commands, Mapping) else list(commands)
    hand = _list(screen.get("hand", game_state.get("hand")))
    monsters = _list(screen.get("monsters", game_state.get("monsters")))
    targets = [index + 1 for index, monster in enumerate(monsters) if _is_live_target(monster)]
    potions = _list(screen.get("potions", game_state.get("potions")))
    choices = _list(screen.get("choice_list", screen.get("choices", screen.get("options", game_state.get("choices")))))
    actions: list[LegalAction] = []
    for tool in names:
        if tool == "play_card":
            for index, raw_card in enumerate(hand):
                card = _mapping(raw_card)
                if card.get("is_playable") is False or card.get("isPlayable") is False:
                    continue
                name, uuid = _card_name(card), _card_uuid(card)
                suffix = f" uuid={uuid}" if uuid else f" index={index + 1}"
                semantic = {"kind": "card", "card_uuid": uuid, "card_id": card.get("id"),
                            "card_index": index + 1, "silver_label": name}
                fingerprint = card.get("silver_fingerprint", card.get("semantic_fingerprint"))
                if card.get("has_target") or card.get("hasTarget"):
                    for target in targets:
                        _append(actions, tool, {"card_index": index + 1, "target_index": target},
                                f"Play {name}{suffix} -> monster {target}",
                                {**semantic, "target_index": target,
                                 "silver_label": f"{name} -> Monster {target}"},
                                _text(fingerprint) if fingerprint else None)
                else:
                    _append(actions, tool, {"card_index": index + 1}, f"Play {name}{suffix}", semantic,
                             _text(fingerprint) if fingerprint else None)
        elif tool == "end_turn":
            _append(actions, tool, {}, "End turn", {"kind": "end_turn", "silver_label": "End Turn"},
                    SILVER_END_TURN_FINGERPRINT)
        elif tool in {"use_potion", "discard_potion"}:
            for index, raw_potion in enumerate(potions):
                potion = _mapping(raw_potion)
                potion_id = _text(potion.get("id", potion.get("name", "Potion Slot")))
                if not potion_id or potion_id.lower() in {"potion slot", "empty", "none"}:
                    continue
                can_use = potion.get("can_use", potion.get("canUse")) is True
                can_discard = potion.get("can_discard", potion.get("canDiscard")) is True
                if tool == "use_potion" and not can_use:
                    continue
                if tool == "discard_potion" and not can_discard:
                    continue
                semantic = {"kind": "potion", "potion_id": potion_id,
                            "potion_slot": index + 1, "discard": tool == "discard_potion"}
                args = {"potion_slot": index + 1}
                requires_target = potion.get("requires_target", potion.get("requiresTarget", potion.get("has_target", False)))
                for target in (targets if requires_target else [None]):
                    target_args = {**args, **({"target_index": target} if target is not None else {})}
                    target_semantic = {**semantic, **({"target_index": target} if target is not None else {})}
                    suffix = f" -> monster {target}" if target is not None else ""
                    _append(actions, tool, target_args,
                            f"{tool.replace('_', ' ').title()} {potion_id} slot {index + 1}{suffix}", target_semantic)
        elif tool == "choose":
            for index, choice in enumerate(choices):
                _append(actions, tool, {"choice_index": index + 1},
                        f"Choose {index + 1}: {_choice_label(choice)}",
                        {"kind": "choice", "choice_index": index + 1, "choice": choice})
        elif tool in {"skip", "proceed", "cancel", "confirm", "continue_game"}:
            _append(actions, tool, {}, tool.replace("_", " ").title(), {"kind": tool})
        elif tool == "start_game":
            character = screen.get("character", screen.get("character_class", screen.get("characterClass")))
            if character is not None and _text(character):
                _append(actions, tool, {"character": character}, "Start game", {"kind": tool, "character": character})
        elif tool == "select_cards":
            options = screen.get("selection_options", screen.get("select_options", game_state.get("selection_options")))
            selection = _first_mapping(screen.get("selection"), game_state.get("selection"))
            selection_cards = _list(selection.get("cards", hand))
            def card_uuids(args: Mapping[str, Any]) -> list[str]:
                indexes = args.get("drop", args.get("keep", []))
                return [_card_uuid(_mapping(selection_cards[index - 1])) for index in indexes
                        if isinstance(index, int) and 0 < index <= len(selection_cards)]
            for option in _list(options):
                args = _selection_arguments(option)
                if args is not None:
                    _append(actions, tool, args, f"Select cards: {args}",
                             {"kind": "select_cards", **args, "card_uuids": card_uuids(args)})
            if not options:
                cards = selection_cards
                minimum = int(selection.get("min", selection.get("pick_count", selection.get("pickCount", 0))))
                maximum = min(int(selection.get("max", selection.get("pick_count", selection.get("pickCount", len(cards))))), len(cards))
                if maximum >= minimum:
                    for count in range(minimum, maximum + 1):
                        for indexes in itertools.combinations(range(1, len(cards) + 1), count):
                            _append(actions, tool, {"drop": list(indexes)}, f"Select cards to drop {list(indexes)}",
                                     {"kind": "select_cards", "drop": list(indexes),
                                      "card_uuids": card_uuids({"drop": list(indexes)})})
    if len(actions) > max_candidates:
        raise CandidateEnumerationError(f"legal action set has {len(actions)} candidates; configured limit is {max_candidates}")
    actionable = [name for name in names if name in ACTION_TOOLS]
    if actionable and not actions:
        raise CandidateEnumerationError(f"MCP advertises actionable tools {actionable} but no legal candidate was constructed")
    return actions


def forced_ooc_action(screen: Mapping[str, Any], candidates: Sequence[LegalAction]) -> LegalAction | None:
    """Take the only enumerated legal noncombat action without a model round trip."""
    if _is_combat(screen) or len(candidates) != 1:
        return None
    if _text(screen.get("screen_type", screen.get("screenType"))).upper() in {"MAIN_MENU", "GAME_OVER"}:
        return None
    candidate = candidates[0]
    if candidate.mcp_tool == "choose":
        choices = _list(screen.get("choice_list", screen.get("choices", screen.get("options"))))
        if len(choices) != 1 or candidate.mcp_arguments != {"choice_index": 1}:
            return None
    elif candidate.mcp_tool not in ACTION_TOOLS:
        return None
    return candidate


def _semantic_match(selected: Mapping[str, Any], action: LegalAction) -> bool:
    semantic = action.semantic
    selected_kind = selected.get("kind")
    if selected_kind and selected_kind != semantic.get("kind"):
        if not ((selected_kind == "card_select" and semantic.get("kind") == "select_cards")
                or (selected_kind == "choose" and semantic.get("kind") == "choice")):
            return False
    for selected_key, action_key in (("cardUuid", "card_uuid"), ("card_uuid", "card_uuid"),
                                     ("targetIndex", "target_index"),
                                     ("target_index", "target_index"), ("potionSlot", "potion_slot"),
                                     ("potion_slot", "potion_slot"), ("choiceIndex", "choice_index"),
                                     ("choice_index", "choice_index"), ("discard", "discard")):
        if selected_key in selected and selected[selected_key] != semantic.get(action_key):
            return False
    if "cardUuids" in selected:
        return selected["cardUuids"] == semantic.get("card_uuids")
    return bool(selected)


def map_silver_action(selected_live_action: Any, candidates: Sequence[LegalAction]) -> LegalAction:
    """Map Silver's structured live action to exactly one MCP candidate."""
    if not isinstance(selected_live_action, Mapping):
        raise IntegrationFailure("Silver response has no structured selectedLiveAction")
    matches = [candidate for candidate in candidates if _semantic_match(selected_live_action, candidate)]
    if (len(matches) > 1 and selected_live_action.get("kind") == "potion"
            and selected_live_action.get("discard") is False
            and "targetIndex" not in selected_live_action
            and "target_index" not in selected_live_action
            and all(candidate.mcp_tool == "use_potion"
                    and candidate.semantic.get("potion_id") in {"SmokeBomb", "Explosive Potion"}
                    and candidate.semantic.get("potion_slot") == selected_live_action.get("potionSlot")
                    and isinstance(candidate.semantic.get("target_index"), int)
                    for candidate in matches)):
        # Vanilla SmokeBomb.use overwrites the argument with the player;
        # ExplosivePotion.use damages every enemy without reading the argument.
        # MCP still requires a monster target for these thrown potions.
        return min(matches, key=lambda candidate: candidate.semantic["target_index"])
    if len(matches) != 1:
        raise IntegrationFailure(f"Silver action mapping expected exactly one candidate, got {len(matches)} for {selected_live_action!r}")
    return matches[0]


def map_ooc_action(selected: Any, candidates: Sequence[LegalAction]) -> LegalAction:
    """Resolve one structured provider hint; labels are never action identities."""
    if not isinstance(selected, Mapping):
        raise IntegrationFailure("OOC response has no structured selectedLiveAction")
    kind = selected.get("kind")
    allowed = {"choose": {"kind", "choiceIndex"}, "map": {"kind", "x", "y"},
               **{name: {"kind"} for name in ("skip", "proceed", "cancel", "confirm")}}
    if not isinstance(kind, str) or kind not in allowed or set(selected) != allowed[kind]:
        raise IntegrationFailure(f"malformed OOC selectedLiveAction: {selected!r}")
    if kind == "choose":
        index = selected["choiceIndex"]
        if type(index) is not int or index < 1:
            raise IntegrationFailure("OOC choiceIndex must be a positive integer")
        matches = [a for a in candidates if a.mcp_tool == "choose" and a.mcp_arguments == {"choice_index": index}]
    elif kind == "map":
        if any(type(selected[key]) is not int for key in ("x", "y")):
            raise IntegrationFailure("OOC map coordinates must be integers")
        matches = [a for a in candidates if a.mcp_tool == "choose"
                   and all(_mapping(a.semantic.get("choice")).get(key) == selected[key] for key in ("x", "y"))]
    else:
        matches = [a for a in candidates if a.mcp_tool == kind and not a.mcp_arguments]
    if len(matches) != 1:
        raise IntegrationFailure(f"OOC action mapping expected exactly one candidate, got {len(matches)} for {selected!r}",
                                 matches=[a.trace() for a in matches])
    return matches[0]


OOC_SCREENS = {
    "card_reward": {"CARD_REWARD"}, "combat_reward": {"COMBAT_REWARD"},
    "rest": {"REST", "CAMPFIRE", "NONE"}, "map": {"MAP"},
    "event": {"EVENT", "NONE"}, "neow": {"EVENT", "NONE", "NEOW"},
    "shop": {"SHOP", "SHOP_SCREEN"}, "shop_room": {"NONE", "SHOP", "SHOP_ROOM"}, "upgrade": {"GRID", "GRID_SELECT", "GRID_SELECT_SCREEN"},
    "remove": {"GRID", "GRID_SELECT", "GRID_SELECT_SCREEN"},
    "selector": {"GRID", "GRID_SELECT", "GRID_SELECT_SCREEN", "HAND_SELECT"},
    "treasure": {"TREASURE", "CHEST", "NONE"}, "boss_relic": {"BOSS_REWARD", "BOSS_RELIC"},
}


def validate_ooc_current(observation: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    ooc = _mapping(observation.get("ooc"))
    if observation.get("boundary") != "ooc" or type(ooc.get("schemaVersion")) is not int or ooc.get("schemaVersion") != 1:
        raise DriverError("inspector OOC observation has unsupported/malformed schema")
    screen = ooc.get("screen")
    current_screen = _text(state.get("screen_type", state.get("screenType"))).upper()
    if not isinstance(screen, str) or current_screen not in OOC_SCREENS.get(screen, {screen.upper() if isinstance(screen, str) else ""}):
        raise DriverError(f"inspector OOC screen mismatch: {screen!r} != {current_screen!r}")
    public = _mapping(ooc.get("publicState"))
    player = _mapping(state.get("player"))
    for key, aliases in {"act": ("act", "act_num"), "floor": ("floor", "floor_num"),
                         "hp": ("hp", "current_hp", "current_health"), "maxHp": ("maxHp", "max_hp", "max_health"),
                         "gold": ("gold",)}.items():
        for source in (state, player):
            found = next((source[name] for name in aliases if name in source), None)
            if found is not None:
                if key not in public or public[key] != found:
                    raise DriverError(f"inspector OOC {key} does not match MCP state")
                break
    live = ooc.get("liveChoices")
    if not isinstance(live, list) or any(not isinstance(choice, Mapping) for choice in live):
        raise DriverError("inspector OOC liveChoices is malformed")
    captured = ooc.get("mcpState")
    if not isinstance(captured, Mapping) or not captured:
        raise DriverError("inspector OOC has no MCP correlation snapshot")
    captured = normalize_game_state(captured)
    for key, expected in _without_readiness(captured).items():
        if key not in state or _without_readiness(state[key]) != expected:
            raise DriverError(f"inspector OOC MCP {key} does not match current state")
    if "choice_list" in state and captured.get("choice_list") != state["choice_list"]:
        raise DriverError("inspector OOC choices do not match MCP state")
    if not any(key in captured for key in ("screen_type", "screenType")):
        raise DriverError("inspector OOC MCP snapshot has no screen identity")


@dataclass(frozen=True)
class InspectorSnapshot:
    raw: Mapping[str, Any]
    session: str
    sequence: int
    observation_hash: str
    response: Mapping[str, Any]
    advisor: Mapping[str, Any]

    @classmethod
    def load(cls, path: Path) -> "InspectorSnapshot":
        try:
            raw = json.loads(path.read_text())
        except FileNotFoundError as error:
            raise DriverError(f"inspector snapshot is unavailable: {path}") from error
        except (OSError, json.JSONDecodeError) as error:
            raise DriverError(f"malformed inspector snapshot {path}: {error}") from error
        if not isinstance(raw, Mapping):
            raise DriverError(f"malformed inspector snapshot {path}: top level is not an object")
        response = _mapping(raw.get("response"))
        if response.get("ready") is not True:
            raise DriverError(f"inspector snapshot is not ready: {response.get('status', 'unknown')}")
        session, sequence, observation_hash = _text(raw.get("session")), raw.get("sequence"), _text(raw.get("observationHash"))
        if not session or type(sequence) is not int or sequence < 0 or not observation_hash:
            raise DriverError("inspector snapshot has incomplete observation identity")
        if (_text(response.get("session")) != session or response.get("sequence") != sequence
                or _text(response.get("observationHash")) != observation_hash):
            raise DriverError("inspector response identity does not match its observation")
        advisor = _mapping(response.get("advisor"))
        if not advisor:
            raise DriverError("inspector snapshot is ready but contains no advisor response")
        return cls(raw, session, sequence, observation_hash, response, advisor)

    def validate_current(self, state: Mapping[str, Any]) -> None:
        for key, expected in (("session", self.session), ("sequence", self.sequence), ("observationHash", self.observation_hash)):
            if key in state and state[key] != expected:
                raise DriverError(f"inspector {key} does not match MCP state: {state[key]!r} != {expected!r}")
        observation = _mapping(self.raw.get("observation"))
        if state.get("_expected_boundary") and observation.get("boundary") != state["_expected_boundary"]:
            raise DriverError("inspector observation boundary does not match the current decision")
        if observation.get("boundary") == "ooc" or (not _is_combat(state) and _text(state.get("screen_type")) not in {"", "NONE", "COMBAT"}):
            validate_ooc_current(observation, state)
            return
        if observation.get("boundary") not in (None, "combat"):
            raise DriverError(f"inspector observation boundary is not combat: {observation.get('boundary')!r}")
        screen_type = _text(state.get("screen_type", state.get("screenType", ""))).upper()
        phase = _text(state.get("room_phase", state.get("roomPhase", ""))).upper()
        if screen_type not in {"", "NONE", "COMBAT"} and phase != "COMBAT":
            raise DriverError(f"inspector combat observation does not correspond to screen {screen_type!r}")
        silver_root = _mapping(observation.get("silverRoot"))
        combat = _mapping(silver_root.get("combat", observation.get("combat")))
        raw_hand, current_hand = _list(combat.get("hand")), _list(state.get("hand"))
        compared = False
        if raw_hand and current_hand:
            raw_uuids = {_card_uuid(_mapping(card)) for card in raw_hand}
            current_uuids = {_card_uuid(_mapping(card)) for card in current_hand}
            if raw_uuids and current_uuids and raw_uuids != current_uuids:
                raise DriverError("inspector hand identity does not match MCP state")
            compared = bool(raw_uuids and current_uuids)
        raw_monsters, current_monsters = _list(combat.get("monsters")), _list(state.get("monsters"))
        if raw_monsters and current_monsters:
            def active(monster: Any) -> bool:
                item = _mapping(monster)
                hp = item.get("current_hp", item.get("curHp", item.get("hp")))
                return not (item.get("dead") or item.get("is_gone") or item.get("isGone")
                            or item.get("half_dead") or item.get("halfDead")
                            or (isinstance(hp, (int, float)) and hp <= 0))
            def monster_key(monster: Any) -> Any:
                item = _mapping(monster)
                return item.get("id", item.get("name"))
            raw_summary = sorted((monster_key(monster), _mapping(monster).get("hp", _mapping(monster).get("curHp")))
                                 for monster in raw_monsters if active(monster))
            current_summary = sorted((monster_key(monster), _mapping(monster).get("current_hp", _mapping(monster).get("curHp", _mapping(monster).get("hp"))))
                                    for monster in current_monsters if active(monster))
            comparable = all(key is not None for key, _ in raw_summary + current_summary)
            if comparable and raw_summary != current_summary:
                raise DriverError("inspector monster identity/state does not match MCP state")
            compared = comparable
        if not any(key in state for key in ("session", "sequence", "observationHash")) and not compared:
            raise DriverError("cannot correlate inspector observation with MCP-visible state")

    def reject_advisor_error(self) -> None:
        if (self.advisor.get("kind") == "error" or self.advisor.get("status") == "ERROR"
                or self.response.get("status") == "ERROR"):
            raise DriverError(f"advisor error {self.advisor.get('code', 'ERROR')}: "
                              f"{self.advisor.get('message', self.response.get('reason', 'unspecified'))}")

    def silver_evaluator(self) -> Mapping[str, Any]:
        self.reject_advisor_error()
        for evaluator in _list(self.advisor.get("evaluators")):
            if _mapping(evaluator).get("id") == "silver_player_decision_v2":
                return _mapping(evaluator)
        if self.advisor.get("silverStatus") is not None:
            return self.advisor
        raise DriverError("advisor response contains no silver_player_decision_v2 evaluator")


    def ooc_evaluator(self, policy: str) -> Mapping[str, Any]:
        self.reject_advisor_error()
        matches = [e for e in _list(self.advisor.get("evaluators"))
                   if isinstance(e, Mapping) and e.get("id") == "live_ooc_decision_v1"]
        if len(matches) != 1:
            raise DriverError(f"advisor must contain exactly one live_ooc_decision_v1 evaluator, got {len(matches)}")
        evaluator = matches[0]
        if evaluator.get("policy") != policy:
            raise DriverError(f"OOC evaluator policy mismatch: {evaluator.get('policy')!r} != {policy!r}")
        if not isinstance(evaluator.get("status"), str) or evaluator["status"] not in {"OK", "UNSUPPORTED"}:
            raise DriverError("malformed OOC evaluator status")
        if evaluator["status"] == "UNSUPPORTED" and not isinstance(evaluator.get("reason"), str):
            raise DriverError("OOC UNSUPPORTED evaluator requires a reason")
        if evaluator["status"] == "OK":
            if not isinstance(evaluator.get("selectedSemanticKey"), str) or not evaluator["selectedSemanticKey"]:
                raise DriverError("OOC OK evaluator has no selected semantic identity")
            summaries = evaluator.get("candidateSummaries")
            if not isinstance(summaries, list) or not summaries:
                raise DriverError("OOC OK evaluator has no candidate summaries")
            keys = []
            require_mcts_stats = policy == "mcts_ctm"
            total_visits = 0
            total_share = 0.0
            for candidate in summaries:
                if not isinstance(candidate, Mapping) or not isinstance(candidate.get("semanticKey"), str):
                    raise DriverError("malformed OOC candidate summary")
                q = candidate.get("q")
                if type(q) not in (int, float) or not math.isfinite(q):
                    raise DriverError("OOC candidate has a non-finite/missing score")
                visits = candidate.get("visits")
                share = candidate.get("visitShare")
                prior = candidate.get("prior")
                if require_mcts_stats and (type(visits) is not int or visits < 0 or type(share) not in (int, float) \
                        or not math.isfinite(share) or share < 0 \
                        or type(prior) not in (int, float) or not math.isfinite(prior) or prior < 0):
                    raise DriverError("OOC candidate has malformed MCTS statistics")
                if require_mcts_stats and share > 1.0 + 1e-9:
                    raise DriverError("OOC candidate visit share exceeds one")
                if require_mcts_stats:
                    total_visits += visits
                    total_share += float(share)
                keys.append(candidate["semanticKey"])
            if len(keys) != len(set(keys)) or keys.count(evaluator["selectedSemanticKey"]) != 1:
                raise DriverError("ambiguous/missing OOC selected semantic candidate")
            selected = summaries[keys.index(evaluator["selectedSemanticKey"])]
            if require_mcts_stats:
                max_visits = max(candidate["visits"] for candidate in summaries)
                if selected["visits"] != max_visits:
                    raise DriverError("OOC selected candidate is not the visit winner")
            # The native planner bypasses simulations for a qualified sole
            # legal root. It reports that one forced action with zero visits
            # and a full share; multi-action roots still require visits.
            sole_root_bypass = (require_mcts_stats and len(summaries) == 1 and total_visits == 0
                                and summaries[0]["visits"] == 0
                                and summaries[0]["prior"] == 1.0)
            if require_mcts_stats and ((total_visits <= 0 and not sole_root_bypass)
                                       or abs(total_share - 1.0) > 1e-6):
                raise DriverError("OOC MCTS root visits/shares do not form a complete root distribution")
            if selected.get("liveAction") != evaluator.get("selectedLiveAction"):
                raise DriverError("OOC selected action disagrees with candidate summary")
        return evaluator


class InspectorReader:
    # OOC MCTS may legitimately take tens of seconds; do not classify a
    # healthy unchanged screen as stale while the advisor is still working.
    # MCP transition/readiness timeouts are configured independently by the
    # live-game client and are intentionally not changed here.
    def __init__(self, path: Path, timeout: float = 120.0, poll_interval: float = 0.1):
        self.path, self.timeout, self.poll_interval = path, timeout, poll_interval

    async def read_for(self, state: Mapping[str, Any], previous: tuple[str, int] | None = None) -> InspectorSnapshot:
        deadline, last_error = time.monotonic() + self.timeout, None
        while time.monotonic() < deadline:
            try:
                snapshot = InspectorSnapshot.load(self.path)
                snapshot.validate_current(state)
                if previous and snapshot.session == previous[0] and snapshot.sequence <= previous[1]:
                    raise DriverError("inspector sequence did not advance after the prior action")
                return snapshot
            except DriverError as error:
                last_error = error
            await asyncio.sleep(self.poll_interval)
        raise DriverError(f"no fresh inspector response for current state: {last_error}")

    async def read_ooc_observation_for(self, state: Mapping[str, Any],
                                       previous: tuple[str, int] | None = None) -> tuple[str, int, Mapping[str, Any]]:
        """Read correlated public reward identities without waiting for scoring."""
        deadline, last_error = time.monotonic() + self.timeout, None
        while time.monotonic() < deadline:
            try:
                raw = json.loads(self.path.read_text())
                if not isinstance(raw, Mapping):
                    raise DriverError("inspector observation is malformed")
                session, sequence = raw.get("session"), raw.get("sequence")
                if not isinstance(session, str) or not session or type(sequence) is not int or sequence < 0:
                    raise DriverError("inspector observation has incomplete identity")
                if previous and session == previous[0] and sequence <= previous[1]:
                    raise DriverError("inspector observation sequence did not advance")
                observation = _mapping(raw.get("observation"))
                if observation.get("boundary") != "ooc":
                    raise DriverError("inspector observation is not OOC")
                validate_ooc_current(observation, state)
                return session, sequence, _mapping(observation.get("ooc"))
            except (OSError, ValueError, DriverError) as error:
                last_error = error
            await asyncio.sleep(self.poll_interval)
        raise DriverError(f"no fresh inspector OOC observation for current state: {last_error}")


class TraceWriter:
    def __init__(self, path: Path):
        self.path = path
        self.recent: deque[dict[str, Any]] = deque(maxlen=20)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        if isinstance(value, Mapping):
            return {str(key): ("[REDACTED]" if "api_key" in str(key).lower() or "secret" in str(key).lower()
                               else self._sanitize(item)) for key, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        return value

    def write(self, row: Mapping[str, Any]) -> None:
        self.recent.append(self._sanitize(dict(row)))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self._sanitize(dict(row)), sort_keys=True, default=str) + "\n")


    def write_failure(self, packet: Mapping[str, Any]) -> Path:
        path = Path(str(self.path) + ".failure.json")
        temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(self._sanitize(dict(packet)), handle, sort_keys=True, indent=2, default=str)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return path

    @property
    def run_report_path(self) -> Path:
        return self.path.with_suffix(".run.json")

    def write_run_report(self, summary: Mapping[str, Any], *, identity: Mapping[str, Any],
                         failure: Mapping[str, Any] | None = None) -> Path:
        """Write one readable, per-run decision and wait-time report."""
        decisions = []
        try:
            rows = (json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines())
            for row in rows:
                if not isinstance(row, Mapping) or row.get("record_type") == "summary":
                    continue
                source = _text(row.get("decision_source", "unknown"))
                if source == "silver":
                    kind = "Silver combat model"
                elif source == "ooc_v4":
                    kind = "OOC decision model"
                elif source in {"run_control", "game_over_navigation", "menu_inspection"}:
                    kind = "run control"
                else:
                    kind = "driver automation"
                durations = {
                    key.removesuffix("_micros"): round(value / 1000.0, 3)
                    for key, value in row.items()
                    if key.endswith("_micros") and isinstance(value, (int, float))
                    and math.isfinite(value) and value >= 0
                }
                wait_reasons = []
                if durations.get("inspector_wait", 0) > 0:
                    wait_reasons.append({
                        "phase": "model observation and decision",
                        "reason": "waiting for the inspector response; the response latency is recorded separately",
                        "milliseconds": durations["inspector_wait"],
                    })
                if durations.get("post_action_wait", 0) > 0:
                    wait_reasons.append({
                        "phase": "game transition",
                        "reason": "waiting for MCP readiness, command availability, and a changed correlated state",
                        "milliseconds": durations["post_action_wait"],
                    })
                if durations.get("mcp_action", 0) > 0:
                    wait_reasons.append({
                        "phase": "MCP action",
                        "reason": "waiting for the game-control action call to return",
                        "milliseconds": durations["mcp_action"],
                    })
                action = row.get("selected_mcp_tool") or row.get("executed_mcp_tool")
                args = row.get("selected_mcp_arguments") or row.get("executed_mcp_arguments") or {}
                automated_reasons = {
                    "parent_reward_cleanup": "collect an unconditional gold reward mechanically",
                    "card_reward_reveal": "reveal the concealed card group after visible parent rewards were resolved",
                    "neow_navigation": "advance the Neow screen after the model decision completed",
                    "shop_navigation": "enter or leave the shop through its mechanical navigation button",
                    "event_completion": "select the only Leave option after the event decision completed",
                    "dead_adventurer_fight": "start the encounter because Fight is the only active event option",
                    "nest_intro": "advance the Nest introduction to expose its actual reward decision",
                    "boss_door": "advance through the act boss door after combat has ended",
                    "selector_confirmation": "confirm the model-selected card operation",
                    "combat_selection_confirmation": "confirm the already selected combat card target",
                    "boss_chest_skip_cleanup": "close the boss chest after the model declined its relic",
                    "boss_chest_reveal": "open the boss chest to reveal its relic offer",
                    "declined_reward_cleanup": "clear rewards already declined by the model",
                    "empty_reward_proceed": "proceed because no reward choices remain",
                    "forced_ooc_action": "take the only legal noncombat action enumerated by the driver",
                    "stale_observation_retry": "discard a decision after the game state changed before action and request a fresh observation",
                }
                decision_reason = (row.get("fallback_reason") or row.get("unsupported_reason")
                                   or row.get("decision_error") or automated_reasons.get(source))
                if source == "silver":
                    decision_reason = "Silver selected the action from the current legal combat choices"
                elif source == "ooc_v4":
                    decision_reason = "OOC selected the action from the current public noncombat choices"
                selected_id = row.get("selected_candidate")
                description = next((candidate.get("human_description")
                                    for candidate in _list(row.get("legal_candidates"))
                                    if isinstance(candidate, Mapping) and candidate.get("id") == selected_id), None)
                decisions.append({
                    "step": row.get("step"),
                    "screen": row.get("screen_type"),
                    "decision_type": kind,
                    "decision_source": source,
                    "decision_reason": decision_reason,
                    "model_status": row.get("ooc_v4_status") or row.get("silver_status"),
                    "model_latency_ms": round(row.get("ooc_v4_latency_micros", row.get("silver_latency_micros", 0)) / 1000.0, 3),
                    "chosen_action": {"tool": action, "arguments": args,
                                      "description": description},
                    "elapsed_ms": round(row.get("driver_step_micros", 0) / 1000.0, 3),
                    "durations_ms": durations,
                    "wait_reasons": wait_reasons,
                })
        except (OSError, ValueError):
            decisions = []
        report = {
            "schema": "live_driver_run_report",
            "schemaVersion": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "driver": dict(identity),
            "summary": dict(summary),
            "decision_count": len(decisions),
            "decisions": decisions,
        }
        if failure is not None:
            report["failure"] = dict(failure)
        temporary = self.run_report_path.with_name(self.run_report_path.name + f".tmp-{os.getpid()}")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(self._sanitize(report), handle, sort_keys=True, indent=2, default=str)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.run_report_path)
        finally:
            temporary.unlink(missing_ok=True)
        return self.run_report_path


class McpGameClient:
    def __init__(self, session: Any):
        self.session = session
        self.tool_names: set[str] = set()

    async def initialize(self) -> set[str]:
        result = await self.session.list_tools()
        raw_tools = getattr(result, "tools", result.get("tools", []) if isinstance(result, Mapping) else [])
        self.tool_names = {str(getattr(tool, "name", _mapping(tool).get("name"))) for tool in raw_tools}
        self.tool_names.discard("None")
        missing = READ_TOOLS - self.tool_names
        if missing:
            raise DriverError(f"MCPTheSpire missing required read tools: {sorted(missing)}")
        if not self.tool_names & ACTION_TOOLS:
            raise DriverError("MCPTheSpire exposes no supported control tools")
        return self.tool_names

    async def call(self, tool: str, arguments: Mapping[str, Any] | None = None) -> Any:
        if tool not in self.tool_names:
            raise DriverError(f"MCP tool is not available: {tool}")
        try:
            result = await self.session.call_tool(tool, arguments=dict(arguments or {}))
        except Exception as error:
            raise DriverError(f"MCP call {tool} failed: {error}") from error
        return _unwrap_mcp_result(result)


@asynccontextmanager
async def connected_mcp(url: str) -> AsyncIterator[McpGameClient]:
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as error:
        raise DriverError("live-driver extra is missing the official mcp SDK") from error
    try:
        async with streamable_http_client(url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                client = McpGameClient(session)
                await client.initialize()
                yield client
    except DriverError:
        raise
    except Exception as error:
        raise DriverError(f"cannot connect to MCPTheSpire at {url}: {_exception_text(error)}") from error


def _is_combat(screen: Mapping[str, Any]) -> bool:
    phase = _text(screen.get("room_phase", screen.get("roomPhase", ""))).upper()
    screen_type = _text(screen.get("screen_type", screen.get("screenType", ""))).upper()
    return phase == "COMBAT" or (not phase and screen_type == "COMBAT")


def _has_uninitialized_combat_intent(screen: Mapping[str, Any], game: Mapping[str, Any] | None = None) -> bool:
    """DEBUG is AbstractMonster's construction sentinel, not a hidden intent."""
    if not _is_combat(screen):
        return False
    return any(_is_live_target(monster) and _mapping(monster).get("intent") == "DEBUG"
               for source in (screen, game or {}) for monster in _list(source.get("monsters")))


def _is_terminal(screen: Mapping[str, Any]) -> bool:
    text = " ".join(_text(screen.get(key, "")).upper() for key in
                     ("screen_type", "screenType", "room_phase", "roomPhase", "outcome", "run_state"))
    return any(marker in text for marker in ("VICTORY", "DEATH", "GAME_OVER", "GAME OVER", "RUN_COMPLETE"))


def choose_deterministic_action(screen: Mapping[str, Any], candidates: Sequence[LegalAction]) -> LegalAction:
    """Choose from materialized candidates using a stable screen-specific policy."""
    if not candidates:
        raise DriverError("deterministic policy cannot choose from an empty candidate set")
    screen_type = _text(screen.get("screen_type", screen.get("screenType", ""))).upper()
    phase = _text(screen.get("room_phase", screen.get("roomPhase", ""))).upper()
    if phase == "COMBAT" or screen_type in {"NONE", "COMBAT"}:
        for tool in ("play_card", "use_potion", "discard_potion", "end_turn"):
            match = next((candidate for candidate in candidates if candidate.mcp_tool == tool), None)
            if match:
                return match
    if screen_type == "COMBAT_REWARD":
        for tool in ("choose", "proceed"):
            match = next((candidate for candidate in candidates if candidate.mcp_tool == tool), None)
            if match:
                return match
    if "SHOP" in screen_type or phase == "SHOP":
        for tool in ("leave", "cancel", "proceed"):
            match = next((candidate for candidate in candidates if candidate.mcp_tool == tool), None)
            if match:
                return match
    for tool in ("choose", "select_cards", "confirm", "skip", "proceed", "continue_game", "start_game", "cancel"):
        match = next((candidate for candidate in candidates if candidate.mcp_tool == tool), None)
        if match:
            return match
    return candidates[0]


def card_reward_reveal_action(screen: Mapping[str, Any], game: Mapping[str, Any],
                              candidates: Sequence[LegalAction],
                              declined_indexes: set[int] | None = None) -> LegalAction | None:
    """Open a hidden card group without claiming any parent reward."""
    if _text(screen.get("screen_type", screen.get("screenType"))).upper() != "COMBAT_REWARD":
        return None
    occurrences = _list(_mapping(game.get("screen_state", {})).get("rewards"))
    if not occurrences:
        return None
    # A concealed card group may be opened mechanically only after OOC has
    # chosen among any remaining visible parent rewards.  Those choices can
    # conflict (notably Sapphire Key vs relic), so keep the card hidden until
    # the model has consumed the public parent surface.
    for index, reward in enumerate(occurrences):
        if index in (declined_indexes or set()):
            continue
        kind = _text(_mapping(reward).get("reward_type", _mapping(reward).get("type", ""))).upper()
        has_live_choice = any(candidate.mcp_tool == "choose"
                              and candidate.mcp_arguments == {"choice_index": index + 1}
                              for candidate in candidates)
        if kind in {"RELIC", "POTION", "EMERALD_KEY", "SAPPHIRE_KEY"} and has_live_choice:
            return None
    for index, reward in enumerate(occurrences):
        kind = _text(_mapping(reward).get("reward_type", _mapping(reward).get("type", ""))).upper()
        if kind == "CARD" and index not in (declined_indexes or set()):
            return next((candidate for candidate in candidates
                         if candidate.mcp_tool == "choose"
                         and candidate.mcp_arguments == {"choice_index": index + 1}), None)
    return None


def parent_reward_action(screen: Mapping[str, Any], game: Mapping[str, Any],
                         candidates: Sequence[LegalAction]) -> LegalAction | None:
    """Collect only unconditional gold before asking OOC about other rewards."""
    if _text(screen.get("screen_type", screen.get("screenType"))).upper() != "COMBAT_REWARD":
        return None
    occurrences = _list(_mapping(game.get("screen_state", {})).get("rewards"))
    if not occurrences:
        return None
    visible_types = {"GOLD", "STOLEN_GOLD"}
    for index, reward in enumerate(occurrences):
        kind = _text(_mapping(reward).get("reward_type", _mapping(reward).get("type", ""))).upper()
        if kind not in visible_types:
            continue
        match = next((candidate for candidate in candidates
                      if candidate.mcp_tool == "choose"
                      and candidate.mcp_arguments == {"choice_index": index + 1}), None)
        if match is not None:
            return match
    return None


def empty_combat_reward_proceed_action(screen: Mapping[str, Any], game: Mapping[str, Any],
                                       candidates: Sequence[LegalAction]) -> LegalAction | None:
    """Advance only an explicitly empty combat reward with one Proceed command."""
    if _text(screen.get("screen_type")).upper() != "COMBAT_REWARD" or len(candidates) != 1:
        return None
    rewards = _mapping(game.get("screen_state", screen.get("screen_state"))).get("rewards")
    if rewards != [] or candidates[0].mcp_tool != "proceed":
        return None
    return candidates[0]


def neow_navigation_action(screen: Mapping[str, Any], candidates: Sequence[LegalAction]) -> LegalAction | None:
    """Advance Neow's single Talk or Leave prompt around a model-selected bonus."""
    if (_text(screen.get("screen_type")).upper() != "EVENT"
            or _text(screen.get("room_type")) != "NeowRoom"
            or screen.get("floor") != 0
            or _text(_mapping(screen.get("screen_state")).get("event_id")) != "Neow Event"
            or _list(screen.get("choice_list")) not in (["[Talk]"], ["[Leave]"])
            or len(candidates) != 1):
        return None
    candidate = candidates[0]
    return candidate if candidate.mcp_tool == "choose" and candidate.mcp_arguments == {"choice_index": 1} else None


def shop_entry_action(screen: Mapping[str, Any], candidates: Sequence[LegalAction],
                      entered: bool = False) -> LegalAction | None:
    """Open the merchant inventory once, then advance after the model leaves it."""
    if (_text(screen.get("screen_type")).upper() != "SHOP_ROOM"
            or _text(screen.get("room_type")) != "ShopRoom"
            or _text(screen.get("room_phase")) != "COMPLETE"
            or _list(screen.get("choice_list")) != ["shop"]
            or len(candidates) != 2
            or {candidate.mcp_tool for candidate in candidates} != {"choose", "proceed"}):
        return None
    tool, arguments = ("proceed", {}) if entered else ("choose", {"choice_index": 1})
    return next((candidate for candidate in candidates
                 if candidate.mcp_tool == tool and candidate.mcp_arguments == arguments), None)


def event_completion_action(screen: Mapping[str, Any], candidates: Sequence[LegalAction]) -> LegalAction | None:
    """Dismiss an already resolved event's sole Leave button."""
    if (_text(screen.get("screen_type")).upper() != "EVENT"
            or _text(screen.get("room_type")) != "EventRoom"
            or _text(screen.get("room_phase")) not in {"EVENT", "COMPLETE"}
            or _list(screen.get("choice_list")) != ["[Leave]"]
            or len(candidates) != 1):
        return None
    candidate = candidates[0]
    return candidate if candidate.mcp_tool == "choose" and candidate.mcp_arguments == {"choice_index": 1} else None


def dead_adventurer_fight_action(screen: Mapping[str, Any], candidates: Sequence[LegalAction]) -> LegalAction | None:
    """Advance the sole Fight button after Dead Adventurer's modeled Search."""
    if (_text(screen.get("screen_type")).upper() != "EVENT"
            or _text(screen.get("room_type")) != "EventRoom"
            or _text(_mapping(screen.get("screen_state")).get("event_id")) != "Dead Adventurer"
            or _list(screen.get("choice_list")) != ["[Fight]"]
            or len(candidates) != 1):
        return None
    candidate = candidates[0]
    return candidate if candidate.mcp_tool == "choose" and candidate.mcp_arguments == {"choice_index": 1} else None


def nest_intro_action(screen: Mapping[str, Any], candidates: Sequence[LegalAction]) -> LegalAction | None:
    """Advance the Nest's introductory Continue before its first choice."""
    if (_text(screen.get("screen_type")).upper() != "EVENT"
            or _text(screen.get("room_type")) != "EventRoom"
            or _text(_mapping(screen.get("screen_state")).get("event_id")) != "Nest"
            or _list(screen.get("choice_list")) != ["[Continue]"]
            or len(candidates) != 1):
        return None
    candidate = candidates[0]
    return candidate if candidate.mcp_tool == "choose" and candidate.mcp_arguments == {"choice_index": 1} else None


def boss_door_action(screen: Mapping[str, Any], candidates: Sequence[LegalAction]) -> LegalAction | None:
    """Enter the boss when the map has exactly its sole Boss node."""
    if (_text(screen.get("screen_type")).upper() != "MAP"
            or screen.get("floor") not in (15, 32, 49)
            or _list(screen.get("choice_list")) != ["Boss!"]
            or len(candidates) not in (1, 2)
            or (len(candidates) == 2 and {c.mcp_tool for c in candidates} != {"choose", "cancel"})):
        return None
    candidate = candidates[0]
    return candidate if candidate.mcp_tool == "choose" and candidate.mcp_arguments == {"choice_index": 1} else None


def boss_chest_reveal_action(screen: Mapping[str, Any], candidates: Sequence[LegalAction]) -> LegalAction | None:
    """Open the boss chest so its relic offer becomes visible to OOC."""
    state = _mapping(screen.get("screen_state"))
    if (_text(screen.get("screen_type")).upper() != "CHEST"
            or _text(screen.get("room_type")) != "TreasureRoomBoss"
            or _text(state.get("chest_type")) != "BossChest"
            or state.get("chest_open") is not False
            or _list(screen.get("choice_list")) != ["open"]
            or len(candidates) != 2
            or {c.mcp_tool for c in candidates} != {"choose", "proceed"}):
        return None
    return next((c for c in candidates if c.mcp_tool == "choose"
                 and c.mcp_arguments == {"choice_index": 1}), None)


def boss_chest_skip_cleanup_action(screen: Mapping[str, Any],
                                   candidates: Sequence[LegalAction]) -> LegalAction | None:
    """Leave the chest after OOC explicitly selected no boss relic."""
    state = _mapping(screen.get("screen_state"))
    if (_text(screen.get("screen_type")).upper() != "CHEST"
            or _text(screen.get("room_type")) != "TreasureRoomBoss"
            or _text(state.get("chest_type")) != "BossChest"
            or _list(screen.get("choice_list")) != ["open"]):
        return None
    return next((c for c in candidates if c.mcp_tool == "proceed"
                 and c.mcp_arguments == {}), None)


def selector_confirmation_action(screen: Mapping[str, Any],
                                 candidates: Sequence[LegalAction]) -> LegalAction | None:
    """Confirm the single card already chosen by OOC on this grid."""
    state = _mapping(screen.get("screen_state"))
    if (_text(screen.get("screen_type")).upper() != "GRID"
            or state.get("confirm_up") is not True
            or state.get("num_cards") != 1
            or screen.get("can_proceed") is not True
            or _text(screen.get("proceed_button")) != "confirm"):
        return None
    return next((c for c in candidates if c.mcp_tool == "proceed"
                 and c.mcp_arguments == {}), None)


def combat_selection_confirmation_action(screen: Mapping[str, Any],
                                         candidates: Sequence[LegalAction]) -> LegalAction | None:
    """Confirm a completed hand selection when MCP exposes only Confirm."""
    state = _mapping(screen.get("screen_state"))
    selected = _list(state.get("selected"))
    maximum = state.get("max_cards")
    if (_text(screen.get("screen_type")).upper() != "HAND_SELECT"
            or not _is_combat(screen) or screen.get("can_proceed") is not True
            or _text(screen.get("proceed_button")) != "confirm"
            or type(maximum) is not int or maximum < 1
            or len(selected) != maximum or len(candidates) != 1):
        return None
    candidate = candidates[0]
    return candidate if candidate.mcp_tool == "proceed" and candidate.mcp_arguments == {} else None


def declined_reward_cleanup_action(occurrences: Sequence[Any], declined_indexes: set[int],
                                   candidates: Sequence[LegalAction]) -> LegalAction | None:
    """Claim free gold or leave once every remaining card group was model-declined."""
    if not occurrences or not declined_indexes:
        return None
    gold_indexes = []
    for item in occurrences:
        reward = _mapping(item)
        index = reward.get("index")
        kind = _text(reward.get("type")).upper()
        if type(index) is not int:
            return None
        if kind == "CARD" and index in declined_indexes:
            continue
        if kind in {"GOLD", "STOLEN_GOLD"}:
            gold_indexes.append(index)
            continue
        return None
    if gold_indexes:
        return next((candidate for candidate in candidates
                     if candidate.mcp_tool == "choose"
                     and candidate.mcp_arguments == {"choice_index": min(gold_indexes) + 1}), None)
    return next((candidate for candidate in candidates if candidate.mcp_tool == "proceed"
                 and candidate.mcp_arguments == {}), None)


def _latency_summary(values: Sequence[float]) -> dict[str, Any]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "max": None}
    def percentile(fraction: float) -> float:
        position = fraction * (len(ordered) - 1)
        lo, hi = math.floor(position), math.ceil(position)
        return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)
    return {"count": len(ordered), "mean": sum(ordered) / len(ordered),
            "p50": percentile(.5), "p95": percentile(.95), "max": ordered[-1]}


def _git_identity() -> dict[str, str]:
    result = {}
    for key, ref in (("head", "HEAD"), ("baseline", "origin/main")):
        try:
            proc = subprocess.run(["git", "rev-parse", ref], cwd=Path(__file__).resolve().parents[1],
                                  text=True, capture_output=True, timeout=2, check=False)
            if proc.returncode == 0:
                result[key] = proc.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return result


class Driver:
    def __init__(self, client: McpGameClient, inspector: InspectorReader, trace: TraceWriter, *,
                 dry_run: bool = False, strict_silver: bool = False, strict_ooc: bool = False,
                 ooc_policy: str = "mcts", max_steps: int | None = None,
                 new_run: bool = False, continue_run: bool = False, character: str | None = None,
                 ascension: int | None = None, seed: str | None = None,
                 poll_timeout: float = 8.0, poll_interval: float = 0.1,
                 startup_timeout: float = 45.0,
                 reproduction_command: str | None = None):
        self.client, self.inspector, self.trace = client, inspector, trace
        self.dry_run, self.strict_silver, self.max_steps = dry_run, strict_silver, max_steps
        self.strict_ooc, self.ooc_policy = strict_ooc, {"v4": "v4_q", "mcts": "mcts_ctm"}.get(ooc_policy, ooc_policy)
        self.new_run, self.continue_run, self.character = new_run, continue_run, character
        self.new_run_started = False
        self.ascension, self.seed = ascension, seed
        self.poll_timeout, self.poll_interval = poll_timeout, poll_interval
        self.startup_timeout = startup_timeout
        self.reproduction_command = reproduction_command or "uv run --extra live-driver python tools/live_game_driver.py --continue-run --run-until-error"
        self.previous_inspector: tuple[str, int] | None = None
        self.entered_shop_rooms: set[tuple[int, int]] = set()
        self.declined_rewards: set[tuple[str, str]] = set()
        self.boss_relic_skipped_rooms: set[tuple[int, int]] = set()
        self.pending_selector_confirmation: tuple[int, int, str] | None = None
        self.ooc_actions_seen: set[tuple[str, str, str]] = set()
        self.counters: Counter[str] = Counter({name: 0 for name in (
            "silver_ok", "silver_unsupported", "ooc_v4_ok", "ooc_v4_unsupported",
            "deterministic_fallback_combat", "deterministic_fallback_ooc", "mapping_failures")})
        self.unsupported: Counter[str] = Counter()
        self.latencies: dict[str, list[float]] = {"ooc_v4_micros": [], "ooc_scorer_micros": [], "driver_step_micros": []}
        self.started = time.monotonic()
        self.steps = 0
        self.stale_retries = 0
        self.outcome = "unknown"
        self.last_screen: Mapping[str, Any] = {}
        self.last_game: Mapping[str, Any] = {}
        self.context: dict[str, Any] = {}
        self.context_started_monotonic = self.started
        self.failure_path: Path | None = None
        self.identity = _git_identity()

    async def read_screen(self) -> Mapping[str, Any]:
        screen = await self.client.call("get_screen_state")
        if not isinstance(screen, Mapping):
            raise DriverError(f"MCP screen state is not an object: {screen!r}")
        return screen

    async def read_game_state(self) -> dict[str, Any]:
        if "get_game_state" not in self.client.tool_names:
            return {}
        value = await self.client.call("get_game_state")
        return normalize_game_state(value)

    async def read_ready_state(self) -> tuple[Mapping[str, Any], Any]:
        started, last = time.monotonic(), {}
        budget = self.poll_timeout
        deadline = started + budget
        while time.monotonic() < deadline:
            screen = await self.read_screen()
            last = screen
            self.last_screen = screen
            if self.steps == 0 and screen.get("in_game") is False:
                budget = max(self.poll_timeout, self.startup_timeout)
                deadline = started + budget
            if _is_terminal(screen):
                if (self.new_run and not self.new_run_started
                        and _text(screen.get("screen_type")).upper() == "GAME_OVER"
                        and _ready(screen)):
                    commands = await self.client.call("get_available_commands")
                    if _ready(commands):
                        return screen, commands
                return screen, {}
            if _ready(screen) and not _has_uninitialized_combat_intent(screen):
                commands = await self.client.call("get_available_commands")
                if _ready(commands):
                    return screen, commands
            await asyncio.sleep(self.poll_interval)
        raise DriverError(f"MCP state was not ready for a command within {budget:.1f}s: {last!r}")

    async def read_ready_snapshot(self) -> tuple[Mapping[str, Any], Any, dict[str, Any]]:
        deadline = time.monotonic() + self.poll_timeout
        while time.monotonic() < deadline:
            screen, commands = await self.read_ready_state()
            game = await self.read_game_state()
            self.last_game = game
            if (_same_mcp_boundary(screen, game)
                    and not _has_uninitialized_combat_intent(screen, game)):
                return screen, commands, game
            await asyncio.sleep(self.poll_interval)
        raise DriverError("MCP combat monster intent remained DEBUG before the decision boundary")

    async def wait_for_ready_advance(self, before: str, *,
                                     ignore_terminal: bool = False) -> tuple[Mapping[str, Any], dict[str, Any]]:
        deadline, last = time.monotonic() + self.poll_timeout, {}
        while time.monotonic() < deadline:
            screen = await self.read_screen()
            last = screen
            if _is_terminal(screen) and not ignore_terminal:
                return screen, await self.read_game_state()
            if _ready(screen):
                commands = await self.client.call("get_available_commands")
                game_state = await self.read_game_state()
                if (_ready(commands) and (not ignore_terminal or not _is_terminal(screen))
                        and _same_mcp_boundary(screen, game_state)
                        and not _has_uninitialized_combat_intent(screen, game_state)
                        and transition_identity(screen, game_state) != before):
                    return screen, game_state
            await asyncio.sleep(self.poll_interval)
        raise DriverError(f"post-action MCP state did not become ready and advance within {self.poll_timeout:.1f}s: {last!r}")

    def menu_action(self, screen: Mapping[str, Any], commands: Any) -> LegalAction | None:
        names = _tool_names(commands)
        if not ({"continue_game", "start_game"} & set(names)):
            if self.new_run and not self.new_run_started:
                raise DriverError("--new-run cannot replace a currently live run")
            return None
        if "continue_game" in names:
            if self.new_run:
                raise DriverError("--new-run refuses to replace an existing save; continue it first")
            return LegalAction("run-control", "Continue saved run", "continue_game", {}, {"kind": "continue_game"})
        if self.continue_run:
            raise DriverError("--continue-run requested but MCP advertises no saved run")
        if not (self.new_run or self.character):
            raise DriverError("main menu has no save; starting requires --new-run or --character")
        arguments: dict[str, Any] = {"character": self.character or "IRONCLAD"}
        if self.ascension is not None:
            arguments["ascension"] = self.ascension
        if self.seed is not None:
            arguments["seed"] = self.seed
        return LegalAction("run-control", "Start requested run", "start_game", arguments, {"kind": "start_game"})

    def fallback_action(self, screen: Mapping[str, Any], game: Mapping[str, Any],
                        candidates: Sequence[LegalAction], snapshot: InspectorSnapshot | None = None) -> tuple[LegalAction, tuple[int, int] | None]:
        if screen.get("screen_type") == "COMBAT_REWARD" and snapshot is not None:
            ooc = _mapping(_mapping(snapshot.raw.get("observation")).get("ooc"))
            occurrences = _list(ooc.get("rewardOccurrences"))
            declined_indexes = {item.get("index") + 1 for item in occurrences
                                if isinstance(item, Mapping) and type(item.get("index")) is int
                                and isinstance(item.get("identity"), str)
                                and (snapshot.session, item.get("identity")) in self.declined_rewards}
            candidates = [candidate for candidate in candidates
                          if not (candidate.mcp_tool == "choose"
                                  and candidate.mcp_arguments.get("choice_index") in declined_indexes)]
            # MCP can advertise a potion reward even when the inventory is
            # full, but the inspector deliberately omits that primitive
            # because this boundary has no discard command.  Only suppress
            # that specifically identified potion occurrence.  Unopened card
            # rewards are also absent from liveChoices by design, but remain
            # valid raw MCP fallback actions that open the hidden card group.
            live_choices = _list(ooc.get("liveChoices"))
            public = _mapping(ooc.get("publicState"))
            capacity = public.get("potionCapacity")
            potions = _list(public.get("potions"))
            occupied = sum(
                _text(_mapping(potion).get("id", potion)).lower()
                not in {"", "potion slot", "empty", "none"}
                for potion in potions)
            full_potions = type(capacity) is int and occupied >= capacity
            if full_potions and live_choices:
                live_choice_indexes = {
                    hint.get("choiceIndex")
                    for choice in live_choices
                    for hint in [_mapping(_mapping(choice).get("liveAction"))]
                    if hint.get("kind") == "choose" and type(hint.get("choiceIndex")) is int
                }
                absent_potions = {
                    item.get("index") + 1
                    for item in occurrences
                    if isinstance(item, Mapping)
                    and type(item.get("index")) is int
                    and _text(item.get("type")).upper() == "POTION"
                    and item.get("index") + 1 not in live_choice_indexes
                }
                candidates = [candidate for candidate in candidates
                              if not (candidate.mcp_tool == "choose"
                                      and candidate.mcp_arguments.get("choice_index") in absent_potions)]
            reward_order = ("GOLD", "STOLEN_GOLD", "RELIC", "POTION", "CARD")
            for reward_type in reward_order:
                for item in occurrences:
                    if _text(item.get("type")).upper() != reward_type:
                        continue
                    choice_index = item.get("index") + 1 if type(item.get("index")) is int else None
                    match = next((candidate for candidate in candidates
                                  if candidate.mcp_tool == "choose"
                                  and candidate.mcp_arguments.get("choice_index") == choice_index), None)
                    if match is not None:
                        return match, None
        if _text(screen.get("screen_type", screen.get("screenType"))).upper() != "SHOP_ROOM":
            return choose_deterministic_action(screen, candidates), None
        act, floor = game.get("act", screen.get("act")), screen.get("floor", game.get("floor"))
        if type(act) is not int or type(floor) is not int:
            raise DriverError("SHOP_ROOM navigation requires exact act/floor identity")
        room = (act, floor)
        entering = room not in self.entered_shop_rooms
        tool, arguments = ("choose", {"choice_index": 1}) if entering else ("proceed", {})
        matches = [candidate for candidate in candidates
                   if candidate.mcp_tool == tool and candidate.mcp_arguments == arguments]
        if len(matches) != 1 or (entering and sum(candidate.mcp_tool == "choose" for candidate in candidates) != 1):
            raise IntegrationFailure("SHOP_ROOM navigation does not match the single merchant entry/proceed surface")
        return matches[0], room if entering else None

    async def step(self, step: int) -> bool:
        started = time.monotonic()
        self.context_started_monotonic = started
        self.context = {"step": step, "timestamp": datetime.now(timezone.utc).isoformat()}
        row = self.context
        screen, commands, game_state = await self.read_ready_snapshot()
        self.last_screen, self.last_game = screen, game_state
        if _is_terminal(screen):
            if (self.new_run and not self.new_run_started
                    and _text(screen.get("screen_type")).upper() == "GAME_OVER"
                    and "proceed" in _tool_names(commands)):
                row.update({"decision_source": "game_over_navigation",
                            "screen_type": "GAME_OVER", "executed_mcp_tool": "proceed",
                            "executed_mcp_arguments": {}})
                row["mcp_result"] = await self.client.call("proceed", {})
                if (_mapping(row["mcp_result"]).get("success") is False
                        or _mapping(row["mcp_result"]).get("error")):
                    raise DriverError("MCP game-over Proceed failed")
                self.steps += 1
                post, post_game_state = await self.wait_for_ready_advance(
                    transition_identity(screen, game_state), ignore_terminal=True)
                row["post_action_state"] = _compact({"screen": post, "game_state": post_game_state})
                row["driver_step_micros"] = (time.monotonic() - started) * 1e6
                self.last_screen, self.last_game = post, post_game_state
                self.trace.write(row)
                return True
            self.outcome = _terminal_outcome(screen)
            return False
        if (self.dry_run and not (self.new_run or self.continue_run or self.character)
                and _text(screen.get("screen_type", screen.get("screenType"))).upper() == "MAIN_MENU"
                and "start_game" in _tool_names(commands) and "continue_game" not in _tool_names(commands)):
            # Launcher probes inspect an idle menu without selecting or starting
            # a run. The normal mutating path still requires explicit intent.
            self.outcome = "dry_run"
            row.update({"dry_run": True, "decision_source": "menu_inspection",
                        "screen_type": screen.get("screen_type", screen.get("screenType")),
                        "screen": screen, "available_commands": commands,
                        "state_identity": transition_identity(screen, game_state),
                        "legal_candidates": []})
            self.trace.write(row)
            return False
        action = self.menu_action(screen, commands)
        snapshot = None
        shop_entry_key = None
        candidates = [action] if action else build_legal_actions(screen, commands, game_state)
        if not candidates:
            raise DriverError("no legal candidates for a non-terminal screen")
        reveal_card = False
        parent_reward = False
        neow_navigation = False
        shop_entry = False
        event_completion = False
        dead_adventurer_fight = False
        nest_intro = False
        boss_door = False
        boss_chest_reveal = False
        boss_chest_skip_cleanup = False
        selector_confirmation = False
        combat_selection_confirmation = False
        declined_reward_cleanup = False
        empty_reward_proceed = False
        forced_ooc = False
        advisor_started = time.monotonic()
        declined_card_indexes: set[int] = set()
        reward_occurrences: list[Any] = []
        reward_observation: Mapping[str, Any] | None = None
        reward_observation_marker: tuple[str, int] | None = None
        if (action is None and self.declined_rewards
                and _text(screen.get("screen_type")).upper() == "COMBAT_REWARD"):
            inspector_state = {**game_state, **screen, "_expected_boundary": "ooc"}
            session, sequence, ooc = await self.inspector.read_ooc_observation_for(
                inspector_state, self.previous_inspector)
            reward_observation_marker = (session, sequence)
            row.update({"inspector_session": session, "inspector_sequence": sequence,
                        "inspector_observation_only": True})
            reward_observation = ooc
            reward_occurrences = _list(ooc.get("rewardOccurrences"))
            declined_card_indexes = {
                _mapping(item)["index"] for item in reward_occurrences
                if _text(_mapping(item).get("type")).upper() == "CARD"
                and type(_mapping(item).get("index")) is int
                and (session, _mapping(item).get("identity")) in self.declined_rewards}
        if action is None:
            action = combat_selection_confirmation_action(screen, candidates)
            combat_selection_confirmation = action is not None
        if action is None:
            parent = parent_reward_action(screen, game_state, candidates)
            if parent is not None:
                action = parent
                parent_reward = True
            else:
                reveal = card_reward_reveal_action(screen, game_state, candidates, declined_card_indexes)
                if reveal is not None:
                    action = reveal
                    reveal_card = True
                else:
                    action = neow_navigation_action(screen, candidates)
                    neow_navigation = action is not None
                    if action is None:
                        act, floor = game_state.get("act"), screen.get("floor")
                        room = (act, floor) if type(act) is int and type(floor) is int else None
                        action = shop_entry_action(screen, candidates,
                                                   entered=room in self.entered_shop_rooms)
                        shop_entry = action is not None
                        if shop_entry and action.mcp_tool == "choose" and room is not None:
                            shop_entry_key = room
                        if action is None:
                            action = event_completion_action(screen, candidates)
                            event_completion = action is not None
                        if action is None:
                            action = dead_adventurer_fight_action(screen, candidates)
                            dead_adventurer_fight = action is not None
                        if action is None:
                            action = nest_intro_action(screen, candidates)
                            nest_intro = action is not None
                        if action is None:
                            action = boss_door_action(screen, candidates)
                            boss_door = action is not None
                        if action is None:
                            act, floor = game_state.get("act"), screen.get("floor")
                            selector_key = (act, floor, _text(screen.get("room_type")))
                            if self.pending_selector_confirmation == selector_key:
                                action = selector_confirmation_action(screen, candidates)
                                selector_confirmation = action is not None
                            self.pending_selector_confirmation = None
                        if action is None:
                            act, floor = game_state.get("act"), screen.get("floor")
                            room = (act, floor) if type(act) is int and type(floor) is int else None
                            if room in self.boss_relic_skipped_rooms:
                                action = boss_chest_skip_cleanup_action(screen, candidates)
                                boss_chest_skip_cleanup = action is not None
                        if action is None:
                            action = boss_chest_reveal_action(screen, candidates)
                            boss_chest_reveal = action is not None
                        if action is None:
                            action = declined_reward_cleanup_action(
                                reward_occurrences, declined_card_indexes, candidates)
                            declined_reward_cleanup = action is not None
                        if action is None:
                            action = empty_combat_reward_proceed_action(screen, game_state, candidates)
                            empty_reward_proceed = action is not None
                        if action is None:
                            action = forced_ooc_action(screen, candidates)
                            forced_ooc = action is not None
        row.update({"screen_type": screen.get("screen_type", screen.get("screenType")),
                    "state_identity": transition_identity(screen, game_state),
                    "legal_candidates": [candidate.trace() for candidate in candidates]})
        if action:
            if reward_observation_marker is not None:
                self.previous_inspector = reward_observation_marker
            row["decision_source"] = ("parent_reward_cleanup" if parent_reward else
                                      "card_reward_reveal" if reveal_card else
                                      "neow_navigation" if neow_navigation else
                                      "shop_navigation" if shop_entry else
                                      "event_completion" if event_completion else
                                      "dead_adventurer_fight" if dead_adventurer_fight else
                                      "nest_intro" if nest_intro else
                                      "boss_door" if boss_door else
                                      "selector_confirmation" if selector_confirmation else
                                      "combat_selection_confirmation" if combat_selection_confirmation else
                                      "boss_chest_skip_cleanup" if boss_chest_skip_cleanup else
                                      "boss_chest_reveal" if boss_chest_reveal else
                                      "declined_reward_cleanup" if declined_reward_cleanup else
                                      "empty_reward_proceed" if empty_reward_proceed else "run_control")
            if forced_ooc:
                row["decision_source"] = "forced_ooc_action"
        else:
            combat = _is_combat(screen)
            inspector_state = {**game_state, **screen, "_expected_boundary": "combat" if combat else "ooc"}
            if combat and _list(game_state.get("monsters")):
                inspector_state["monsters"] = game_state["monsters"]
            if snapshot is None:
                snapshot = await self.inspector.read_for(inspector_state, self.previous_inspector)
            row.update({"inspector_session": snapshot.session, "inspector_sequence": snapshot.sequence,
                        "inspector_observationHash": snapshot.observation_hash,
                        "inspector_boundary": _mapping(snapshot.raw.get("observation")).get("boundary"),
                        "inspector_wait_micros": (time.monotonic() - advisor_started) * 1e6,
                        "advisor_latency_micros": snapshot.response.get("latencyMicros")})
            evaluator = snapshot.silver_evaluator() if combat else snapshot.ooc_evaluator(self.ooc_policy)
            prefix = "silver" if combat else "ooc_v4"
            status = _text(evaluator.get("status", evaluator.get("silverStatus"))).upper()
            row.update({"silver_evaluator" if combat else "ooc_evaluator": evaluator,
                        f"{prefix}_status": status, "selectedLiveAction": evaluator.get("selectedLiveAction")})
            if status == "OK":
                try:
                    action = (map_silver_action if combat else map_ooc_action)(evaluator.get("selectedLiveAction"), candidates)
                except IntegrationFailure as error:
                    self.counters["mapping_failures"] += 1
                    row.update({"mapping_candidates": error.matches, "mapping_match_count": len(error.matches)})
                    raise
                self.counters[f"{prefix}_ok"] += 1
                row.update({"decision_source": prefix, "mapping_candidates": [action.trace()], "mapping_match_count": 1})
            elif status == "UNSUPPORTED":
                reason = _text(evaluator.get("reason", evaluator.get("silverReason", "unknown")))
                self.counters[f"{prefix}_unsupported"] += 1
                self.unsupported[f"{prefix}:{reason}"] += 1
                row.update({"decision_source": prefix, "unsupported_reason": reason})
                if (self.strict_silver if combat else self.strict_ooc):
                    raise DriverError(f"{prefix} explicitly unsupported: {reason}")
                action, shop_entry_key = self.fallback_action(screen, game_state, candidates, snapshot)
                if shop_entry_key is not None:
                    row["shop_entry_room"] = list(shop_entry_key)
                self.counters["deterministic_fallback_combat" if combat else "deterministic_fallback_ooc"] += 1
                row.update({"decision_source": "deterministic_fallback", "fallback_reason": f"{prefix}_unsupported:{reason}"})
            else:
                raise DriverError(f"unexpected {prefix} advisor status: {status!r}")
            if not combat:
                row["ooc_scorer_latency_micros"] = evaluator.get("scorerLatencyMicros")
            latency = evaluator.get("latencyMicros")
            if type(latency) in (int, float) and math.isfinite(latency) and latency >= 0:
                row[f"{prefix}_latency_micros"] = latency
                if not combat and status == "OK":
                    self.latencies["ooc_v4_micros"].append(latency)
            scorer_latency = evaluator.get("scorerLatencyMicros")
            if (not combat and status == "OK" and type(scorer_latency) in (int, float)
                    and math.isfinite(scorer_latency) and scorer_latency >= 0):
                self.latencies["ooc_scorer_micros"].append(scorer_latency)
            self.previous_inspector = (snapshot.session, snapshot.sequence)
        row.update({"selected_candidate": action.id, "selected_mcp_tool": action.mcp_tool,
                    "selected_mcp_arguments": action.mcp_arguments})
        cycle_state = transition_identity(screen, game_state)
        if (snapshot is not None or reward_observation is not None) and screen.get("screen_type") in {"CARD_REWARD", "COMBAT_REWARD"}:
            ooc = reward_observation if reward_observation is not None else _mapping(
                _mapping(snapshot.raw.get("observation")).get("ooc"))
            # Identical visible offers can belong to distinct physical rewards.
            cycle_state += json.dumps([row.get("inspector_session"), ooc.get("rewardIdentity"),
                                       ooc.get("rewardOccurrences")], sort_keys=True)
        cycle_key = (cycle_state, action.mcp_tool,
                     json.dumps(action.mcp_arguments, sort_keys=True))
        if not _is_combat(screen) and cycle_key in self.ooc_actions_seen:
            raise DriverError("repeated OOC state/action cycle; no further action executed")
        if self.dry_run:
            row["dry_run"] = True
            self.outcome = "dry_run"
            self.trace.write(row)
            return False
        # Advisor work is asynchronous: re-read immediately before mutation so
        # an old, internally consistent response cannot act on a changed screen.
        current_screen, current_commands, current_game = await self.read_ready_snapshot()
        if transition_identity(current_screen, current_game) != transition_identity(screen, game_state):
            row["observed_state"] = {"screen": screen, "game_state": game_state}
            row["pre_action_state"] = {"screen": current_screen, "game_state": current_game}
            self.stale_retries += 1
            if self.stale_retries > 3:
                raise DriverError("MCP state changed during four consecutive advisor attempts; no action executed")
            previous_source = row.get("decision_source")
            if previous_source in {"silver", "ooc_v4"}:
                self.counters[f"{previous_source}_ok"] -= 1
            row["rejected_decision_source"] = previous_source
            row["decision_source"] = "stale_observation_retry"
            # The MCP can change display-only fields without a new inspector
            # observation. Revalidate this snapshot against the next state;
            # read_for still rejects it if an actionable identity changed.
            self.previous_inspector = None
            row["driver_step_micros"] = (time.monotonic() - started) * 1e6
            self.last_screen, self.last_game = current_screen, current_game
            self.trace.write(row)
            return True
        if action.mcp_tool not in _tool_names(current_commands):
            raise DriverError("selected MCP command is no longer advertised; no action executed")
        self.stale_retries = 0
        call_started = time.monotonic()
        row.update({"executed_mcp_tool": action.mcp_tool,
                    "executed_mcp_arguments": action.mcp_arguments})
        row["mcp_result"] = await self.client.call(action.mcp_tool, action.mcp_arguments)
        row["mcp_action_micros"] = (time.monotonic() - call_started) * 1e6
        if _mapping(row["mcp_result"]).get("success") is False or _mapping(row["mcp_result"]).get("error"):
            raise DriverError(f"MCP action failed: {row['mcp_result']!r}")
        if shop_entry_key is not None:
            self.entered_shop_rooms.add(shop_entry_key)
        if action.mcp_tool == "start_game":
            self.new_run_started = True
        if (screen.get("screen_type") == "GRID" and action.mcp_tool == "choose"
                and row.get("decision_source") == "ooc_v4"):
            act, floor = game_state.get("act"), screen.get("floor")
            if type(act) is int and type(floor) is int:
                self.pending_selector_confirmation = (act, floor, _text(screen.get("room_type")))
        if (screen.get("screen_type") == "BOSS_REWARD" and action.mcp_tool == "skip"
                and row.get("decision_source") == "ooc_v4"):
            act, floor = game_state.get("act"), screen.get("floor")
            if type(act) is int and type(floor) is int:
                self.boss_relic_skipped_rooms.add((act, floor))
        if not _is_combat(screen):
            self.ooc_actions_seen.add(cycle_key)
        if screen.get("screen_type") == "CARD_REWARD" and action.mcp_tool == "skip":
            ooc = _mapping(_mapping(snapshot.raw.get("observation")).get("ooc"))
            reward_identity = ooc.get("rewardIdentity")
            if isinstance(reward_identity, str) and reward_identity:
                self.declined_rewards.add((snapshot.session, reward_identity))
                row["declined_reward_identity"] = reward_identity
        self.steps += 1
        wait_started = time.monotonic()
        post, post_game_state = await self.wait_for_ready_advance(transition_identity(screen, game_state))
        row["post_action_wait_micros"] = (time.monotonic() - wait_started) * 1e6
        row.update({"post_action_state": _compact({"screen": post, "game_state": post_game_state}),
                    "post_action_identity": transition_identity(post, post_game_state),
                    "driver_step_micros": (time.monotonic() - started) * 1e6})
        self.latencies["driver_step_micros"].append(row["driver_step_micros"])
        self.last_screen, self.last_game = post, post_game_state
        self.trace.write(row)
        if _is_terminal(post):
            self.outcome = _terminal_outcome(post)
            return False
        return True

    def summary(self) -> dict[str, Any]:
        state = {**self.last_game, **self.last_screen}
        player = _mapping(state.get("player"))
        return {"record_type": "summary", "outcome": self.outcome, "steps": self.steps,
                "act": state.get("act", state.get("act_num")), "floor": state.get("floor", state.get("floor_num")),
                "hp": player.get("current_hp", player.get("current_health", player.get("hp",
                    state.get("current_hp", state.get("current_health", state.get("hp")))))),
                "combat_decisions": self.counters["silver_ok"] + self.counters["deterministic_fallback_combat"],
                "ooc_decisions": self.counters["ooc_v4_ok"] + self.counters["deterministic_fallback_ooc"],
                "counters": dict(self.counters), "unsupported_reasons": dict(self.unsupported),
                "wall_seconds": time.monotonic() - self.started,
                "latency": {name: _latency_summary(values) for name, values in self.latencies.items()}}

    def write_failure(self, error: BaseException) -> Path:
        self.outcome = "error"
        if (self.context.get("step") is not None
                and (not self.trace.recent or self.trace.recent[-1].get("step") != self.context.get("step"))):
            self.context.setdefault("driver_step_micros",
                                    (time.monotonic() - self.context_started_monotonic) * 1e6)
            self.context["decision_error"] = _exception_text(error)
            self.context["record_type"] = "decision_failure"
            self.trace.write(self.context)
        packet = {"schema": "live_driver_failure", "schemaVersion": 1,
                  "timestamp": datetime.now(timezone.utc).isoformat(), "driver": self.identity,
                  "step": self.context.get("step", self.steps), "screen": self.last_screen,
                  "game_state": self.last_game, "mcp_state_identity": transition_identity(self.last_screen, self.last_game),
                  "inspector": {"session": self.context.get("inspector_session"),
                                "sequence": self.context.get("inspector_sequence"),
                                "observationHash": self.context.get("inspector_observationHash"),
                                "boundary": self.context.get("inspector_boundary")},
                  "decision": self.context, "error_class": type(error).__name__, "reason": _exception_text(error),
                  "recent_trace": list(self.trace.recent), "trace_path": str(self.trace.path),
                  "reproduction_command": self.reproduction_command, "summary": self.summary()}
        # Include the rejected asynchronous snapshot for stale/malformed errors,
        # even when correlation failed before a decision could be formed.
        try:
            packet["inspector_snapshot"] = json.loads(self.inspector.path.read_text())
        except (OSError, ValueError):
            packet["inspector_snapshot"] = None
        self.failure_path = self.trace.write_failure(packet)
        self.trace.write_run_report(self.summary(), identity=self.identity,
                                    failure={"error_class": type(error).__name__,
                                             "reason": _exception_text(error),
                                             "step": packet["step"]})
        return self.failure_path

    async def run(self) -> None:
        step = 0
        try:
            while self.max_steps is None or step < self.max_steps:
                if not await self.step(step):
                    break
                step += 1
            else:
                self.outcome = "max_steps"
        except Exception as error:
            self.write_failure(error)
            raise
        finally:
            summary = self.summary()
            self.trace.write(summary)
            failure = None
            if self.failure_path is not None:
                try:
                    packet = json.loads(self.failure_path.read_text(encoding="utf-8"))
                    failure = {key: packet.get(key) for key in ("error_class", "reason", "step")}
                except (OSError, ValueError):
                    failure = {"reason": "failure packet could not be read"}
            self.trace.write_run_report(summary, identity=self.identity, failure=failure)


def _terminal_outcome(screen: Mapping[str, Any]) -> str:
    victory = _mapping(screen.get("screen_state")).get("victory")
    if type(victory) is bool:
        return "victory" if victory else "death"
    text = " ".join(_text(screen.get(key, "")).upper() for key in
                    ("screen_type", "screenType", "screen_name", "outcome", "run_state"))
    return "victory" if "VICTORY" in text else "death" if "DEATH" in text else "run_complete"


def _default_trace_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_TRACE_DIR / f"trace-{stamp}.jsonl"


def _reproduction_command(args: argparse.Namespace) -> str:
    command = ["uv", "run", "--extra", "live-driver", "python", "tools/live_game_driver.py",
               "--continue-run", "--run-until-error", "--mcp-url", args.mcp_url,
               "--inspector", args.inspector, "--inspector-timeout", str(args.inspector_timeout),
               "--startup-timeout", str(args.startup_timeout),
               "--ooc-policy", args.ooc_policy]
    for option in ("strict_silver", "strict_ooc", "dry_run"):
        if getattr(args, option):
            command.append("--" + option.replace("_", "-"))
    if args.max_steps is not None:
        command.extend(["--max-steps", str(args.max_steps)])
    return shlex.join(command)


async def async_main(args: argparse.Namespace) -> int:
    trace_path = Path(args.trace) if args.trace else _default_trace_path()
    trace = TraceWriter(trace_path)
    inspector = InspectorReader(Path(args.inspector), timeout=args.inspector_timeout)
    driver = None
    reproduction = _reproduction_command(args)
    try:
        async with connected_mcp(args.mcp_url) as client:
            driver = Driver(client, inspector, trace, dry_run=args.dry_run,
                            strict_silver=args.strict_silver, strict_ooc=args.strict_ooc,
                            ooc_policy=args.ooc_policy, max_steps=args.max_steps,
                            new_run=args.new_run, continue_run=args.continue_run,
                            character=args.character, ascension=args.ascension, seed=args.seed,
                            startup_timeout=args.startup_timeout,
                            reproduction_command=reproduction)
            await driver.run()
    except Exception as error:
        if driver is not None:
            failure = driver.failure_path or driver.write_failure(error)
            step = driver.context.get("step", driver.steps)
        else:
            step = 0
            failure = trace.write_failure({"schema": "live_driver_failure", "schemaVersion": 1,
                "timestamp": datetime.now(timezone.utc).isoformat(), "step": 0,
                "error_class": type(error).__name__, "reason": _exception_text(error),
                "trace_path": str(trace_path), "driver": _git_identity(), "recent_trace": [],
                "reproduction_command": reproduction})
        print(f"LIVE_DRIVER_ERROR type={type(error).__name__} step={step} trace={shlex.quote(str(trace_path))} report={shlex.quote(str(trace.run_report_path))} failure={shlex.quote(str(failure))}", file=sys.stderr)
        return 2
    print(f"trace: {trace_path}")
    print(f"run report: {trace.run_report_path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp-url", default=os.environ.get("STS_MCP_URL", DEFAULT_MCP_URL))
    parser.add_argument("--inspector", default=os.environ.get("STS_INSPECTOR_PATH", str(DEFAULT_INSPECTOR)))
    parser.add_argument("--trace", help="JSONL trace path (default: ~/.cache/sts-live-driver/)")
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--run-until-error", action="store_true", help="continue until terminal outcome or integration error")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strict-silver", action="store_true")
    parser.add_argument("--strict-ooc", action="store_true")
    parser.add_argument("--ooc-policy", choices=("mcts", "mcts_ctm", "v4", "v4_q"), default="mcts")
    run = parser.add_mutually_exclusive_group()
    run.add_argument("--new-run", action="store_true")
    run.add_argument("--continue-run", action="store_true")
    parser.add_argument("--character", choices=("IRONCLAD", "SILENT", "DEFECT", "WATCHER"))
    parser.add_argument("--ascension", type=int)
    parser.add_argument("--seed")
    parser.add_argument("--inspector-timeout", type=float, default=120.0,
                        help="fresh inspector response budget; OOC MCTS may take tens of seconds")
    parser.add_argument("--startup-timeout", type=float, default=45.0,
                        help="initial menu readiness budget; starts immediately when ready")
    args = parser.parse_args(argv)
    if args.max_steps is not None and args.max_steps < 0:
        parser.error("--max-steps must be nonnegative")
    if args.ascension is not None and not 0 <= args.ascension <= 20:
        parser.error("--ascension must be between 0 and 20")
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
