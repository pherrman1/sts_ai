#!/usr/bin/env python3
"""One native decision captured from native state must replay exactly."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.differential_replay import replay
from tools.differential_trace import DifferentialTraceWriter


def adapter(binary: Path, identity: str) -> dict:
    rows = [
        {"record_type": "header", "schema": "sts_differential_trace", "schemaVersion": 1,
         "traceId": "native-self", "provenance": {"seed": "0", "ascension": 0}},
        {"record_type": "decision", "schema": "sts_differential_trace", "schemaVersion": 1,
         "traceId": "native-self", "decisionIndex": 0, "seed": "0", "boundary": "ooc",
         "selectedAction": {"identity": identity}},
    ]
    process = subprocess.run([str(binary), "differentialreplay"],
                             input="".join(json.dumps(row) + "\n" for row in rows),
                             text=True, capture_output=True, check=True)
    return json.loads(process.stdout.strip())


def main() -> int:
    binary = Path(sys.argv[1])
    probe = adapter(binary, "missing")
    legal = probe.get("legalActions")
    if not isinstance(legal, list) or not legal:
        raise AssertionError(probe)
    identity = legal[0]["semanticKey"]
    native = adapter(binary, identity)
    if "traceError" in native or "after" not in native:
        raise AssertionError(native)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "native.jsonl"
        writer = DifferentialTraceWriter(path, run_id="native-self",
                                         provenance={"seed": "0", "ascension": 0})
        writer.write_decision({"step": 0, "seed": "0",
            "pre_action_state": native["state"], "post_action_state": native["after"],
            "differential_legal_actions": native["legalActions"],
            "semantic_action_identity": identity, "selected_candidate": legal[0],
            "preRng": native["rng"], "postRng": native["postRng"]}, boundary="ooc")
        result = replay(path, [native])
        if result.get("category") != "RUN_COMPLETE_EQUIVALENT":
            raise AssertionError(result)
    print("native_differential_replay: one native OOC boundary replayed exactly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
