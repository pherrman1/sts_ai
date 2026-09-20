#!/usr/bin/env python3
"""Drive a live Slay the Spire run through MCPTheSpire.

The MCP server is the only game-control boundary. Silver supplies structured
combat actions when its evaluator is qualified; all other choices use the
small, deterministic policy in this file.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import itertools
import json
import os
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
    pass


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
                semantic = {"kind": "potion", "potion_slot": index + 1, "discard": tool == "discard_potion"}
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
                        {"kind": "choice", "choice_index": index + 1})
        elif tool in {"skip", "proceed", "cancel", "confirm", "start_game", "continue_game"}:
            _append(actions, tool, {}, tool.replace("_", " ").title(), {"kind": tool})
        elif tool == "select_cards":
            options = screen.get("selection_options", screen.get("select_options", game_state.get("selection_options")))
            for option in _list(options):
                args = _selection_arguments(option)
                if args is not None:
                    _append(actions, tool, args, f"Select cards: {args}", {"kind": "select_cards", **args})
            if not options:
                selection = _first_mapping(screen.get("selection"), game_state.get("selection"))
                cards = _list(selection.get("cards", hand))
                minimum = int(selection.get("min", selection.get("pick_count", selection.get("pickCount", 0))))
                maximum = min(int(selection.get("max", selection.get("pick_count", selection.get("pickCount", len(cards))))), len(cards))
                if maximum >= minimum:
                    for count in range(minimum, maximum + 1):
                        for indexes in itertools.combinations(range(1, len(cards) + 1), count):
                            _append(actions, tool, {"drop": list(indexes)}, f"Select cards to drop {list(indexes)}",
                                     {"kind": "select_cards", "drop": list(indexes)})
    if len(actions) > max_candidates:
        raise CandidateEnumerationError(f"legal action set has {len(actions)} candidates; configured limit is {max_candidates}")
    actionable = [name for name in names if name in ACTION_TOOLS]
    if actionable and not actions:
        raise CandidateEnumerationError(f"MCP advertises actionable tools {actionable} but no legal candidate was constructed")
    return actions


def _semantic_match(selected: Mapping[str, Any], action: LegalAction) -> bool:
    semantic = action.semantic
    selected_kind = selected.get("kind")
    if selected_kind and selected_kind != semantic.get("kind"):
        if not (selected_kind == "card_select" and semantic.get("kind") == "select_cards"):
            return False
    for selected_key, action_key in (("kind", "kind"), ("cardUuid", "card_uuid"),
                                     ("card_uuid", "card_uuid"), ("targetIndex", "target_index"),
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
    if len(matches) != 1:
        raise IntegrationFailure(f"Silver action mapping expected exactly one candidate, got {len(matches)} for {selected_live_action!r}")
    return matches[0]


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
        if not session or not isinstance(sequence, int) or not observation_hash:
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
            raw_summary = [(_mapping(monster).get("id"), _mapping(monster).get("hp")) for monster in raw_monsters]
            current_summary = [(_mapping(monster).get("id"), _mapping(monster).get("current_hp", _mapping(monster).get("hp"))) for monster in current_monsters]
            if raw_summary != current_summary:
                raise DriverError("inspector monster identity/state does not match MCP state")
            compared = True
        if not any(key in state for key in ("session", "sequence", "observationHash")) and not compared:
            raise DriverError("cannot correlate inspector observation with MCP-visible state")

    def silver_evaluator(self) -> Mapping[str, Any]:
        for evaluator in _list(self.advisor.get("evaluators")):
            if _mapping(evaluator).get("id") == "silver_player_decision_v2":
                return _mapping(evaluator)
        if self.advisor.get("silverStatus") is not None:
            return self.advisor
        raise DriverError("advisor response contains no silver_player_decision_v2 evaluator")


class InspectorReader:
    def __init__(self, path: Path, timeout: float = 8.0, poll_interval: float = 0.1):
        self.path, self.timeout, self.poll_interval = path, timeout, poll_interval

    async def read_for(self, state: Mapping[str, Any]) -> InspectorSnapshot:
        deadline, last_error = time.monotonic() + self.timeout, None
        while time.monotonic() < deadline:
            try:
                snapshot = InspectorSnapshot.load(self.path)
                snapshot.validate_current(state)
                return snapshot
            except DriverError as error:
                last_error = error
            await asyncio.sleep(self.poll_interval)
        raise DriverError(f"no fresh inspector response for current state: {last_error}")


class TraceWriter:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): ("[REDACTED]" if "api_key" in str(key).lower() or "secret" in str(key).lower()
                               else self._sanitize(item)) for key, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        return value

    def write(self, row: Mapping[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self._sanitize(dict(row)), sort_keys=True, default=str) + "\n")


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
    return (_text(screen.get("screen_type", screen.get("screenType", ""))).upper() in {"NONE", "COMBAT"}
            or _text(screen.get("room_phase", screen.get("roomPhase", ""))).upper() == "COMBAT")


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


class Driver:
    def __init__(self, client: McpGameClient, inspector: InspectorReader, trace: TraceWriter, *,
                 dry_run: bool = False, strict_silver: bool = False, max_steps: int | None = None,
                 poll_timeout: float = 8.0, poll_interval: float = 0.1):
        self.client, self.inspector, self.trace = client, inspector, trace
        self.dry_run, self.strict_silver, self.max_steps = dry_run, strict_silver, max_steps
        self.poll_timeout, self.poll_interval = poll_timeout, poll_interval

    async def read_screen(self) -> Mapping[str, Any]:
        screen = await self.client.call("get_screen_state")
        if not isinstance(screen, Mapping):
            raise DriverError(f"MCP screen state is not an object: {screen!r}")
        return screen

    async def read_ready_state(self) -> tuple[Mapping[str, Any], Any]:
        deadline, last = time.monotonic() + self.poll_timeout, {}
        while time.monotonic() < deadline:
            screen = await self.read_screen()
            last = screen
            if _ready(screen):
                commands = await self.client.call("get_available_commands")
                if _ready(commands):
                    return screen, commands
            await asyncio.sleep(self.poll_interval)
        raise DriverError(f"MCP state was not ready for a command within {self.poll_timeout:.1f}s: {last!r}")

    async def wait_for_ready_advance(self, before: str) -> Mapping[str, Any]:
        deadline, last = time.monotonic() + self.poll_timeout, {}
        while time.monotonic() < deadline:
            screen = await self.read_screen()
            last = screen
            if _ready(screen):
                commands = await self.client.call("get_available_commands")
                if _ready(commands) and state_identity(screen) != before:
                    return screen
            await asyncio.sleep(self.poll_interval)
        raise DriverError(f"post-action MCP state did not become ready and advance within {self.poll_timeout:.1f}s: {last!r}")

    async def step(self, step: int) -> bool:
        screen, commands = await self.read_ready_state()
        if _is_terminal(screen):
            return False
        game_state: dict[str, Any] = {}
        if "get_game_state" in self.client.tool_names:
            game_state = normalize_game_state(await self.client.call("get_game_state"))
        candidates = build_legal_actions(screen, commands, game_state)
        if not candidates:
            raise DriverError("no legal candidates for a non-terminal screen")
        row: dict[str, Any] = {"timestamp": datetime.now(timezone.utc).isoformat(), "step": step,
                               "screen_type": screen.get("screen_type", screen.get("screenType")),
                               "state_identity": state_identity(screen),
                               "legal_candidates": [candidate.trace() for candidate in candidates]}
        if _is_combat(screen):
            snapshot = await self.inspector.read_for(screen)
            evaluator = snapshot.silver_evaluator()
            status = _text(evaluator.get("status", evaluator.get("silverStatus"))).upper()
            row.update({"inspector_session": snapshot.session, "inspector_sequence": snapshot.sequence,
                        "inspector_observationHash": snapshot.observation_hash, "silver_status": status,
                        "silver_selected_action": evaluator.get("selectedAction"),
                        "silver_selected_live_action": evaluator.get("selectedLiveAction")})
            if status == "OK":
                action = map_silver_action(evaluator.get("selectedLiveAction"), candidates)
                row.update({"decision_source": "silver", "silver_mapping_result": action.id})
            elif status == "UNSUPPORTED":
                reason = _text(evaluator.get("reason", evaluator.get("silverReason", "unknown")))
                if self.strict_silver:
                    raise DriverError(f"Silver explicitly unsupported: {reason}")
                action = choose_deterministic_action(screen, candidates)
                row.update({"decision_source": "deterministic_fallback", "fallback_reason": f"silver_unsupported:{reason}"})
            else:
                raise DriverError(f"unexpected Silver advisor status: {status!r}")
        else:
            action = choose_deterministic_action(screen, candidates)
            row.update({"decision_source": "deterministic_fallback",
                        "fallback_reason": f"non_combat_policy:{_text(screen.get('screen_type', screen.get('screenType', 'UNKNOWN')))}"})
        row.update({"selected_candidate": action.id, "executed_mcp_tool": action.mcp_tool,
                    "executed_mcp_arguments": action.mcp_arguments})
        if self.dry_run:
            row["dry_run"] = True
            self.trace.write(row)
            return False
        row["mcp_result"] = await self.client.call(action.mcp_tool, action.mcp_arguments)
        try:
            post = await self.wait_for_ready_advance(state_identity(screen))
        except DriverError:
            self.trace.write(row)
            raise
        row.update({"post_action_state": _compact(post), "post_action_identity": state_identity(post)})
        for key in ("session", "sequence", "observationHash"):
            if key in post:
                row[f"post_action_{key}"] = post[key]
        self.trace.write(row)
        return not _is_terminal(post)

    async def run(self) -> None:
        step = 0
        while self.max_steps is None or step < self.max_steps:
            if not await self.step(step):
                return
            step += 1


def _default_trace_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_TRACE_DIR / f"trace-{stamp}.jsonl"


async def async_main(args: argparse.Namespace) -> int:
    trace_path = Path(args.trace) if args.trace else _default_trace_path()
    trace = TraceWriter(trace_path)
    inspector = InspectorReader(Path(args.inspector), timeout=args.inspector_timeout)
    try:
        async with connected_mcp(args.mcp_url) as client:
            await Driver(client, inspector, trace, dry_run=args.dry_run,
                         strict_silver=args.strict_silver, max_steps=args.max_steps).run()
    except DriverError as error:
        print(f"live-game-driver: {error}\ntrace: {trace_path}", file=sys.stderr)
        return 2
    print(f"trace: {trace_path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp-url", default=os.environ.get("STS_MCP_URL", DEFAULT_MCP_URL))
    parser.add_argument("--inspector", default=os.environ.get("STS_INSPECTOR_PATH", str(DEFAULT_INSPECTOR)))
    parser.add_argument("--trace", help="JSONL trace path (default: ~/.cache/sts-live-driver/)")
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strict-silver", action="store_true")
    parser.add_argument("--inspector-timeout", type=float, default=8.0)
    return asyncio.run(async_main(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
