#!/usr/bin/env python3
"""Drive a live Slay the Spire run through MCPTheSpire.

This is an integration/debug harness.  It deliberately keeps the MCP server as
the only game-control boundary and keeps JEV restricted to choosing among
already-materialized candidate IDs.
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
MAX_JEV_CANDIDATES = 128
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
    """Convert an MCP SDK result to its structured JSON payload."""
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
        parts: list[Any] = []
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
    """Keep JEV prompts and traces bounded without changing candidate identity."""
    if isinstance(value, Mapping):
        result = {str(k): _compact(v, limit) for k, v in value.items()}
    elif isinstance(value, list):
        result = [_compact(v, limit) for v in value]
    else:
        return value
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), default=str)
    if len(encoded) <= limit:
        return result
    return {"truncated": True, "sha256": hashlib.sha256(encoded.encode()).hexdigest(),
            "bytes": len(encoded)}


def state_identity(state: Mapping[str, Any]) -> str:
    """Return a stable identity for transition verification."""
    explicit = {key: state[key] for key in ("session", "sequence", "observationHash") if key in state}
    if len(explicit) == 3:
        return json.dumps(explicit, sort_keys=True, separators=(",", ":"))
    payload = _compact(dict(state), 50000)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


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
                "mcp_tool": self.mcp_tool, "mcp_arguments": self.mcp_arguments}


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


def build_legal_actions(
    screen: Mapping[str, Any],
    commands: Mapping[str, Any] | Sequence[str],
    game_state: Mapping[str, Any] | None = None,
    *,
    max_candidates: int = MAX_JEV_CANDIDATES,
) -> list[LegalAction]:
    """Materialize concrete MCP calls from the current advertised surface."""
    screen = dict(screen)
    game_state = dict(game_state or {})
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
                name = _card_name(card)
                uuid = _card_uuid(card)
                suffix = f" uuid={uuid}" if uuid else f" index={index + 1}"
                base = {"card_index": index + 1}
                semantic = {"kind": "card", "card_uuid": uuid, "card_id": card.get("id"),
                            "card_index": index + 1, "silver_label": name}
                fingerprint = card.get("silver_fingerprint", card.get("semantic_fingerprint"))
                if card.get("has_target") or card.get("hasTarget"):
                    for target in targets:
                        _append(actions, tool, {**base, "target_index": target},
                                f"Play {name}{suffix} -> monster {target}",
                                {**semantic, "target_index": target,
                                 "silver_label": f"{name} -> Monster {target}"},
                                _text(fingerprint) if fingerprint else None)
                else:
                    _append(actions, tool, base, f"Play {name}{suffix}", semantic,
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
                args = {"potion_slot": index + 1}
                requires_target = potion.get("requires_target", potion.get("requiresTarget", potion.get("has_target", False)))
                if requires_target:
                    for target in targets:
                        _append(actions, tool, {**args, "target_index": target},
                                f"{tool.replace('_', ' ').title()} {potion_id} slot {index + 1} -> monster {target}",
                                {"kind": "potion", "potion_slot": index + 1, "target_index": target,
                                 "silver_label": f"Use {potion_id} -> Monster {target}"})
                else:
                    _append(actions, tool, args, f"{tool.replace('_', ' ').title()} {potion_id} slot {index + 1}",
                             {"kind": "potion", "potion_slot": index + 1,
                              "silver_label": f"Use {potion_id}"})
        elif tool == "choose":
            for index, choice in enumerate(choices):
                _append(actions, tool, {"choice_index": index + 1},
                        f"Choose {index + 1}: {_choice_label(choice)}",
                        {"kind": "choice", "choice_index": index + 1})
        elif tool in {"skip", "proceed", "cancel", "confirm"}:
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
                maximum = int(selection.get("max", selection.get("pick_count", selection.get("pickCount", len(cards)))))
                maximum = min(maximum, len(cards))
                if maximum >= minimum:
                    for count in range(minimum, maximum + 1):
                        for indexes in itertools.combinations(range(1, len(cards) + 1), count):
                            args = {"drop": list(indexes)}
                            _append(actions, tool, args, f"Select cards to drop {list(indexes)}",
                                     {"kind": "select_cards", "drop": list(indexes)})

    if len(actions) > max_candidates:
        raise CandidateEnumerationError(
            f"legal action set has {len(actions)} candidates; configured JEV limit is {max_candidates}")
    actionable_advertised = [name for name in names if name in ACTION_TOOLS]
    if actionable_advertised and not actions:
        raise CandidateEnumerationError(
            f"MCP advertises actionable tools {actionable_advertised} but no legal candidate was constructed")
    return actions


def _semantic_match(selected: Mapping[str, Any], action: LegalAction) -> bool:
    semantic = action.semantic
    if selected.get("kind") and selected.get("kind") != semantic.get("kind"):
        return False
    for left, right in (("card_uuid", "card_uuid"), ("target_index", "target_index"),
                        ("potion_slot", "potion_slot"), ("choice_index", "choice_index")):
        if left in selected and selected[left] != semantic.get(right):
            return False
    return bool(selected) and all(key in semantic or key not in {"kind", "card_uuid", "target_index", "potion_slot", "choice_index"}
                                 for key in selected)


def map_silver_action(selected_action: Any, candidates: Sequence[LegalAction], *, selected_label: str | None = None) -> LegalAction:
    """Map Silver's semantic recommendation to exactly one MCP candidate."""
    matches = [candidate for candidate in candidates
               if candidate.silver_fingerprint is not None and candidate.silver_fingerprint == selected_action]
    if not matches and isinstance(selected_action, Mapping):
        matches = [candidate for candidate in candidates if _semantic_match(selected_action, candidate)]
    if not matches and selected_label:
        # Labels are only a last-resort bridge for protocols that omit the
        # stable fingerprint.  Ambiguous labels are never guessed.
        matches = [candidate for candidate in candidates
                   if candidate.semantic.get("silver_label") == selected_label]
    if len(matches) != 1:
        raise IntegrationFailure(
            f"Silver action mapping expected exactly one candidate, got {len(matches)} for {selected_action!r}")
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
        session = _text(raw.get("session"))
        sequence = raw.get("sequence")
        observation_hash = _text(raw.get("observationHash"))
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
        for key, expected in (("session", self.session), ("sequence", self.sequence),
                              ("observationHash", self.observation_hash)):
            if key in state and state[key] != expected:
                raise DriverError(f"inspector {key} does not match MCP state: {state[key]!r} != {expected!r}")
        observation = _mapping(self.raw.get("observation"))
        if observation.get("boundary") not in (None, "combat"):
            raise DriverError(f"inspector observation boundary is not combat: {observation.get('boundary')!r}")
        screen_type = _text(state.get("screen_type", state.get("screenType", ""))).upper()
        phase = _text(state.get("room_phase", state.get("roomPhase", ""))).upper()
        if screen_type not in {"", "NONE", "COMBAT"} and phase != "COMBAT":
            raise DriverError(f"inspector combat observation does not correspond to screen {screen_type!r}")
        # If the MCP surface exposes card/monster identity, compare it with the
        # raw observation.  Lack of these optional fields is tolerated because
        # older MCPTheSpire builds only expose screen state and identity.
        silver_root = _mapping(observation.get("silverRoot"))
        combat = _mapping(silver_root.get("combat", observation.get("combat")))
        raw_hand = _list(combat.get("hand"))
        current_hand = _list(state.get("hand"))
        compared = False
        if raw_hand and current_hand:
            raw_uuids = {_card_uuid(_mapping(card)) for card in raw_hand}
            current_uuids = {_card_uuid(_mapping(card)) for card in current_hand}
            if raw_uuids and current_uuids and raw_uuids != current_uuids:
                raise DriverError("inspector hand identity does not match MCP state")
            compared = bool(raw_uuids and current_uuids)
        raw_monsters = _list(combat.get("monsters"))
        current_monsters = _list(state.get("monsters"))
        if raw_monsters and current_monsters:
            raw_summary = [(_mapping(monster).get("id"), _mapping(monster).get("hp"))
                           for monster in raw_monsters]
            current_summary = [(_mapping(monster).get("id"),
                                _mapping(monster).get("current_hp", _mapping(monster).get("hp")))
                               for monster in current_monsters]
            if raw_summary != current_summary:
                raise DriverError("inspector monster identity/state does not match MCP state")
            compared = True
        if not any(key in state for key in ("session", "sequence", "observationHash")) and not compared:
            raise DriverError("cannot correlate inspector observation with MCP-visible state")

    def silver_evaluator(self) -> Mapping[str, Any]:
        evaluators = _list(self.advisor.get("evaluators"))
        for evaluator in evaluators:
            if _mapping(evaluator).get("id") == "silver_player_decision_v2":
                return _mapping(evaluator)
        if self.advisor.get("silverStatus") is not None:
            return self.advisor
        raise DriverError("advisor response contains no silver_player_decision_v2 evaluator")


class InspectorReader:
    def __init__(self, path: Path, timeout: float = 8.0, poll_interval: float = 0.1):
        self.path, self.timeout, self.poll_interval = path, timeout, poll_interval

    async def read_for(self, state: Mapping[str, Any]) -> InspectorSnapshot:
        deadline = time.monotonic() + self.timeout
        last_error: Exception | None = None
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
    def __init__(self, path: Path, secret: str | None = None):
        self.path = path
        self.secret = secret
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): ("[REDACTED]" if "api_key" in str(key).lower() or "secret" in str(key).lower()
                               else self._sanitize(item)) for key, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        if isinstance(value, str) and self.secret:
            return value.replace(self.secret, "[REDACTED]")
        return value

    def write(self, row: Mapping[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self._sanitize(dict(row)), sort_keys=True, default=str) + "\n")


class JevPolicy:
    def __init__(self, client: Any = None):
        self.client = client
        self._owned = client is None

    async def __aenter__(self) -> "JevPolicy":
        if self._owned:
            try:
                from typesafe_sdk import AsyncTypeSafeClient
            except ImportError as error:
                raise DriverError("live-driver extra is missing typesafe-sdk") from error
            if not os.environ.get("TYPESAFE_API_KEY"):
                raise DriverError("TYPESAFE_API_KEY is required for non-combat JEV decisions")
            self.client = AsyncTypeSafeClient()
            await self.client.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._owned and self.client is not None:
            await self.client.__aexit__(exc_type, exc, tb)

    async def choose(self, state: Mapping[str, Any], candidates: Sequence[LegalAction]) -> dict[str, Any]:
        if not candidates:
            raise DriverError("JEV cannot choose from an empty legal action set")
        try:
            from typesafe_sdk import Choice
        except ImportError as error:
            raise DriverError("live-driver extra is missing typesafe-sdk") from error
        criteria = {candidate.id: candidate.human_description for candidate in candidates}
        started = time.monotonic()
        response = await self.client.system_one(
            state={"game": _compact(state), "legal_actions": criteria},
            questions={"action": Choice(
                instructions="Choose one supplied legal action ID for the current Slay the Spire state. Return only an ID.",
                criteria=criteria,
            )},
        )
        latency_ms = (time.monotonic() - started) * 1000.0
        answer = response.choices.get("action") if hasattr(response, "choices") else response.answers.get("action")
        choice = getattr(answer, "choice", None)
        probabilities = getattr(answer, "probabilities", None)
        confidence = getattr(answer, "confidence", None)
        if choice not in {candidate.id for candidate in candidates}:
            raise DriverError(f"JEV selected illegal candidate {choice!r}")
        return {"choice": choice, "probabilities": probabilities, "confidence": confidence,
                "latency_ms": latency_ms}


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
    screen_type = _text(screen.get("screen_type", screen.get("screenType", ""))).upper()
    phase = _text(screen.get("room_phase", screen.get("roomPhase", ""))).upper()
    return screen_type in {"NONE", "COMBAT"} or phase == "COMBAT"


def _is_terminal(screen: Mapping[str, Any]) -> bool:
    text = " ".join(_text(screen.get(key, "")).upper() for key in ("screen_type", "screenType", "room_phase", "roomPhase", "outcome", "run_state"))
    return any(marker in text for marker in ("VICTORY", "DEATH", "GAME_OVER", "GAME OVER", "RUN_COMPLETE"))


class Driver:
    def __init__(self, client: McpGameClient, jev: JevPolicy, inspector: InspectorReader,
                 trace: TraceWriter, *, dry_run: bool = False, strict_silver: bool = False,
                 max_steps: int | None = None, poll_timeout: float = 8.0,
                 poll_interval: float = 0.1):
        self.client, self.jev, self.inspector, self.trace = client, jev, inspector, trace
        self.dry_run, self.strict_silver, self.max_steps = dry_run, strict_silver, max_steps
        self.poll_timeout, self.poll_interval = poll_timeout, poll_interval

    async def read_screen(self) -> Mapping[str, Any]:
        screen = await self.client.call("get_screen_state")
        if not isinstance(screen, Mapping):
            raise DriverError(f"MCP screen state is not an object: {screen!r}")
        return screen

    async def wait_for_change(self, before: str) -> Mapping[str, Any]:
        deadline = time.monotonic() + self.poll_timeout
        last: Mapping[str, Any] = {}
        while time.monotonic() < deadline:
            last = await self.read_screen()
            if state_identity(last) != before:
                return last
            await asyncio.sleep(self.poll_interval)
        raise DriverError(f"post-action MCP state did not advance within {self.poll_timeout:.1f}s")

    async def step(self, step: int) -> bool:
        screen = await self.read_screen()
        if _is_terminal(screen):
            return False
        commands = await self.client.call("get_available_commands")
        game_state: Mapping[str, Any] = {}
        if "get_game_state" in self.client.tool_names:
            value = await self.client.call("get_game_state")
            if isinstance(value, Mapping):
                game_state = value
        candidates = build_legal_actions(screen, commands, game_state)
        if not candidates:
            raise DriverError("no legal candidates for a non-terminal screen")
        row: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(), "step": step,
            "screen_type": screen.get("screen_type", screen.get("screenType")),
            "state_identity": state_identity(screen),
            "legal_candidates": [candidate.trace() for candidate in candidates],
        }
        if _is_combat(screen):
            snapshot = await self.inspector.read_for(screen)
            evaluator = snapshot.silver_evaluator()
            row.update({"inspector_session": snapshot.session, "inspector_sequence": snapshot.sequence,
                        "inspector_observationHash": snapshot.observation_hash,
                        "silver_status": evaluator.get("status", evaluator.get("silverStatus")),
                        "silver_selected_action": evaluator.get("selectedAction")})
            status = _text(evaluator.get("status", evaluator.get("silverStatus"))).upper()
            if status == "OK":
                selected = evaluator.get("selectedAction")
                action = map_silver_action(selected, candidates, selected_label=evaluator.get("selectedLabel"))
                row.update({"decision_source": "silver", "silver_mapping_result": action.id})
            elif status == "UNSUPPORTED":
                reason = _text(evaluator.get("reason", evaluator.get("silverReason", "unknown")))
                row.update({"fallback_reason": f"silver_unsupported:{reason}"})
                if self.strict_silver:
                    raise DriverError(f"Silver explicitly unsupported: {reason}")
                jev_result = await self.jev.choose({"screen": screen, "game": game_state}, candidates)
                action = next(candidate for candidate in candidates if candidate.id == jev_result["choice"])
                row.update({"decision_source": "jev", "jev": jev_result})
            else:
                raise DriverError(f"unexpected Silver advisor status: {status!r}")
        else:
            jev_result = await self.jev.choose({"screen": screen, "game": game_state}, candidates)
            action = next(candidate for candidate in candidates if candidate.id == jev_result["choice"])
            row.update({"decision_source": "jev", "jev": jev_result})
        row["selected_candidate"] = action.id
        row["executed_mcp_tool"] = action.mcp_tool
        row["executed_mcp_arguments"] = action.mcp_arguments
        if self.dry_run:
            row["dry_run"] = True
            self.trace.write(row)
            return False
        result = await self.client.call(action.mcp_tool, action.mcp_arguments)
        row["mcp_result"] = result
        try:
            post = await self.wait_for_change(state_identity(screen))
        except DriverError:
            self.trace.write(row)
            raise
        row["post_action_state"] = _compact(post)
        row["post_action_identity"] = state_identity(post)
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
    secret = os.environ.get("TYPESAFE_API_KEY")
    trace = TraceWriter(trace_path, secret)
    inspector = InspectorReader(Path(args.inspector), timeout=args.inspector_timeout)
    try:
        async with connected_mcp(args.mcp_url) as client:
            async with JevPolicy() as jev:
                await Driver(client, jev, inspector, trace, dry_run=args.dry_run,
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
