#!/usr/bin/env python3
"""Frozen 64-root, four-arm ordering-ablation analysis; no game execution."""

import argparse
import hashlib
import json
import math
import random
import statistics
from pathlib import Path


ARMS = ("A", "B", "G", "H")
CONTRASTS = ("G-A", "H-A", "G-B", "H-B", "B-A")
RESAMPLES = 10000
SEED = 20260917
CLASSIFICATIONS = ("ROOT_PRIOR_SIGNAL_CONFIRMED", "ROOT_ORDER_SIGNAL_ONLY",
                   "ROOT_COMBINATION_ONLY", "ROOT_GUIDANCE_SIGNAL_NOT_CONFIRMED",
                   "ROOT_GUIDANCE_INCONCLUSIVE")


def _metadata(row):
    required = ("state_hash", "teacher_a_hash", "teacher_b_hash", "executable_git_sha",
                "silver_upstream_sha", "native_order", "fixture_only")
    if any(key not in row for key in required) or row["fixture_only"] is not False:
        raise ValueError("scientific replay provenance is incomplete")
    if (not isinstance(row["state_hash"], str) or not row["state_hash"]
            or not isinstance(row["teacher_a_hash"], str) or not row["teacher_a_hash"]
            or not isinstance(row["teacher_b_hash"], str) or not row["teacher_b_hash"]
            or not isinstance(row["executable_git_sha"], str)
            or not row["executable_git_sha"]
            or not isinstance(row["silver_upstream_sha"], str)
            or not row["silver_upstream_sha"]
            or not isinstance(row["native_order"], list) or not row["native_order"]):
        raise ValueError("invalid scientific replay provenance")
    return tuple(json.dumps(row[key], sort_keys=True) for key in required[:-1])


def select(rows):
    identities = [row["root_id"] for row in rows]
    if any(not isinstance(identity, str) or not identity for identity in identities):
        raise ValueError("invalid root identity")
    if len(set(identities)) != len(identities) or len(rows) < 64:
        raise ValueError("need at least 64 unique eligible roots")
    return sorted(rows, key=lambda row: (
        hashlib.sha256(row["root_id"].encode()).hexdigest(), row["root_id"]))[:64]


def analyze(rows, expected_roots=64):
    indexed = {}
    seeds = {}
    sources = {}
    metadata = {}
    executable_sha = None
    silver_sha = None
    for row in rows:
        root, arm, replicate = row["root_id"], row["arm"], row["replicate"]
        if (not isinstance(root, str) or not root or arm not in ARMS
                or type(replicate) is not int or replicate not in range(4)
                or type(row["simulations"]) is not int or row["simulations"] != 32
                or type(row["source_seed"]) is not int or row["source_seed"] < 0
                or type(row["search_seed"]) is not int or row["search_seed"] <= 0
                or type(row["b_best"]) is not bool
                or type(row["b_regret"]) not in (int, float)
                or not math.isfinite(row["b_regret"]) or row["b_regret"] < 0
                or not isinstance(row["selected_action_fingerprint"], str)
                or not row["selected_action_fingerprint"]
                or not isinstance(row.get("replay_order"), list)
                or not isinstance(row.get("priors"), list)):
            raise ValueError("invalid replay row")
        row_metadata = _metadata(row)
        if executable_sha is None:
            executable_sha = row["executable_git_sha"]
            silver_sha = row["silver_upstream_sha"]
        elif (row["executable_git_sha"] != executable_sha
              or row["silver_upstream_sha"] != silver_sha):
            raise ValueError("scientific artifact provenance differs globally")
        if metadata.setdefault(root, row_metadata) != row_metadata:
            raise ValueError("root provenance differs between arms or replicates")
        native_order = json.loads(row_metadata[5])
        if row["selected_action_fingerprint"] not in native_order:
            raise ValueError("selected action is outside the native root surface")
        key = root, arm, replicate
        if key in indexed:
            raise ValueError("duplicate root/arm/replicate")
        indexed[key] = row
        seed_key = root, replicate
        if seeds.setdefault(seed_key, row["search_seed"]) != row["search_seed"]:
            raise ValueError("search replicate identities differ between arms")
        if sources.setdefault(root, row["source_seed"]) != row["source_seed"]:
            raise ValueError("root source identity changed")
    roots = sorted(sources)
    expected = {(root, arm, replicate) for root in roots for arm in ARMS
                for replicate in range(4)}
    if len(roots) != expected_roots or not roots or set(indexed) != expected:
        raise ValueError("incomplete root/arm/replicate population")
    for root in roots:
        if len({seeds[root, replicate] for replicate in range(4)}) != 4:
            raise ValueError("replicate RNG identities must be distinct")
    reduced = {}
    for root in roots:
        reduced[root] = {}
        samples_by_arm = {arm: [indexed[root, arm, replicate] for replicate in range(4)]
                          for arm in ARMS}
        native = json.loads(metadata[root][5])
        if any(sample["replay_order"] != native for sample in samples_by_arm["A"]):
            raise ValueError("native-order arm contract differs from native order")
        ordered = samples_by_arm["B"][0]["replay_order"]
        if any(sample["replay_order"] != ordered for sample in samples_by_arm["B"]):
            raise ValueError("Teacher-A full ordering differs between replicates")
        if sorted(ordered) != sorted(native):
            raise ValueError("Teacher-A full ordering is not the native surface")
        top1 = samples_by_arm["G"][0]["replay_order"]
        top2 = samples_by_arm["H"][0]["replay_order"]
        if any(sample["replay_order"] != top1 for sample in samples_by_arm["G"]):
            raise ValueError("top1 ordering differs between replicates")
        if any(sample["replay_order"] != top2 for sample in samples_by_arm["H"]):
            raise ValueError("top2 ordering differs between replicates")
        if sorted(top1) != sorted(native) or sorted(top2) != sorted(native):
            raise ValueError("prefix ordering is not the native surface")
        if top1[1:] != [action for action in native if action != top1[0]]:
            raise ValueError("top1 ordering changes the native remainder")
        if top2[2:] != [action for action in native if action not in top2[:2]]:
            raise ValueError("top2 ordering changes the native remainder")
        if top1[0] != ordered[0] or top2[:2] != ordered[:2]:
            raise ValueError("prefix ordering does not match Teacher-A prefix")
        if any(sample["priors"] for arm in ARMS for sample in samples_by_arm[arm]):
            raise ValueError("UCT ordering arm unexpectedly carries priors")
        for arm in ARMS:
            samples = samples_by_arm[arm]
            contracts = {(json.dumps(sample["replay_order"], sort_keys=True),
                          json.dumps(sample["priors"], sort_keys=True)) for sample in samples}
            if len(contracts) != 1:
                raise ValueError("replay contract differs between replicates")
            if any(sample["priors"] for sample in samples):
                raise ValueError("root prior vector does not match UCT contract")
            regrets = [sample["b_regret"] for sample in samples]
            reduced[root][arm] = {
                "regret": statistics.mean(regrets),
                "b_best_probability": statistics.mean(sample["b_best"] for sample in samples),
                "regret_sd": statistics.pstdev(regrets),
                "regret_range": max(regrets) - min(regrets)}
    source_root_groups = {}
    for root in roots:
        source_root_groups.setdefault(sources[root], []).append(root)
    if any(len(group) != 2 for group in source_root_groups.values()):
        raise ValueError("each source seed must contribute exactly two roots")
    source_seeds = sorted(source_root_groups)
    source_results = {}
    for source_seed in source_seeds:
        source_results[source_seed] = {
            arm: {
                "regret": statistics.mean(reduced[root][arm]["regret"]
                                           for root in source_root_groups[source_seed]),
                "b_best_probability": statistics.mean(
                    reduced[root][arm]["b_best_probability"]
                    for root in source_root_groups[source_seed]),
            }
            for arm in ARMS
        }

    generator = random.Random(SEED)
    draws = [[generator.randrange(len(source_seeds)) for _ in source_seeds]
             for _ in range(RESAMPLES)]

    def interval(values):
        means = sorted(statistics.mean(values[index] for index in draw) for draw in draws)
        return [means[249], means[9749]]

    def sign_test_pvalue(deltas):
        non_ties = [delta for delta in deltas if delta != 0]
        wins = sum(delta < 0 for delta in non_ties)
        losses = len(non_ties) - wins
        tail = min(wins, losses)
        probability = sum(math.comb(len(non_ties), index)
                          for index in range(tail + 1)) / 2 ** len(non_ties)
        return min(1.0, 2.0 * probability) if non_ties else 1.0

    contrasts = {}
    for contrast in CONTRASTS:
        treatment, control = contrast.split("-")
        deltas = [source_results[source_seed][treatment]["regret"]
                  - source_results[source_seed][control]["regret"]
                  for source_seed in source_seeds]
        probabilities = [source_results[source_seed][treatment]["b_best_probability"]
                         - source_results[source_seed][control]["b_best_probability"]
                         for source_seed in source_seeds]
        contrasts[contrast] = {
            "mean_regret_delta": statistics.mean(deltas), "regret_ci95": interval(deltas),
            "b_best_probability_delta": statistics.mean(probabilities),
            "b_best_probability_ci95": interval(probabilities),
            "improved": sum(delta < 0 for delta in deltas),
            "worsened": sum(delta > 0 for delta in deltas),
            "tied": sum(delta == 0 for delta in deltas),
            "sign_test_p_two_sided": sign_test_pvalue(deltas),
            "root_deltas": {
                root: reduced[root][treatment]["regret"]
                - reduced[root][control]["regret"] for root in roots},
            "source_seed_deltas": dict(zip(source_seeds, deltas)),
            "worst_harms": sorted(zip(source_seeds, deltas), key=lambda pair: pair[1], reverse=True)[:10]}
    return {"roots": len(roots), "source_seeds": len(source_seeds),
            "replicates_per_root": 4, "bootstrap_resamples": RESAMPLES,
            "bootstrap_seed": SEED, "bootstrap_unit": "source_seed", "contrasts": contrasts,
            "arms_schema": "ordering_ablation_v1",
            "arms": {arm: {field: statistics.mean(reduced[root][arm][field] for root in roots)
                           for field in reduced[roots[0]][arm]} for arm in ARMS},
            "root_results": reduced, "source_seed_results": source_results,
            "source_seed_map": sources, "classification": None,
            "predeclared_classifications": CLASSIFICATIONS,
            "interpretation": "Statistical screen only; correctness and harmful-tail review remain required."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("select", "analyze"))
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest_path = Path(str(args.output) + ".manifest.json")
    if args.output.exists() or manifest_path.exists():
        raise ValueError("refusing existing output/manifest")
    raw = args.input.read_bytes()
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if args.mode == "select":
        result = select(rows)
        content = "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in result)
        manifest = {"schema": "silver_root_mechanism_selection_v1",
                    "source_capture_sha256": hashlib.sha256(raw).hexdigest(),
                    "selected_sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "selection": "lowest 64 SHA256(UTF8(root_id)); root_id breaks hash ties",
                    "selected_root_ids": [row["root_id"] for row in result],
                    "source_root_count": len(rows),
                    "source_seeds": sorted({row["source_seed"] for row in rows})}
    else:
        for row in rows:
            if row.get("schema") != "silver_root_mechanism_replay_v1" or row.get("fixture_only") is not False:
                raise ValueError("analysis requires scientific replay records, not fixtures")
        result = analyze(rows)
        result["input_sha256"] = hashlib.sha256(raw).hexdigest()
        content = json.dumps(result, indent=2, allow_nan=False) + "\n"
    with args.output.open("x") as output:
        output.write(content)
    if args.mode == "select":
        with manifest_path.open("x") as output:
            json.dump(manifest, output, indent=2)


if __name__ == "__main__":
    main()
