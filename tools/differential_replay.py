#!/usr/bin/env python3
"""Replay a differential trace through a native JSONL adapter.

The adapter receives one decision record and returns one object containing
state, legalActions, and optional rng. It must not synchronize native RNG to
Java; it only reports its current state for diagnostics.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any, Mapping

try:
    from tools.differential_trace import (DifferentialTraceError, compare_legal_actions,
                                          compare_states, read_trace, resolve_unique_action)
except ModuleNotFoundError:  # direct invocation: python tools/differential_replay.py
    from differential_trace import (DifferentialTraceError, compare_legal_actions,
                                    compare_states, read_trace, resolve_unique_action)


def replay(trace: Path, native_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    try:
        rows = read_trace(trace)
    except (OSError, DifferentialTraceError) as error:
        return {"category": "TRACE_OR_SCHEMA_ERROR", "reason": str(error)}
    decisions = [row for row in rows if row.get("record_type") == "decision"]
    if not decisions:
        return {"category": "TRACE_OR_SCHEMA_ERROR", "decisionCount": 0,
                "reason": "no_decisions_captured"}
    for index, decision in enumerate(decisions):
        trace_error = decision.get("traceError")
        if isinstance(trace_error, Mapping):
            return {"category": trace_error.get("category", "UNSUPPORTED_BOUNDARY"),
                    "decisionIndex": decision.get("decisionIndex"),
                    "reason": trace_error.get("reason", "unspecified trace boundary")}
        if index >= len(native_rows):
            return {"category": "TRACE_OR_SCHEMA_ERROR",
                    "decisionIndex": decision.get("decisionIndex"),
                    "reason": "native adapter ended before trace"}
        native = native_rows[index]
        native_error = native.get("traceError")
        if isinstance(native_error, Mapping):
            return {"category": native_error.get("category", "UNSUPPORTED_BOUNDARY"),
                    "decisionIndex": decision.get("decisionIndex"),
                    "reason": native_error.get("reason", "native replay stopped")}
        boundary = decision.get("boundary")
        if boundary not in {"combat", "ooc"}:
            return {"category": "UNSUPPORTED_BOUNDARY", "decisionIndex": decision.get("decisionIndex"),
                    "reason": f"boundary={boundary!r}"}
        state = native.get("state")
        if state is None:
            return {"category": "TRACE_OR_SCHEMA_ERROR", "decisionIndex": decision.get("decisionIndex"),
                    "reason": "native row has no state"}
        state_result = compare_states(
            decision.get("before"), state, java_rng=decision.get("preRng"),
            native_rng=native.get("rng"), state_before_equal=True,
            action=decision.get("selectedAction", {}).get("identity"))
        if state_result["category"] != "EQUIVALENT":
            return {"decisionIndex": decision.get("decisionIndex"), **state_result}
        legal = compare_legal_actions(decision.get("legalActions", []),
                                      native.get("legalActions", []), boundary)
        if legal["category"] != "EQUIVALENT":
            return {"decisionIndex": decision.get("decisionIndex"), **legal}
        identity = decision.get("selectedAction", {}).get("identity")
        try:
            resolve_unique_action(identity, native.get("legalActions", []), boundary)
        except DifferentialTraceError as error:
            return {"category": str(error), "decisionIndex": decision.get("decisionIndex"),
                    "recordedIdentity": identity}
        if "after" not in native:
            return {"category": "TRACE_OR_SCHEMA_ERROR", "decisionIndex": decision.get("decisionIndex"),
                    "reason": "native adapter has no post-action state"}
        after_result = compare_states(decision.get("after"), native.get("after"),
                                      java_rng=decision.get("postRng"),
                                      native_rng=native.get("postRng"),
                                      state_before_equal=True, action=identity)
        if after_result["category"] != "EQUIVALENT":
            return {"decisionIndex": decision.get("decisionIndex"), **after_result}
    if len(native_rows) != len(decisions):
        return {"category": "TRACE_OR_SCHEMA_ERROR", "reason": "native adapter returned extra rows"}
    outcome = rows[-1].get("outcome")
    if outcome == "max_steps":
        return {"category": "BOUNDED_PREFIX_EQUIVALENT", "decisionCount": len(decisions)}
    if outcome in {"victory", "death", "run_complete"}:
        # Terminal capture currently has no qualified cross-runtime schema.
        return {"category": "UNSUPPORTED_BOUNDARY", "reason": "terminal_state_unqualified"}
    return {"category": "TRACE_OR_SCHEMA_ERROR",
            "reason": f"capture did not complete successfully: {outcome!r}"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--native-jsonl", type=Path)
    parser.add_argument("--native-command")
    args = parser.parse_args(argv)
    try:
        if args.native_jsonl:
            with args.native_jsonl.open(encoding="utf-8") as handle:
                native_rows = [json.loads(line) for line in handle if line.strip()]
        elif args.native_command:
            rows = read_trace(args.trace)
            proc = subprocess.run(
                shlex.split(args.native_command),
                input="".join(json.dumps(row) + "\n" for row in rows),
                text=True, capture_output=True, check=False)
            if proc.returncode:
                raise DifferentialTraceError(f"native adapter exit {proc.returncode}: {proc.stderr.strip()}")
            native_rows = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        else:
            parser.error("one of --native-jsonl or --native-command is required")
        result = replay(args.trace, native_rows)
    except (OSError, ValueError, DifferentialTraceError) as error:
        result = {"category": "TRACE_OR_SCHEMA_ERROR", "reason": str(error)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["category"] == "BOUNDED_PREFIX_EQUIVALENT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
