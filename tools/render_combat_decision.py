#!/usr/bin/env python3
"""Render one captured Slay the Spire combat decision as standalone HTML.

This is intentionally a read-only presentation tool.  It does not contact the
game, run a simulator, or reinterpret Silver's root statistics.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
import webbrowser
from pathlib import Path
from typing import Any, Mapping, Sequence


SILVER_ID = "silver_player_decision_v2"


class RenderError(ValueError):
    """An input cannot be mapped to one decision without guessing."""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any, default: str = "not captured") -> str:
    if value is None or value == "":
        return default
    return str(value)


def _pick(*objects: Any, keys: Sequence[str], default: Any = None) -> Any:
    for obj in objects:
        if not isinstance(obj, Mapping):
            continue
        for key in keys:
            if key in obj and obj[key] is not None:
                return obj[key]
    return default


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RenderError(f"input file is unavailable: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise RenderError(f"malformed JSON input {path}: {error}") from error


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, default=str)


def _source(raw: Mapping[str, Any], *, kind: str, evaluator: Mapping[str, Any] | None = None,
            observation: Mapping[str, Any] | None = None, decision: Mapping[str, Any] | None = None) -> dict[str, Any]:
    observation = observation or {}
    evaluator = evaluator or {}
    decision = decision or {}
    if kind == "snapshot":
        state = _combat_state(observation)
        raw_data = raw
        before = state
        after = None
        legal_actions = evaluator.get("legalActions")
        matched = None
        executed = None
    elif kind == "trace":
        state = _trace_before(decision)
        raw_data = decision
        after = _first_mapping(decision, ("post_action_state", "after"))
        legal_actions = decision.get("legal_candidates", decision.get("legalActions", []))
        evaluator = _first_mapping(decision, ("silver_evaluator", "evaluator"))
        matched = _first_mapping(decision, ("mapping_candidates", "selected_candidate_trace", "selected_candidate"))
        executed = _executed(decision)
        before = state
        observation = _mapping(decision.get("observation"))
    else:
        observation = _mapping(decision.get("liveObservation"))
        state = _combat_state(observation)
        raw_data = decision
        before = _first_mapping(decision, ("before",))
        after = _first_mapping(decision, ("after",))
        legal_actions = decision.get("legalActions", [])
        selected = _mapping(decision.get("selectedAction"))
        evaluator = {"status": "not captured", "reason": "differential trace record",
                     "selectedAction": selected.get("identity")}
        matched = _mapping(selected.get("action"))
        executed = _mapping(decision.get("mcpAction"))
    return {
        "kind": kind,
        "raw": raw_data,
        "observation": observation,
        "state": state,
        "before": before,
        "after": after,
        "evaluator": evaluator,
        "legal_actions": _list(legal_actions),
        "matched": matched,
        "executed": executed,
    }


def _first_mapping(obj: Mapping[str, Any], keys: Sequence[str]) -> Mapping[str, Any]:
    for key in keys:
        value = obj.get(key)
        if isinstance(value, Mapping):
            return value
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], Mapping):
            return value[0]
    return {}


def _executed(row: Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(row.get("executed_mcp_action"), Mapping):
        return row["executed_mcp_action"]
    tool = row.get("executed_mcp_tool", row.get("selected_mcp_tool"))
    arguments = row.get("executed_mcp_arguments", row.get("selected_mcp_arguments"))
    if tool is None and arguments is None:
        return {}
    return {"tool": tool, "arguments": arguments or {}}


def _trace_before(row: Mapping[str, Any]) -> Mapping[str, Any]:
    # The current driver intentionally records compact identity fields rather
    # than a fabricated full pre-state.  Only use an explicit state packet.
    for key in ("before", "pre_action_state", "observed_state", "state"):
        value = row.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _combat_state(observation: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("combat", "combatState", "game_state", "gameState"):
        if isinstance(observation.get(key), Mapping):
            return observation[key]
    silver_root = _mapping(observation.get("silverRoot"))
    for key in ("combat", "combatState"):
        if isinstance(silver_root.get(key), Mapping):
            return silver_root[key]
    # Some inspector versions put the combat fields directly under observation.
    if any(key in observation for key in ("player", "hand", "monsters", "draw_pile", "drawPile")):
        return observation
    return {}


def load_snapshot(path: Path) -> dict[str, Any]:
    raw = _read_json(path)
    if not isinstance(raw, Mapping):
        raise RenderError("malformed inspector snapshot: top level is not an object")
    observation = _mapping(raw.get("observation"))
    if observation.get("boundary") != "combat":
        raise RenderError(f"inspector observation is not combat: {observation.get('boundary', 'missing')!r}")
    response = _mapping(raw.get("response"))
    advisor = _mapping(response.get("advisor"))
    evaluators = [item for item in _list(advisor.get("evaluators"))
                  if isinstance(item, Mapping) and item.get("id") == SILVER_ID]
    if not evaluators:
        raise RenderError(f"snapshot contains no {SILVER_ID} evaluator")
    if len(evaluators) != 1:
        raise RenderError(f"snapshot contains multiple ambiguous {SILVER_ID} evaluators")
    return _source(raw, kind="snapshot", observation=observation, evaluator=evaluators[0])


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise RenderError(f"input file is unavailable: {path}") from error
    except OSError as error:
        raise RenderError(f"cannot read trace {path}: {error}") from error
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise RenderError(f"malformed trace {path} line {number}: {error}") from error
        if not isinstance(row, Mapping):
            raise RenderError(f"malformed trace {path} line {number}: row is not an object")
        rows.append(dict(row))
    return rows


def load_trace(path: Path, step: int) -> dict[str, Any]:
    matches = [row for row in _read_jsonl(path)
               if row.get("step") == step and row.get("record_type") != "summary"]
    if not matches:
        raise RenderError(f"trace contains no normal decision row for step {step}")
    if len(matches) != 1:
        raise RenderError(f"trace contains {len(matches)} decision rows for step {step}; expected exactly one")
    if not isinstance(matches[0].get("silver_evaluator"), Mapping):
        raise RenderError(f"trace step {step} is not a normal combat decision row: no Silver evaluator")
    return _source(matches[0], kind="trace", decision=matches[0])


def load_differential_trace(path: Path, decision_index: int) -> dict[str, Any]:
    matches = [row for row in _read_jsonl(path)
               if row.get("record_type") == "decision" and row.get("decisionIndex") == decision_index]
    if not matches:
        raise RenderError(f"differential trace contains no decision {decision_index}")
    if len(matches) != 1:
        raise RenderError(f"differential trace contains {len(matches)} records for decision {decision_index}")
    record = matches[0]
    if record.get("schema") != "sts_differential_trace":
        raise RenderError(f"differential decision {decision_index} has unsupported schema")
    if record.get("schemaVersion") != 1:
        raise RenderError(f"differential decision {decision_index} has unsupported schema version")
    if record.get("boundary") != "combat":
        raise RenderError(f"differential decision {decision_index} is not a combat record")
    return _source(record, kind="differential", decision=record)


def _esc(value: Any) -> str:
    return html.escape(_text(value), quote=True)


def _pretty(value: Any) -> str:
    return html.escape(_json(value))


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.4g}"
    return _esc(value)


def _cell(value: Any) -> str:
    return f"<td>{_value(value)}</td>"


def _state_packet(source: Mapping[str, Any]) -> Mapping[str, Any]:
    state = _mapping(source.get("state"))
    before = _mapping(source.get("before"))
    return state or before


def _header(source: Mapping[str, Any]) -> str:
    raw = _mapping(source.get("raw"))
    observation = _mapping(source.get("observation"))
    state = _state_packet(source)
    evaluator = _mapping(source.get("evaluator"))
    silver_root = _mapping(observation.get("silverRoot"))
    player = _mapping(_pick(state, observation, keys=("player",), default={}))
    identity = [
        ("session", _pick(raw, observation, keys=("session", "inspector_session"), default=None)),
        ("sequence", _pick(raw, observation, keys=("sequence", "inspector_sequence"), default=None)),
        ("observation hash", _pick(raw, observation, keys=("observationHash", "observation_hash", "inspector_observationHash"), default=None)),
        ("act", _pick(state, observation, raw, keys=("act", "act_num", "actNum"), default=None)),
        ("floor", _pick(state, observation, raw, keys=("floor", "floor_num", "floorNum"), default=None)),
        ("encounter", _pick(state, observation, silver_root, keys=("encounter", "encounterName", "room_type", "roomType"), default=None)),
        ("turn", _pick(state, observation, keys=("turn", "turnNumber", "turn_num"), default=None)),
        ("decision in turn", evaluator.get("decisionInTurn")),
        ("HP", _pick(player, state, observation, keys=("current_hp", "currentHp", "current_health", "hp"), default=None)),
        ("max HP", _pick(player, state, observation, keys=("max_hp", "maxHp", "max_health"), default=None)),
        ("energy", _pick(player, state, observation, keys=("energy", "energy_panel"), default=None)),
        ("requested simulations", evaluator.get("requestedSimulations")),
        ("total simulations", evaluator.get("totalSimulations", evaluator.get("simulations"))),
        ("root visits", evaluator.get("rootVisits")),
        ("inherited visits", _pick(evaluator.get("reroot"), keys=("inheritedVisits",), default=None)),
        ("reroot mode", _reroot_mode(evaluator.get("reroot"))),
    ]
    items = "".join(f"<div class=\"metric\"><span>{_esc(label)}</span><strong>{_value(value)}</strong></div>"
                    for label, value in identity)
    selected = evaluator.get("selectedAction", "not captured")
    return (
        f"<section class=\"decision-header\"><div class=\"metrics\">{items}</div>"
        f"<div class=\"selected-summary\">Selected Silver action: <code>{_esc(selected)}</code></div></section>"
    )


def _reroot_mode(value: Any) -> str:
    reroot = _mapping(value)
    if not reroot:
        return "not captured"
    if reroot.get("fallback"):
        reason = reroot.get("fallbackReason", "reason not captured")
        return f"fallback ({reason})"
    if reroot.get("exact"):
        return "exact"
    if reroot.get("equivalentCopy"):
        return "equivalent copy"
    return "not rerooted"


def _combat_section(source: Mapping[str, Any]) -> str:
    observation = _mapping(source.get("observation"))
    state = _state_packet(source)
    if not state:
        return '<section><h2>Combat state</h2><p class="muted">not captured in this source</p></section>'
    player = _mapping(state.get("player")) or state
    fields = [("HP", _pick(player, state, observation, keys=("current_hp", "currentHp", "current_health", "hp"))),
              ("block", _pick(player, state, observation, keys=("block", "current_block", "currentBlock"))),
              ("energy", _pick(player, state, observation, keys=("energy",))),]
    player_html = "".join(f"<div class=\"state-chip\"><span>{_esc(k)}</span><b>{_value(v)}</b></div>" for k, v in fields)
    enemies = _list(_pick(state, keys=("monsters", "enemies"), default=[]))
    enemy_rows = []
    for index, raw in enumerate(enemies, 1):
        enemy = _mapping(raw)
        name = _pick(enemy, keys=("name", "id", "monsterId"), default=f"target {index}")
        hp = _pick(enemy, keys=("current_hp", "currentHp", "curHp", "hp"))
        maximum = _pick(enemy, keys=("max_hp", "maxHp", "maxHealth"))
        intent = _pick(enemy, keys=("intent", "move", "moveName", "nextMove"))
        damage = _pick(enemy, keys=("intended_damage", "intendedDamage", "intentDamage", "damage", "moveDamage"))
        hp_text = f"{_value(hp)}/{_value(maximum,)}" if maximum is not None else _value(hp)
        enemy_rows.append(f"<tr><td>{index}</td><td>{_value(name)}</td><td>{hp_text}</td>"
                          f"<td>{_value(_pick(enemy, keys=('block', 'current_block')))}</td>"
                          f"<td>{_value(intent)}</td><td>{_value(damage)}</td></tr>")
    enemy_html = ("<table><thead><tr><th>#</th><th>enemy / id</th><th>HP</th><th>block</th>"
                  "<th>intent / move</th><th>intended damage</th></tr></thead><tbody>"
                  + "".join(enemy_rows) + "</tbody></table>") if enemies else '<p class="muted">enemies not captured</p>'
    hand = _list(state.get("hand"))
    hand_rows = []
    for raw in hand:
        card = _mapping(raw)
        hand_rows.append(f"<tr><td>{_value(_pick(card, keys=('name', 'id', 'card_id')))}</td>"
                         f"<td>{_value(_pick(card, keys=('uuid', 'unique_id', 'uniqueId')))}</td>"
                         f"<td>{_value(_pick(card, keys=('upgrade', 'upgraded', 'timesUpgraded')))}</td>"
                         f"<td>{_value(_pick(card, keys=('costForTurn', 'current_cost', 'currentCost', 'cost')))}</td></tr>")
    hand_html = ("<table><thead><tr><th>card</th><th>physical UUID</th><th>upgrade</th><th>cost</th></tr></thead><tbody>"
                 + "".join(hand_rows) + "</tbody></table>") if hand else '<p class="muted">hand not captured</p>'
    pile_names = (("draw", "draw", "draw_pile", "drawPile"),
                  ("discard", "discard", "discard_pile", "discardPile"),
                  ("exhaust", "exhaust", "exhaust_pile", "exhaustPile"))
    pile_html = "".join(f"<div class=\"state-chip\"><span>{_esc(label)}</span><b>{_value(_pile_value(state, keys))}</b></div>"
                        for label, *keys in pile_names)
    potions = _list(state.get("potions"))
    relics = _list(state.get("relics"))
    extras = f"<div class=\"columns\"><div><h3>potions</h3><pre>{_pretty(potions) if potions else 'not captured'}</pre></div>"
    extras += f"<div><h3>relics</h3><pre>{_pretty(relics) if relics else 'not captured'}</pre></div></div>"
    return (
        f"<section><h2>Combat state</h2><h3>player</h3><div class=\"chips\">{player_html}</div>"
        f"<h3>enemies</h3>{enemy_html}<h3>hand</h3>{hand_html}<h3>piles</h3><div class=\"chips\">{pile_html}</div>{extras}</section>"
    )


def _pile_value(state: Mapping[str, Any], keys: Sequence[str]) -> Any:
    value = _pick(state, keys=keys)
    if isinstance(value, list):
        return len(value)
    return value


def _root_section(source: Mapping[str, Any]) -> str:
    evaluator = _mapping(source.get("evaluator"))
    summaries = _list(evaluator.get("rootActionSummaries"))
    selected = evaluator.get("selectedAction")
    if not summaries:
        status = evaluator.get("status", "not captured")
        reason = evaluator.get("reason", "not captured")
        legal = source.get("legal_actions") or evaluator.get("legalActions")
        legal_html = _pretty(legal) if legal else "not captured"
        return (
            f"<section><h2>Root action ranking</h2><div class=\"status\">status: {_esc(status)}</div>"
            f"<p>reason: {_esc(reason)}</p><h3>legal actions</h3><pre>{legal_html}</pre></section>"
        )
    rows = []
    for rank, item in enumerate(summaries, 1):
        action = _mapping(item)
        fingerprint = action.get("fingerprint", action.get("semanticFingerprint"))
        is_selected = fingerprint == selected
        raw_share = action.get("visitShare")
        valid_share = (isinstance(raw_share, (int, float)) and not isinstance(raw_share, bool)
                       and math.isfinite(float(raw_share)))
        bar_share = max(0.0, min(1.0, float(raw_share))) if valid_share else 0.0
        share_text = _value(raw_share) if raw_share is not None else "not captured"
        q_valid = action.get("selectionQValid") is True and "selectionQ" in action
        q = _value(action.get("selectionQ")) if q_valid else "unvisited / Q unavailable"
        live = action.get("liveAction")
        klass = "selected-action" if is_selected else ""
        marker = "✓ selected" if is_selected else ""
        rows.append(f"<tr class=\"{klass}\"><td>{rank}</td><td>{_esc(marker)}</td>"
                    f"<td><strong>{_value(action.get('label', fingerprint))}</strong><br><code>{_esc(fingerprint)}</code></td>"
                    f"<td class=\"visits\">{_value(action.get('edgeVisits'))}</td>"
                    f"<td><div class=\"share\"><span>{share_text}</span><i style=\"width:{bar_share * 100:.3f}%\"></i></div></td>"
                    f"<td>{q}</td><td><pre>{_pretty(live) if live is not None else 'not captured'}</pre></td></tr>")
    return ("<section><h2>Root action ranking</h2><table class=\"ranking\"><thead><tr>"
            "<th>#</th><th></th><th>action</th><th>visits</th><th>share</th><th>Q</th><th>live action</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></section>")


def _diagnostics(source: Mapping[str, Any]) -> str:
    evaluator = _mapping(source.get("evaluator"))
    reroot = _mapping(evaluator.get("reroot"))
    values = [("status", evaluator.get("status")), ("reason", evaluator.get("reason")),
              ("exact reroot", reroot.get("exact")), ("equivalent-copy reroot", reroot.get("equivalentCopy")),
              ("fallback", reroot.get("fallback")), ("fallback reason", reroot.get("fallbackReason")),
              ("inherited visits", reroot.get("inheritedVisits")), ("root visits", evaluator.get("rootVisits")),
              ("simulations added", evaluator.get("additionalSimulations")),
              ("total simulations", evaluator.get("totalSimulations", evaluator.get("simulations")))]
    rows = "".join(f"<tr><th>{_esc(label)}</th>{_cell(value)}</tr>" for label, value in values)
    return f"<section><h2>Search diagnostics</h2><table class=\"diagnostics\">{rows}</table></section>"


def _lowering(source: Mapping[str, Any]) -> str:
    evaluator = _mapping(source.get("evaluator"))
    matched = source.get("matched")
    executed = source.get("executed")
    selected = evaluator.get("selectedAction")
    live = evaluator.get("selectedLiveAction")
    matched_value = matched if matched else "not captured"
    executed_value = executed if executed else "not captured"
    return ("<section><h2>Action lowering / execution</h2><div class=\"chain\">"
            f"<div><label>Silver semantic action</label><code>{_esc(selected)}</code></div><b>→</b>"
            f"<div><label>selectedLiveAction</label><pre>{_pretty(live) if live is not None else 'not captured'}</pre></div><b>→</b>"
            f"<div><label>matched live-driver candidate</label><pre>{_pretty(matched_value)}</pre></div><b>→</b>"
            f"<div><label>executed MCP command</label><pre>{_pretty(executed_value)}</pre></div></div></section>")


def _diff_values(before: Any, after: Any, path: str = "") -> list[tuple[str, Any, Any]]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        result: list[tuple[str, Any, Any]] = []
        for key in sorted(set(before) | set(after), key=str):
            child = f"{path}.{key}" if path else str(key)
            if key not in before:
                result.append((child, "<missing>", after[key]))
            elif key not in after:
                result.append((child, before[key], "<missing>"))
            else:
                result.extend(_diff_values(before[key], after[key], child))
        return result
    if isinstance(before, list) and isinstance(after, list):
        result = []
        if len(before) != len(after):
            result.append((path + ".length", len(before), len(after)))
        for index, (left, right) in enumerate(zip(before, after)):
            result.extend(_diff_values(left, right, f"{path}[{index}]"))
        return result
    return [] if before == after and type(before) is type(after) else [(path or "$", before, after)]


def _before_after(source: Mapping[str, Any]) -> str:
    before = source.get("before")
    after = source.get("after")
    if not isinstance(after, Mapping):
        return '<section><h2>Before → after</h2><p class="muted">after state not captured; no historical state was guessed</p></section>'
    if not isinstance(before, Mapping) or not before:
        return '<section><h2>Before → after</h2><p class="muted">before state not captured; showing post-action state only</p></section>'
    diffs = _diff_values(before, after)
    rows = "".join(f"<tr><td><code>{_esc(path)}</code></td><td><pre>{_pretty(left)}</pre></td><td><pre>{_pretty(right)}</pre></td></tr>"
                   for path, left, right in diffs[:200])
    body = ("<p class=\"muted\">no changed fields</p>" if not rows else
            "<table><thead><tr><th>field</th><th>before</th><th>after</th></tr></thead><tbody>" + rows + "</tbody></table>")
    return f"<section><h2>Before → after</h2>{body}</section>"




def _asset(name: str) -> str:
    return (Path(__file__).parent / "combat_graph_viewer" / name).read_text(encoding="utf-8")


def _inline_script(value: str) -> str:
    return value.replace("</", "<\\/").replace("<!--", "<\\!--")


def _workspace(source: Mapping[str, Any]) -> str:
    evaluator = _mapping(source.get("evaluator"))
    tree = _mapping(evaluator.get("tree"))
    if not tree or not tree.get("accepted"):
        reason = tree.get("failureReason") or "Silver graph not captured; enable opt-in debug capture."
        return f'<section><h2>Retained graph unavailable</h2><p>{_esc(reason)}</p></section>'
    # Browser JSON numbers cannot represent all native 64-bit IDs and hashes.
    copied_tree = dict(tree)
    copied_tree["rootId"] = str(tree.get("rootId"))
    copied_tree["nodes"] = [dict(n, id=str(n["id"]),
                                  stateHash=str(n["stateHash"]) if n.get("stateHash") is not None else None)
                            for n in _list(tree.get("nodes"))]
    copied_tree["edges"] = [dict(e, parentId=str(e["parentId"]),
                                  childId=str(e["childId"]) if e.get("childId") is not None else None)
                            for e in _list(tree.get("edges"))]
    payload = _inline_script(json.dumps({"evaluator": dict(evaluator, tree=copied_tree),
                                          "observation": source.get("observation", {})},
                                         ensure_ascii=True, separators=(",", ":")))
    scripts = ("<script id=\"elk-library\">" +
               _inline_script(_asset("vendor/elk.bundled.js")) + "</script>")
    scripts += "<script>" + _inline_script(_asset("vendor/d3.min.js")) + "</script>"
    scripts += "<script>window.__COMBAT_VIEWER__=" + payload + ";</script>"
    scripts += ("<script>window.__RAW_RECORD__=" +
                _inline_script(json.dumps(source.get("raw", {}), ensure_ascii=True,
                                          separators=(",", ":"))) + ";</script>")
    scripts += "".join("<script>" + _inline_script(_asset(name)) + "</script>"
                       for name in ("normalize.js", "visibility.js", "layout.js",
                                    "render.js", "inspector.js", "app.js"))
    return (
        '<header><b id="encounter"></b><span id="simulations"></span><strong id="choice"></strong>'
        '<span id="capture"></span><span class="spacer"></span>'
        '<button id="fullscreen" type="button">Graph only</button></header>'
        '<div class="workspace"><aside class="sidebar"><h2>Root actions</h2>'
        '<div id="root-actions"></div><label for="root-filter">Filter canvas to root action</label>'
        '<select id="root-filter"><option value="">All captured actions</option></select>'
        '<label for="search">Search ID, hash, action or fingerprint</label>'
        '<input id="search" type="search" placeholder="Search capture">'
        '<div id="search-results" class="search-results"></div></aside>'
        '<div class="graph-column" id="graph-area"><div class="graph-tools">'
        '<button id="back" type="button">Back</button><button id="focus" type="button">Focus here</button>'
        '<button id="root" type="button">Return to root</button>'
        '<button id="zoom-out" type="button">−</button><button id="zoom-in" type="button">+</button>'
        '<button id="fit" type="button">Fit visible</button>'
        '<span id="breadcrumb" class="breadcrumb">Root</span>'
        '<label>Depth <input id="depth" type="number" min="1" value="3"></label>'
        '<label>Top-K <input id="top-k" type="number" min="1" value="4"></label>'
        '<label>Min visits <input id="min-visits" type="number" min="0" value="0"></label>'
        '<label>Direction <select id="direction"><option value="RIGHT">Left → right</option>'
        '<option value="DOWN">Top → bottom</option></select></label></div>'
        '<div class="graph-stage"><svg id="graph" aria-label="Silver retained-search graph"></svg>'
        '<span id="layout-status" class="layout-status" role="status"></span>'
        '<svg id="minimap" class="minimap" aria-label="Clickable graph overview"></svg></div>'
        '<div class="graph-footer" id="visible-count"></div></div>'
        '<aside class="inspector"><h2>Inspector</h2><div id="inspector-content"></div></aside></div>'
        '<nav class="tabs"><button data-tab="details" class="active">Details</button>'
        '<button data-tab="execution">Execution</button><button data-tab="raw">Raw data</button></nav>'
        '<div class="details-panel" data-panel="details">' + _header(source) + _combat_section(source)
        + _diagnostics(source) + _root_section(source) + '</div>'
        '<div class="details-panel" data-panel="execution" hidden>' + _lowering(source)
        + _before_after(source) + '</div>'
        '<div class="details-panel" data-panel="raw" hidden>'
        '<details data-raw="observation"><summary>Raw observation</summary><pre></pre></details>'
        '<details data-raw="evaluator"><summary>Raw Silver evaluator</summary><pre></pre></details>'
        '<details data-raw="original"><summary>Original capture record</summary><pre></pre></details>'
        '</div>' + scripts
    )


def render_html(source: Mapping[str, Any]) -> str:
    raw = source.get("raw", {})
    evaluator = source.get("evaluator", {})
    if _mapping(_mapping(source.get("evaluator")).get("tree")).get("accepted"):
        return ("<!doctype html><html><head><meta charset=\"utf-8\"><title>Silver graph</title><style>"
                + _asset("style.css") + _asset("overrides.css") + "</style></head><body>"
                + _workspace(source) + "</body></html>")
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Combat decision</title><style>"
        + _CSS + "</style></head><body><main><h1>Combat decision inspector</h1>"
        + _header(source) + '<section><h2>Retained graph unavailable</h2><p>'
        + _esc(_mapping(_mapping(evaluator).get("tree")).get("failureReason") or
               "Silver debug capture was not enabled for this decision.") + '</p></section>'
        + _combat_section(source) + _root_section(source)
        + _diagnostics(source) + _lowering(source) + _before_after(source)
        + f"<section><h2>Raw data</h2><details><summary>raw observation</summary><pre>{_pretty(source.get('observation', {}))}</pre></details>"
        + f"<details><summary>raw Silver evaluator</summary><pre>{_pretty(evaluator)}</pre></details>"
        + f"<details><summary>selected trace / differential row</summary><pre>{_pretty(raw)}</pre></details></section>"
        + "</main></body></html>"
    )


_CSS = """
:root { color-scheme: dark; --bg:#101318; --panel:#191e27; --line:#303948; --text:#e9edf3; --muted:#9ca8b8; --accent:#72b7ff; --selected:#284d38; }
* { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--text); font:14px/1.45 system-ui,sans-serif; }
main { max-width:1500px; margin:0 auto; padding:24px; } h1 { margin:0 0 16px; font-size:24px; } h2 { margin:0 0 14px; font-size:18px; } h3 { color:var(--muted); font-size:13px; text-transform:uppercase; letter-spacing:.08em; margin:18px 0 8px; }
section { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:16px; margin:14px 0; overflow:auto; } .metrics { display:grid; grid-template-columns:repeat(auto-fit,minmax(125px,1fr)); gap:8px; }
.metric,.state-chip { background:#11161d; border:1px solid var(--line); border-radius:7px; padding:8px 10px; } .metric span,.state-chip span,label { display:block; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; } .metric strong,.state-chip b { display:block; margin-top:3px; font-size:15px; }
.selected-summary { margin-top:12px; padding:10px; border-left:3px solid #6ee7a2; background:#14271e; } code,pre { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; } code { overflow-wrap:anywhere; } pre { margin:4px 0; white-space:pre-wrap; overflow-wrap:anywhere; color:#cbd5e1; }
table { width:100%; border-collapse:collapse; } th,td { text-align:left; vertical-align:top; border-bottom:1px solid var(--line); padding:8px; } th { color:var(--muted); font-size:12px; } .selected-action { background:var(--selected); box-shadow:inset 3px 0 #6ee7a2; } .visits { font-weight:600; white-space:nowrap; }
.share { min-width:130px; } .share i { display:block; height:6px; margin-top:5px; background:var(--accent); border-radius:5px; min-width:1px; } .chips { display:flex; flex-wrap:wrap; gap:8px; } .columns { display:grid; grid-template-columns:1fr 1fr; gap:12px; } .muted { color:var(--muted); }
.status { display:inline-block; padding:5px 9px; border-radius:5px; background:#3a2f16; color:#ffd47a; } .chain { display:grid; grid-template-columns:1fr auto 1fr auto 1fr auto 1fr; gap:10px; align-items:center; } .chain > div { min-width:0; background:#11161d; border:1px solid var(--line); padding:10px; border-radius:7px; } .chain > b { color:var(--accent); font-size:20px; } details { margin:8px 0; } summary { cursor:pointer; color:var(--accent); }
.debug-badge { color:#ffd47a; border:1px solid #846b2e; border-radius:4px; padding:2px 6px; font-size:10px; text-transform:uppercase; letter-spacing:.06em; vertical-align:middle; } .tree-toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-bottom:14px; } .tree-toolbar select { background:#11161d; color:var(--text); border:1px solid var(--line); border-radius:5px; padding:6px; } .tree-toolbar input { accent-color:var(--accent); } .tree-view { overflow:auto; padding:4px 0; } .tree-node { margin:7px 0 7px 14px; padding-left:10px; border-left:1px solid #465266; } .tree-node > summary { list-style:disclosure-closed; } .tree-node[open] > summary { list-style:disclosure-open; } .tree-node-title { color:#d9e7ff; font-weight:600; } .tree-node-meta { display:flex; flex-wrap:wrap; gap:7px; margin:6px 0 8px 20px; color:var(--muted); font:11px ui-monospace,SFMono-Regular,Menlo,monospace; } .tree-node-meta span { background:#11161d; border:1px solid var(--line); border-radius:4px; padding:3px 6px; } .tree-edges { margin-left:12px; } .tree-edge { margin:7px 0; padding-left:12px; border-left:2px solid #365276; } .tree-edge-label { color:#f0c674; } .tree-fingerprint { display:block; color:var(--muted); font-size:11px; margin-top:2px; } .tree-reference { display:block; color:#e2a7a7; font-size:12px; margin:4px 0; } .tree-state { margin:8px 0 8px 20px; } .tree-state summary { font-size:12px; } .tree-state pre { max-height:360px; overflow:auto; background:#0d1117; border:1px solid var(--line); padding:10px; } .tree-filtered { border-left:2px solid #6ee7a2; padding-left:12px; } .tree-graph-shell { margin:16px 0 20px; } .tree-graph-toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:8px 0; } .tree-graph-toolbar button { background:#11161d; color:var(--text); border:1px solid var(--line); border-radius:5px; padding:5px 9px; } .tree-graph-toolbar input { accent-color:var(--accent); } .tree-graph-viewport { height:680px; overflow:hidden; background:#0d1117; border:1px solid var(--line); border-radius:7px; touch-action:none; } #tree-graph-svg { display:block; width:100%; height:100%; user-select:none; } .graph-arrow { fill:#7890ad; } .graph-edge { fill:none; stroke:#4d6b8f; stroke-width:1.2; opacity:.6; } .graph-edge.chance { stroke:#a47e49; stroke-dasharray:4 3; } .graph-edge.decision { stroke:#4d8b70; } .graph-edge-label { fill:#c6d3e3; font:10px ui-monospace,SFMono-Regular,Menlo,monospace; pointer-events:none; } .graph-node rect { fill:#1d344b; stroke:#72b7ff; stroke-width:1.2; } .graph-node.chance rect { fill:#493820; stroke:#d6a15d; } .graph-node.leaf rect { fill:#244d3c; stroke:#6ee7a2; } .graph-node.selected rect { stroke:#fff; stroke-width:2.5; } .graph-node-id,.graph-node-q { fill:#e9edf3; font:11px ui-monospace,SFMono-Regular,Menlo,monospace; pointer-events:none; } .graph-details-meta { display:flex; flex-wrap:wrap; gap:7px; margin:8px 0; color:var(--muted); font:11px ui-monospace,SFMono-Regular,Menlo,monospace; } .graph-details-meta span { background:#11161d; border:1px solid var(--line); border-radius:4px; padding:3px 6px; } .graph-details ul { margin:6px 0; padding-left:22px; max-height:220px; overflow:auto; } .graph-details pre { max-height:300px; overflow:auto; background:#0d1117; border:1px solid var(--line); padding:10px; }
@media (max-width:900px) { .columns,.chain { grid-template-columns:1fr; } .chain > b { transform:rotate(90deg); justify-self:center; } }
"""


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--snapshot", type=Path, help="inspector latest.json")
    source.add_argument("--trace", type=Path, help="live-driver JSONL trace")
    source.add_argument("--differential-trace", type=Path, help="versioned differential JSONL trace")
    parser.add_argument("--step", type=int, help="normal live-driver decision step (with --trace)")
    parser.add_argument("--decision", type=int, help="differential decision index (with --differential-trace)")
    parser.add_argument("--output", type=Path, required=True, help="standalone HTML output path")
    parser.add_argument("--open", action="store_true", help="open the generated file with the default browser")
    args = parser.parse_args(argv)
    if args.trace is not None and args.step is None:
        parser.error("--trace requires --step")
    if args.differential_trace is not None and args.decision is None:
        parser.error("--differential-trace requires --decision")
    if args.snapshot is not None and (args.step is not None or args.decision is not None):
        parser.error("--snapshot does not take --step or --decision")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        if args.snapshot is not None:
            source = load_snapshot(args.snapshot)
        elif args.trace is not None:
            source = load_trace(args.trace, args.step)
        else:
            source = load_differential_trace(args.differential_trace, args.decision)
        args.output.write_text(render_html(source), encoding="utf-8")
        if args.open:
            webbrowser.open(args.output.resolve().as_uri())
        return 0
    except RenderError as error:
        print(f"render_combat_decision: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"render_combat_decision: cannot write output: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
