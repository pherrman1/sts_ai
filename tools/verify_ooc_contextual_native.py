#!/usr/bin/env python3
"""Replay the frozen contextual-prior trace through native C++ and benchmark it."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import evaluate_ooc_contextual_semantic_trace as semantic  # noqa: E402

TRACE = Path("/home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/trace_mainline.jsonl.gz")
STUDENT = Path("/home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/retrained-contextual-student/contextual_student_frozen.pt")
TEACHER = Path("/home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/deployed_teacher_reconstructed.pt")
SOURCE_RESULT = Path("/home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/retrained-contextual-student/source_policy_result.json")
ATTENTION = ROOT / "selfplay/models/ooc_strategic_tok_final.native"
CONTEXTUAL = ROOT / "selfplay/models/ooc_strategic_tok_contextual.native"
CONTEXTUAL_SHA256 = "6d308d5fea278ea8aecc90d1f8bf44efe839b11c57d1362020f1e47f6dba68f7"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command, *, input_text=None, cwd=ROOT):
    return subprocess.run(command, input=input_text, text=True, capture_output=True,
                          check=True, cwd=cwd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True,
                        help="built ooc_contextual_native_probe executable")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--passes", type=int, default=5,
                        help="measured passes per model arm; order alternates A/B and B/A")
    parser.add_argument("--trace", type=Path, default=TRACE)
    parser.add_argument("--student", type=Path, default=STUDENT)
    parser.add_argument("--teacher", type=Path, default=TEACHER)
    parser.add_argument("--source-result", type=Path, default=SOURCE_RESULT)
    parser.add_argument("--attention", type=Path, default=ATTENTION)
    parser.add_argument("--contextual", type=Path, default=CONTEXTUAL)
    args = parser.parse_args()

    for path in (args.probe, args.trace, args.student, args.teacher,
                 args.source_result, args.attention, args.contextual):
        if not path.is_file():
            raise FileNotFoundError(path)
    if args.passes < 2 or args.passes > 20:
        parser.error("--passes must be between 2 and 20")
    hashes = {"trace_gzip_sha256": sha256(args.trace),
              "student_checkpoint_sha256": sha256(args.student),
              "teacher_checkpoint_sha256": sha256(args.teacher),
              "attention_artifact_sha256": sha256(args.attention),
              "contextual_artifact_sha256": sha256(args.contextual),
              "native_probe_sha256": sha256(args.probe),
              "native_source_sha256": sha256(ROOT / "tests/ooc_contextual_native_probe.cpp"),
              "native_model_header_sha256": sha256(ROOT / "apps/ooc_strategic_tok_net.h")}
    if hashes["trace_gzip_sha256"] != semantic.TRACE_GZIP_SHA256:
        raise ValueError(f"saved trace SHA mismatch: {hashes['trace_gzip_sha256']}")
    if hashes["student_checkpoint_sha256"] != "bc22f8b03646da79754c1fcfe04f49f20ed5f51ff9ba5250cf715d390d04a761":
        raise ValueError("frozen contextual checkpoint SHA mismatch")
    if hashes["attention_artifact_sha256"] != "e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c":
        raise ValueError("deployed attention artifact SHA mismatch")
    if hashes["contextual_artifact_sha256"] != CONTEXTUAL_SHA256:
        raise ValueError("exported contextual artifact SHA mismatch")

    records, _, census = semantic.load_unique_trace(args.trace)
    if len(records) != 6317:
        raise ValueError(f"primary prior population differs from 6,317: {len(records)}")
    input_lines = []
    for key, row in records:
        payload = dict(row)
        payload["priorKey"] = key
        input_lines.append(json.dumps(payload, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False))
    native_input = "\n".join(input_lines) + "\n"

    native = run([str(args.probe), "--replay", str(args.contextual)], input_text=native_input)
    native_lines = native.stdout.splitlines()
    if len(native_lines) != len(records):
        raise ValueError(f"native output count differs: {len(native_lines)} != {len(records)}")
    predictions_path = args.out_dir / "native_contextual_trace.jsonl.gz"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with gzip.open(predictions_path, "wt", encoding="utf-8", newline="\n") as stream:
        for line in native_lines:
            json.loads(line)  # Reject malformed native output before persisting it.
            stream.write(line + "\n")

    semantic_path = args.out_dir / "semantic_prior_result.json"
    evaluator_command = [sys.executable,
        str(ROOT / "tools/evaluate_ooc_contextual_semantic_trace.py"),
        "--trace", str(args.trace), "--source-result", str(args.source_result),
        "--teacher", str(args.teacher), "--student", str(args.student),
        "--native-results", str(predictions_path), "--device", "cpu",
        "--out", str(semantic_path)]
    run(evaluator_command)
    semantic_result = json.loads(semantic_path.read_text())
    if semantic_result.get("classification") != "CONTEXTUAL_SEMANTIC_PRIOR_PASS":
        raise RuntimeError("existing semantic-prior evaluator did not retain its PASS classification")
    native_parity = semantic_result.get("native_python_contextual_parity") or {}
    if native_parity.get("pass") is not True:
        raise RuntimeError(f"native/Python contextual parity gate failed: {native_parity}")

    timing = run([str(args.probe), "--benchmark", str(args.attention),
                  str(args.contextual), str(args.passes)], input_text=native_input)
    timing_result = json.loads(timing.stdout)
    if timing_result.get("prior_count") != 6317:
        raise ValueError("timing harness did not process exactly 6,317 unique priors")
    timing_path = args.out_dir / "ab_timing.json"
    timing_path.write_text(json.dumps(timing_result, indent=2, sort_keys=True) + "\n")
    full_prior = timing_result["metrics"]["prior"]
    full_prior_pass = full_prior["reduction_percent"] >= 5.0

    result = {
        "version": "ooc-contextual-native-runtime-v1",
        "artifacts": {**hashes,
                      "native_predictions_sha256": sha256(predictions_path),
                      "semantic_result_sha256": sha256(semantic_path),
                      "timing_result_sha256": sha256(timing_path)},
        "trace_population": census,
        "semantic_classification": semantic_result["classification"],
        "native_python_parity": native_parity,
        "timing": timing_result,
        "decision_rule": "proceed to the optional 8-seed live smoke only if complete production prior evaluation improves by at least 5%",
        "full_prior_speed_gate_pass": full_prior_pass,
    }
    result_path = args.out_dir / "native_runtime_result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"result": str(result_path),
                      "semantic_classification": semantic_result["classification"],
                      "native_parity": native_parity,
                      "timing": {name: {"attention_seconds": item["attention"]["all"]["total_cpu_seconds"],
                                        "contextual_seconds": item["contextual"]["all"]["total_cpu_seconds"],
                                        "reduction_percent": item["reduction_percent"]}
                                 for name, item in timing_result["metrics"].items()},
                      "full_prior_speed_gate_pass": full_prior_pass}, indent=2), flush=True)


if __name__ == "__main__":
    main()
