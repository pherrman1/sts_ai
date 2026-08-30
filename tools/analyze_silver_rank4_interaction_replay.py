#!/usr/bin/env python3
"""Strict root-paired analysis for the fixed rank-4 interaction replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_silver_cross_prior_replay import CONTROL_ARMS, CONTROL_FIELDS, HEADER_FIELDS, indexed
from analyze_silver_learned_visit_replay import ARMS, BOOTSTRAPS, bootstrap_mean, load, validate_controls


SEED = 20260830
SNAPSHOTS_HASH = "7cfc9371f1d1cfe3e48f7cbda3f6b0e7dc55d417be9d1612303d8e50ab67cc51"
RELABELS_HASH = "abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c"
SOURCE_COMMIT = "581b68bb31a8b62bb94e88c5b783e042880746b1"
EXECUTABLE_HASH = "d8d08392343ab442ec093e5fa07b64b326755560ff374dfba61bbce9c1a18006"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_jsonl_bytes(value: bytes) -> list[dict]:
    return [json.loads(line) for line in value.decode("utf-8").splitlines() if line.strip()]


def canonical_jsonl_hash(rows: list[dict]) -> str:
    canonical = b"".join(json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
                           for row in rows)
    return sha256_bytes(canonical)


def newline_hashes_bytes(observed: bytes) -> dict:
    lf = observed.replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    observed_rows, lf_rows, crlf_rows = map(parse_jsonl_bytes, (observed, lf, crlf))
    return {"observed_sha256": sha256_bytes(observed), "lf_sha256": sha256_bytes(lf),
            "crlf_sha256": sha256_bytes(crlf), "observed_newlines": {"lf": observed.count(b"\n"),
            "crlf": observed.count(b"\r\n")}, "parsed_rows_identical": observed_rows == lf_rows == crlf_rows,
            "canonical_semantic_sha256": canonical_jsonl_hash(observed_rows),
            "lf_canonical_semantic_sha256": canonical_jsonl_hash(lf_rows),
            "crlf_canonical_semantic_sha256": canonical_jsonl_hash(crlf_rows)}


def newline_hashes(path: Path) -> dict:
    return newline_hashes_bytes(path.read_bytes())


def byte_hash_acceptance(newline: dict, expected: str) -> tuple[bool, bool]:
    byte_match = newline["observed_sha256"] == expected
    canonical_equivalence = (not byte_match and newline["lf_sha256"] == expected
                             and newline["parsed_rows_identical"]
                             and newline["canonical_semantic_sha256"] == newline["lf_canonical_semantic_sha256"])
    return byte_match, canonical_equivalence


def interaction_recorded(manifest: dict) -> dict:
    return {"recorded_provenance_id": "interaction_replay_manifest",
            "replay_sha256": manifest["outputs"]["replay_jsonl_sha256"],
            "source_commit": manifest["source_commit"], "executable_sha256": manifest["executable_sha256"],
            "snapshots_sha256": manifest["frozen_inputs"]["snapshots_sha256"],
            "relabels_sha256": manifest["frozen_inputs"]["relabels_sha256"]}


def historical_recorded(manifest: dict, name: str) -> dict:
    if name == "grouped_linear":
        return {"recorded_provenance_id": "grouped_linear_replay_manifest",
                "replay_sha256": manifest["outputs"]["replay_jsonl_sha256"],
                "source_commit": manifest["replay_source_commit"], "executable_sha256": manifest["replay_executable_sha256"],
                "snapshots_sha256": manifest["inputs"]["snapshots_sha256"], "relabels_sha256": manifest["inputs"]["relabels_sha256"]}
    return {"recorded_provenance_id": "rankshape_cross_prior_provenance", **manifest["replays"][name]}


def verify_recorded_replay(name: str, path: Path, recorded: dict) -> dict:
    newline = newline_hashes(path)
    byte_match, canonical_equivalence = byte_hash_acceptance(newline, recorded["replay_sha256"])
    if not byte_match and not canonical_equivalence:
        raise ValueError(f"{name} replay byte hash mismatch without canonical-equivalence proof")
    return {"name": name, "recorded": recorded, "observed": newline,
            "byte_hash_match": byte_match, "canonical_equivalence_proved": canonical_equivalence,
            "acceptance": "exact_byte_hash" if byte_match else "LF_CRLF_canonical_equivalence"}


def verify_frozen_inputs(snapshots: Path, relabels: Path) -> dict:
    observed = {"snapshots_sha256": sha256(snapshots), "relabels_sha256": sha256(relabels)}
    if observed != {"snapshots_sha256": SNAPSHOTS_HASH, "relabels_sha256": RELABELS_HASH}:
        raise ValueError("frozen snapshot/relabel hashes do not match the experiment contract")
    return observed


def exact_controls(rows: list[dict]) -> dict:
    return {(row["group_id"], row["replicate"], row["arm"]):
            {field: row[field] for field in CONTROL_FIELDS}
            for row in rows if row["arm"] in CONTROL_ARMS}


def independently_verified(name: str, path: Path, recorded: dict, snapshots: Path, relabels: Path) -> tuple[dict, dict, list[dict]]:
    proof = verify_recorded_replay(name, path, recorded)
    header, rows = load(path)
    frozen = verify_frozen_inputs(snapshots, relabels)
    if recorded["source_commit"] != SOURCE_COMMIT or recorded["executable_sha256"] != EXECUTABLE_HASH:
        raise ValueError(f"{name} recorded source/executable provenance mismatch")
    if recorded["snapshots_sha256"] != frozen["snapshots_sha256"] or recorded["relabels_sha256"] != frozen["relabels_sha256"]:
        raise ValueError(f"{name} recorded snapshot/relabel provenance mismatch")
    proof.update({"root_replicate_set": sorted({(row["group_id"], row["replicate"]) for row in rows}),
                  "search_seeds": sorted((row["group_id"], row["replicate"], row["search_seed"])
                                         for row in rows if row["arm"] == "current_uct"),
                  "control_means": validate_controls(arm_means(rows)), "header": {key: header.get(key) for key in HEADER_FIELDS}})
    return proof, header, rows


def cross_provenance(reference: tuple[dict, dict, list[dict]], candidate: tuple[dict, dict, list[dict]]) -> dict:
    reference_proof, reference_header, reference_rows = reference
    candidate_proof, candidate_header, candidate_rows = candidate
    checks = {"independent_recorded_provenance": (reference_proof["recorded"] is not candidate_proof["recorded"]
                                                   and reference_proof["recorded"]["recorded_provenance_id"]
                                                   != candidate_proof["recorded"]["recorded_provenance_id"]),
              "same_header_contract": all(reference_header.get(k) == candidate_header.get(k) for k in HEADER_FIELDS),
              "same_root_replicate_set": reference_proof["root_replicate_set"] == candidate_proof["root_replicate_set"],
              "same_per_root_search_seeds": reference_proof["search_seeds"] == candidate_proof["search_seeds"],
              "same_source_commit": reference_proof["recorded"]["source_commit"] == candidate_proof["recorded"]["source_commit"],
              "same_executable_sha256": reference_proof["recorded"]["executable_sha256"] == candidate_proof["recorded"]["executable_sha256"],
              "same_snapshots_sha256": reference_proof["recorded"]["snapshots_sha256"] == candidate_proof["recorded"]["snapshots_sha256"],
              "same_relabels_sha256": reference_proof["recorded"]["relabels_sha256"] == candidate_proof["recorded"]["relabels_sha256"],
              "exact_uct_oracle_control_rows": exact_controls(reference_rows) == exact_controls(candidate_rows)}
    return {"pass": all(checks.values()), "checks": checks, "failures": [key for key, value in checks.items() if not value]}


def root_deltas(treatment_rows, control_rows, treatment_arm="learned_visit_puct", control_arm="learned_visit_puct"):
    treatment, control = indexed(treatment_rows), indexed(control_rows)
    groups = sorted({row["group_id"] for row in treatment_rows})
    top, regret = [], []
    for group in groups:
        keys = [(group, replicate) for replicate in range(4)]
        top.append(statistics.fmean(float(treatment[(g, r, treatment_arm)]["frozen_b_top_choice"])
                                    - float(control[(g, r, control_arm)]["frozen_b_top_choice"])
                                    for g, r in keys))
        regret.append(statistics.fmean(float(treatment[(g, r, treatment_arm)]["frozen_b_regret"])
                                       - float(control[(g, r, control_arm)]["frozen_b_regret"])
                                       for g, r in keys))
    return groups, top, regret


def comparison(name, treatment_rows, control_rows, treatment_arm="learned_visit_puct", control_arm="learned_visit_puct", seed=SEED):
    groups, top, regret = root_deltas(treatment_rows, control_rows, treatment_arm, control_arm)
    rng = random.Random(seed)
    loo = [statistics.fmean(regret[:i] + regret[i + 1:]) for i in range(len(regret))]
    return {"name": name, "pairing": "(group_id, replicate), then mean of four replicate differences per root",
            "roots": len(groups), "replicates_per_root": 4, "bootstrap_replicates": BOOTSTRAPS,
            "bootstrap_seed": seed, "mean_b_best_probability_delta": statistics.fmean(top),
            "mean_b_best_probability_delta_pp": 100.0 * statistics.fmean(top),
            "b_best_probability_delta_ci95": bootstrap_mean(top, rng),
            "mean_frozen_b_regret_delta": statistics.fmean(regret),
            "mean_frozen_b_regret_delta_ci95": bootstrap_mean(regret, rng),
            "median_frozen_b_regret_delta": statistics.median(regret),
            "regret_improved": sum(value < -1e-12 for value in regret),
            "regret_worsened": sum(value > 1e-12 for value in regret),
            "regret_tied": sum(abs(value) <= 1e-12 for value in regret),
            "largest_positive_regret_effect": {"group_id": groups[max(range(len(groups)), key=lambda i: (regret[i], groups[i]))],
                                                "delta": max(regret)},
            "largest_negative_regret_effect": {"group_id": groups[min(range(len(groups)), key=lambda i: (regret[i], groups[i]))],
                                                "delta": min(regret)},
            "leave_one_root_out_mean_regret_delta_range": [min(loo), max(loo)]}


def arm_means(rows):
    return {arm: {"mean_b_best_probability": statistics.fmean(float(row["frozen_b_top_choice"])
                                                                for row in rows if row["arm"] == arm),
                  "mean_b_regret": statistics.fmean(float(row["frozen_b_regret"])
                                                      for row in rows if row["arm"] == arm)} for arm in ARMS}


def decision(primary, means):
    g_best = means["oracle_visit_puct"]["mean_b_best_probability"] - means["current_uct"]["mean_b_best_probability"]
    g_regret = means["current_uct"]["mean_b_regret"] - means["oracle_visit_puct"]["mean_b_regret"]
    top, regret = primary["mean_b_best_probability_delta"], primary["mean_frozen_b_regret_delta"]
    top_ci, regret_ci = primary["b_best_probability_delta_ci95"], primary["mean_frozen_b_regret_delta_ci95"]
    supported = (top > 0 and regret < 0 and (top_ci[0] > 0 or regret_ci[1] < 0)
                 and top_ci[0] > -.20 * g_best and regret_ci[1] < .20 * g_regret)
    rejected = (top <= 0 and regret >= 0 and top_ci[1] < .20 * g_best and regret_ci[0] > -.20 * g_regret)
    return {"classification": "INTERACTION_SUPPORTED" if supported else "INTERACTION_REJECTED" if rejected
                             else "RANK4_INTERACTION_VISIT_POLICY_REPLAY_INCONCLUSIVE",
            "oracle_gaps": {"best_probability": g_best, "regret_reduction": g_regret},
            "conditions": {"both_point_estimates_favorable": top > 0 and regret < 0,
                           "at_least_one_ci_excludes_zero_favorably": top_ci[0] > 0 or regret_ci[1] < 0,
                           "best_ci_lower_above_minus_20_percent_oracle_gap": top_ci[0] > -.20 * g_best,
                           "regret_ci_upper_below_plus_20_percent_oracle_gap": regret_ci[1] < .20 * g_regret,
                           "both_points_neutral_or_worse": top <= 0 and regret >= 0,
                           "both_intervals_rule_out_20_percent_improvement": top_ci[1] < .20 * g_best and regret_ci[0] > -.20 * g_regret}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("interaction", type=Path)
    parser.add_argument("grouped_linear", type=Path)
    parser.add_argument("rankshape", type=Path)
    parser.add_argument("snapshots", type=Path)
    parser.add_argument("relabels", type=Path)
    parser.add_argument("--interaction-manifest", required=True, type=Path)
    parser.add_argument("--grouped-manifest", required=True, type=Path)
    parser.add_argument("--rankshape-provenance", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    args = parser.parse_args()
    interaction_manifest = json.loads(args.interaction_manifest.read_text(encoding="utf-8"))
    grouped_manifest = json.loads(args.grouped_manifest.read_text(encoding="utf-8"))
    rankshape_manifest = json.loads(args.rankshape_provenance.read_text(encoding="utf-8"))
    interaction = independently_verified("interaction", args.interaction, interaction_recorded(interaction_manifest), args.snapshots, args.relabels)
    grouped = independently_verified("grouped_linear", args.grouped_linear, historical_recorded(grouped_manifest, "grouped_linear"), args.snapshots, args.relabels)
    rankshape = independently_verified("rankshape", args.rankshape, historical_recorded(rankshape_manifest, "rankshape"), args.snapshots, args.relabels)
    _, interaction_header, interaction_rows = interaction
    comparisons = {}
    for number, (name, candidate) in enumerate((("grouped_linear", grouped), ("rankshape", rankshape)), 1):
        _, _, rows = candidate
        gate = cross_provenance(interaction, candidate)
        if not gate["pass"]:
            raise ValueError(f"replay alignment failure for {name}: {gate['failures']}")
        comparisons[f"interaction_minus_{name}"] = comparison(
            f"interaction minus {name}", interaction_rows, rows, seed=SEED + number)
    comparisons["interaction_minus_current_uct"] = comparison(
        "interaction minus current UCT", interaction_rows, interaction_rows, "learned_visit_puct", "current_uct", SEED + 3)
    comparisons["interaction_minus_oracle"] = comparison(
        "interaction minus oracle", interaction_rows, interaction_rows, "learned_visit_puct", "oracle_visit_puct", SEED + 4)
    means = arm_means(interaction_rows)
    controls = validate_controls(means)
    primary = comparisons["interaction_minus_grouped_linear"]
    oracle_best = means["oracle_visit_puct"]["mean_b_best_probability"] - means["current_uct"]["mean_b_best_probability"]
    oracle_regret = means["current_uct"]["mean_b_regret"] - means["oracle_visit_puct"]["mean_b_regret"]
    interaction_best = means["learned_visit_puct"]["mean_b_best_probability"] - means["current_uct"]["mean_b_best_probability"]
    interaction_regret = means["current_uct"]["mean_b_regret"] - means["learned_visit_puct"]["mean_b_regret"]
    payload = {"schema": "silver_rank4_interaction_replay_analysis_v2", "independent_replay_provenance": {
        "interaction": interaction[0], "grouped_linear": grouped[0], "rankshape": rankshape[0]}, "controls": controls,
        "arm_means": means, "comparisons": comparisons,
        "fraction_of_concurrent_oracle_gain_recovered": {"best_probability": interaction_best / oracle_best,
                                                            "regret_reduction": interaction_regret / oracle_regret},
        "decision": decision(primary, means),
        "interpretation": "Exploratory repeated-root search evidence only; it is not gameplay confirmation and does not authorize a rank, MLP, temperature, or c_puct sweep."}
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
