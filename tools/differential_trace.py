#!/usr/bin/env python3
"""Versioned trace and fail-closed comparison primitives for Java/native parity.

This module is deliberately independent of Silver and OOC policy code. It
owns only the debug trace boundary: canonical semantic action identities,
stable-state normalization, deterministic field diffs, and JSONL framing.
Hidden RNG is accepted only below debugRng and is never part of a public
observation.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA = "sts_differential_trace"
SCHEMA_VERSION = 1
RECORD_TYPES = {"header", "decision", "summary"}
RNG_KEY = "debugRng"

_TRANSIENT_KEYS = {
    "ready_for_command", "readyForCommand", "timestamp", "latencyMicros",
    "waitMicros", "driverStepMicros", "mcp_action_micros", "post_action_wait_micros",
    "session", "sequence", "observationHash", "inspector_session",
    "inspector_sequence", "inspector_observationHash", "inspector_wait_micros",
}


class DifferentialTraceError(ValueError):
    """Malformed trace or non-unique semantic replay identity."""


@dataclass(frozen=True)
class FieldDiff:
    path: str
    expected: Any
    actual: Any

    def json(self) -> dict[str, Any]:
        return {"path": self.path, "java": self.expected, "native": self.actual}


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _canonical(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_state(value: Any, *, include_debug_rng: bool = True) -> Any:
    """Remove UI/correlation noise while preserving semantic ordering."""
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            key = str(key)
            if key in _TRANSIENT_KEYS:
                continue
            if key == RNG_KEY and not include_debug_rng:
                continue
            result[key] = normalize_state(item, include_debug_rng=include_debug_rng)
        return result
    if isinstance(value, (list, tuple)):
        return [normalize_state(item, include_debug_rng=include_debug_rng) for item in value]
    return value


def _diff(expected: Any, actual: Any, path: str, out: list[FieldDiff]) -> None:
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        for key in sorted(set(expected) | set(actual), key=str):
            child = f"{path}.{key}" if path else str(key)
            if key not in expected:
                out.append(FieldDiff(child, "<missing>", actual[key]))
            elif key not in actual:
                out.append(FieldDiff(child, expected[key], "<missing>"))
            else:
                _diff(expected[key], actual[key], child, out)
        return
    if isinstance(expected, Sequence) and not isinstance(expected, (str, bytes)) \
            and isinstance(actual, Sequence) and not isinstance(actual, (str, bytes)):
        if len(expected) != len(actual):
            out.append(FieldDiff(path + ".length", len(expected), len(actual)))
        for index, (left, right) in enumerate(zip(expected, actual)):
            _diff(left, right, f"{path}[{index}]", out)
        return
    if expected != actual or type(expected) is not type(actual):
        out.append(FieldDiff(path or "$", expected, actual))


def field_diffs(expected: Any, actual: Any, *, include_debug_rng: bool = True) -> list[FieldDiff]:
    result: list[FieldDiff] = []
    _diff(normalize_state(expected, include_debug_rng=include_debug_rng),
          normalize_state(actual, include_debug_rng=include_debug_rng), "", result)
    return result


def compare_states(java: Any, native: Any, *, java_rng: Any = None, native_rng: Any = None,
                   state_before_equal: bool = False, action: Any = None) -> dict[str, Any]:
    """Return a structured result; never guesses through a mismatch."""
    diffs = field_diffs(java, native, include_debug_rng=False)
    if not diffs and java_rng is not None and native_rng is not None:
        # drawPileUuids is pile order for the parity probe, not an RNG stream.
        if isinstance(java_rng, Mapping):
            java_rng = {k: v for k, v in java_rng.items() if k != "drawPileUuids"}
        rng_diffs = field_diffs({RNG_KEY: java_rng}, {RNG_KEY: native_rng})
        if rng_diffs and state_before_equal:
            return {"category": "RNG_CONSUMPTION_DIVERGENCE", "diffs": [d.json() for d in rng_diffs],
                    "javaRng": java_rng, "nativeRng": native_rng, "action": action}
    if diffs:
        return {"category": "STATE_DIVERGENCE", "diffs": [d.json() for d in diffs], "action": action}
    return {"category": "EQUIVALENT", "diffs": []}


def combat_action_identity(action: Mapping[str, Any]) -> str:
    fingerprint = action.get("silver_fingerprint") or action.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise DifferentialTraceError("combat action has no canonical Silver fingerprint")
    return "silver:" + fingerprint


def ooc_action_identity(action: Mapping[str, Any]) -> str:
    semantic_key = action.get("semanticKey") or action.get("semantic_key")
    if isinstance(semantic_key, str) and semantic_key:
        return semantic_key
    semantic = action.get("semantic")
    if isinstance(semantic, Mapping):
        semantic_key = semantic.get("semanticKey") or semantic.get("key")
        if isinstance(semantic_key, str) and semantic_key:
            return semantic_key
        if semantic.get("kind") == "map" and isinstance(semantic.get("x"), int) and isinstance(semantic.get("y"), int):
            return f"map:x={semantic['x']}:y={semantic['y']}"
    raise DifferentialTraceError("OOC action has no canonical semantic key")


def action_identity(action: Mapping[str, Any], boundary: str) -> str:
    return combat_action_identity(action) if boundary == "combat" else ooc_action_identity(action)


def resolve_unique_action(recorded_identity: str, legal_actions: Iterable[Mapping[str, Any]], boundary: str) -> Mapping[str, Any]:
    matches = []
    for action in legal_actions:
        try:
            if action_identity(action, boundary) == recorded_identity:
                matches.append(action)
        except DifferentialTraceError:
            continue
    if not matches:
        raise DifferentialTraceError("RECORDED_ACTION_NOT_FOUND")
    if len(matches) != 1:
        raise DifferentialTraceError("RECORDED_ACTION_AMBIGUOUS")
    return matches[0]


def compare_legal_actions(recorded: Iterable[Mapping[str, Any]], native: Iterable[Mapping[str, Any]], boundary: str) -> dict[str, Any]:
    def identities(actions: Iterable[Mapping[str, Any]]) -> list[str]:
        return sorted(action_identity(a, boundary) for a in actions)
    try:
        java_ids, native_ids = identities(recorded), identities(native)
    except DifferentialTraceError as error:
        return {"category": "TRACE_OR_SCHEMA_ERROR", "reason": str(error)}
    if java_ids != native_ids:
        return {"category": "LEGAL_ACTION_SET_DIVERGENCE",
                "javaOnly": sorted(set(java_ids) - set(native_ids)),
                "nativeOnly": sorted(set(native_ids) - set(java_ids))}
    return {"category": "EQUIVALENT", "identities": java_ids}


class DifferentialTraceWriter:
    """Append-only JSONL writer with deterministic framing."""

    def __init__(self, path: Path, *, run_id: str | None = None, provenance: Mapping[str, Any] | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or uuid.uuid4().hex
        self.provenance = dict(provenance or {})
        self.rows: list[dict[str, Any]] = []
        self.path.write_text("", encoding="utf-8")
        self._write({"record_type": "header", "schema": SCHEMA, "schemaVersion": SCHEMA_VERSION,
                     "traceId": self.run_id, "provenance": self.provenance})

    def _write(self, row: Mapping[str, Any]) -> None:
        value = _canonical(dict(row))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        self.rows.append(value)

    def write_decision(self, row: Mapping[str, Any], *, boundary: str) -> None:
        before = row.get("pre_action_state", row.get("observed_state", {}))
        after = row.get("post_action_state", {})
        selected = row.get("selected_candidate_trace", row.get("selected_candidate", {}))
        if not isinstance(selected, Mapping):
            selected = {"id": selected}
        identity = row.get("semantic_action_identity") or action_identity(selected, boundary)
        self._write({
            "record_type": "decision", "schema": SCHEMA, "schemaVersion": SCHEMA_VERSION,
            "traceId": self.run_id, "decisionIndex": row.get("step"), "boundary": boundary,
            "seed": row.get("seed"), "act": row.get("act"), "floor": row.get("floor"),
            "before": normalize_state(before),
            "legalActions": row.get("differential_legal_actions", []),
            "selectedAction": {"identity": identity, "action": selected},
            "mcpAction": {"tool": row.get("executed_mcp_tool", row.get("selected_mcp_tool")),
                          "arguments": row.get("executed_mcp_arguments", row.get("selected_mcp_arguments", {}))},
            "after": normalize_state(after),
            "liveObservation": row.get("live_observation"),
            "preRng": row.get("preRng"), "postRng": row.get("postRng"),
            "runtime": row.get("runtime_provenance"),
            "oocPolicy": row.get("ooc_policy") or self.provenance.get("oocPolicy"),
            "oocSelectionMode": row.get("ooc_selection_mode", "policy"),
            "provenance": self.provenance,
        })

    def write_summary(self, summary: Mapping[str, Any]) -> None:
        decisions = [row for row in self.rows if row.get("record_type") == "decision"]
        self._write({"record_type": "summary", "schema": SCHEMA, "schemaVersion": SCHEMA_VERSION,
                     "traceId": self.run_id, **dict(summary), "decisionCount": len(decisions),
                     "traceSha256": sha256_json(self.rows)})


def read_trace(path: Path) -> list[dict[str, Any]]:
    rows = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise DifferentialTraceError(f"line {line_number}: invalid JSON: {error}") from error
            if not isinstance(row, dict) or row.get("record_type") not in RECORD_TYPES:
                raise DifferentialTraceError(f"line {line_number}: invalid record_type")
            if row.get("schema") != SCHEMA or row.get("schemaVersion") != SCHEMA_VERSION:
                raise DifferentialTraceError(f"line {line_number}: unsupported differential schema")
            rows.append(row)
    if not rows or rows[0].get("record_type") != "header":
        raise DifferentialTraceError("trace has no header")
    if rows[-1].get("record_type") != "summary":
        raise DifferentialTraceError("trace has no closing summary")
    trace_id = rows[0].get("traceId")
    if not isinstance(trace_id, str) or not trace_id:
        raise DifferentialTraceError("trace has no identity")
    previous_index = -1
    for row in rows[1:-1]:
        if row.get("record_type") != "decision":
            raise DifferentialTraceError("trace contains misplaced header or summary")
        index = row.get("decisionIndex")
        if type(index) is not int or index <= previous_index:
            raise DifferentialTraceError("decision indices must be strictly increasing")
        previous_index = index
    if any(row.get("traceId") != trace_id for row in rows):
        raise DifferentialTraceError("trace identity mismatch")
    summary = rows[-1]
    if type(summary.get("decisionCount")) is not int or summary["decisionCount"] != len(rows) - 2:
        raise DifferentialTraceError("summary decision count mismatch")
    if summary.get("traceSha256") != sha256_json(rows[:-1]):
        raise DifferentialTraceError("summary trace hash mismatch")
    return rows
