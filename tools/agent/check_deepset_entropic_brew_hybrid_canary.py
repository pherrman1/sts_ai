#!/usr/bin/env python3
"""Validate the one-seed mechanism/provenance canary for the frozen CTM study."""
from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))
import analyze_deepset_entropic_brew_hybrid_confirmation as confirmation  # noqa: E402


CANARY_SEED = 989999


def file_hashes(local_files: dict[str, Path]) -> dict[str, str]:
    return {role: confirmation.sha256(path) for role, path in local_files.items()}


def validate_canary(manifest_path: Path, standard_dir: Path, hybrid_dir: Path,
                    local_files: dict[str, Path],
                    expected_hashes: dict[str, str] | None = None) -> dict[str, Any]:
    manifest = confirmation.read_manifest(manifest_path)
    hashes = dict(expected_hashes or confirmation.ARTIFACT_SHAS)
    hashes["binary"] = hashes.get("binary", confirmation.FROZEN_BINARY_SHA256)
    arms = confirmation.validate_manifest(
        manifest, local_files, hashes, seed_start=CANARY_SEED, seed_count=1,
    )
    env_c = {**manifest["common_env"], **arms["C"]["env"]}
    env_h = {**manifest["common_env"], **arms["H"]["env"]}
    binary_hash = hashes["binary"]
    seeds = [CANARY_SEED]
    standard = confirmation.validate_arm(standard_dir, "C", seeds, env_c, binary_hash,
                                        arms["C"]["results"])
    hybrid = confirmation.validate_arm(hybrid_dir, "H", seeds, env_h, binary_hash,
                                       arms["H"]["results"])
    require(standard["meta"]["models"] == hybrid["meta"]["models"],
            "canary arms differ in common loaded model metadata")
    for name, arm in (("C", standard), ("H", hybrid)):
        trace = arm["traces"][CANARY_SEED]
        require(int(trace["oocDecisions"]) > 0 and int(trace["simulations"]) > 0,
                f"{name}: canary has no live OOC MCTS decision/simulation receipt")
        require(int(trace["simulations"]) <= confirmation.OOC_SIMULATIONS * int(trace["oocDecisions"]),
                f"{name}: canary MCTS simulation count exceeds its configured per-decision budget")
    h_trace = hybrid["traces"][CANARY_SEED]
    require(int(h_trace["hybridPreparations"]) > 0,
            "H: canary did not exercise or record a hybrid preparation")
    return {
        "status": "CANARY_MECHANISM_AND_PROVENANCE_PASS",
        "seed": CANARY_SEED,
        "binarySha256": binary_hash,
        "frozenGitSha": confirmation.FROZEN_SHA,
        "standardTrace": standard["traces"][CANARY_SEED],
        "hybridTrace": h_trace,
        "standardConfig": standard["oocConfig"],
        "hybridConfig": hybrid["oocConfig"],
        "interpretation": "mechanism/provenance only; canary win/loss is excluded from quality analysis",
    }


def require(condition: bool, message: str) -> None:
    if not condition:
        raise confirmation.EvidenceError(message)


def local_files_from_args(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "binary": args.binary,
        "standard_ctm": args.standard_ctm,
        "fast_ctm": args.fast_ctm,
        "v4_policy": args.v4_policy,
        "floor_model": args.floor_model,
        "win_model": args.win_model,
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="deepset-hybrid-canary-") as temp:
        root = Path(temp)
        standard, hybrid, manifest_path, files = confirmation.synthetic_fixture(root, "pass")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["command"][3] = "1"
        manifest["command"][5] = str(CANARY_SEED)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        for folder in (standard, hybrid):
            for name in ("results.csv", "mcts.csv"):
                path = folder / name
                with path.open(newline="", encoding="utf-8") as stream:
                    rows = list(csv.reader(stream))
                rows = [rows[0], rows[1]]
                rows[1][0] = str(CANARY_SEED)
                with path.open("w", newline="", encoding="utf-8") as stream:
                    csv.writer(stream, lineterminator="\n").writerows(rows)
            for suffix in (".support.jsonl", ".actions.jsonl"):
                path = folder / ("mcts.csv" + suffix)
                row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
                row["seed"] = CANARY_SEED
                path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            meta_path = folder / "results.csv.meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["seedBlock"] = {"lo": CANARY_SEED, "hi": CANARY_SEED}
            meta["nSeeds"] = 1
            manifest_arms = json.loads(manifest_path.read_text(encoding="utf-8"))["arms"]
            arm_name = "C" if folder == standard else "H"
            result_path = next(arm["results"] for arm in manifest_arms if arm["name"] == arm_name)
            meta["argv"] = ["bestbench", "10000", "1", "0", str(CANARY_SEED), result_path]
            meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")

        local_files = dict(files)
        digest_map = file_hashes(local_files)
        synthetic_hashes = {**digest_map}
        result = validate_canary(manifest_path, standard, hybrid, local_files, synthetic_hashes)
        assert result["status"] == "CANARY_MECHANISM_AND_PROVENANCE_PASS"
        assert int(result["hybridTrace"]["hybridPreparations"]) > 0

        bad = json.loads(manifest_path.read_text(encoding="utf-8"))
        bad["arms"][1]["env"]["STS_OOC_MCTS_BREW_FALLBACK_MODEL"] = "artifacts/wrong.native"
        manifest_path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
        try:
            validate_canary(manifest_path, standard, hybrid, local_files, synthetic_hashes)
        except confirmation.EvidenceError:
            pass
        else:
            raise AssertionError("wrong fallback path self-test did not fail")
        assert digest_map["binary"] == confirmation.sha256(local_files["binary"])
    print("deepset hybrid canary validator self-test PASS")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--manifest", type=Path)
    result.add_argument("--standard", type=Path)
    result.add_argument("--hybrid", type=Path)
    result.add_argument("--binary", type=Path)
    result.add_argument("--standard-ctm", type=Path)
    result.add_argument("--fast-ctm", type=Path)
    result.add_argument("--v4-policy", type=Path)
    result.add_argument("--floor-model", type=Path)
    result.add_argument("--win-model", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    required = ("manifest", "standard", "hybrid", "binary", "standard_ctm", "fast_ctm",
                "v4_policy", "floor_model", "win_model")
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        raise SystemExit("missing required arguments: " + ", ".join(missing))
    try:
        report = validate_canary(args.manifest, args.standard, args.hybrid,
                                 local_files_from_args(args))
    except (confirmation.EvidenceError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"deepset hybrid canary FAIL: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
