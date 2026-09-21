#!/usr/bin/env python3
"""Freeze, select, validate and load the policy-only Silver prior dataset.

The planning commands never run gameplay. Execution uses the seed guard and a
separately frozen reviewed-SHA binding; raw J artifacts have no training loader.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

from silver_prior_projection import canonical, digest, project, require, vocabulary, validate_vocabulary

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "silver_prior_plan_v1"
SILVER = "84ab3ead9d88c01c4be09a6773fb9a947f57d5ff"
ENV = {"STS_FAIR": "1", "STS_SEARCHER3": "0", "STS_SILVER_SEARCH": "1",
       "STS_NATIVE_OOC": "1", "STS_SILVER_EXACT_ROOT_BUDGETS": "1",
       "STS_SILVER_ADAPTIVE": "0", "STS_SILVER_EXACT_VISIT_LOCK": "0",
       "STS_SILVER_RHO_RACING": "0", "STS_SILVER_REUSE_CAP_MODE": "allocated",
       "STS_SILVER_REUSE_CAP": "32768", "STS_SILVER_VNET_LEAF_DIRECT": "0", "STS_SILVER_TELEMETRY": "1",
       "STS_COLLECT_KEYS": "0", "STS_STOP_AFTER_ACT": "3", "STS_THREADS": "1"}
CAPTURE = {"simulations": 10000, "reuse_cap": 32768, "reuse_mode": "allocated",
           "adaptive": False, "exact_lock": False, "rho": False}


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    path = Path(path)
    with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as stream:
        return json.load(stream)


def rows(path):
    path = Path(path)
    with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as stream:
        return [json.loads(line) for line in stream if line.strip()]


def publish(path, value):
    """Atomic, create-only; retries accept exactly identical successful evidence."""
    path = Path(path)
    data = (canonical(value) + "\n").encode()
    if path.suffix == ".gz":
        data = gzip.compress(data, mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.read_bytes() == data, f"refusing changed evidence: {path}")
        return
    fd, name = tempfile.mkstemp(prefix=".prior-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def seal(value):
    return {**value, "sha256": digest(value)}


def check_seal(value):
    require(value["sha256"] == digest({k: v for k, v in value.items() if k != "sha256"}),
            "content hash mismatch")


def freeze(directory):
    from ironclad_reachable_domain_census import build_census
    census = build_census()
    vocab = vocabulary(census)
    # Conservative freshness inventory: all numeric seed-sized literals in tracked
    # experiment evidence/docs, plus explicit inclusive seed ranges. No outcomes used.
    tracked = subprocess.check_output(["git", "ls-files", "docs/experiments", "EXPERIMENTS.md"],
                                      cwd=ROOT, text=True).splitlines()
    reserved, inventory = set(), []
    for rel in tracked:
        path = ROOT / rel
        try:
            text = (gzip.decompress(path.read_bytes()).decode() if path.suffix == ".gz"
                    else path.read_text())
        except (UnicodeError, OSError):
            continue
        if "seed" not in text.lower():
            continue
        reserved.update(int(s) for s in re.findall(r"(?<![\w.])\d{5,19}(?![\w.])", text))
        for lo, hi in re.findall(r"(?<!\d)(\d{5,19})\s*(?:\.\.|–|-)\s*(\d{5,19})(?!\d)", text):
            if 0 <= int(hi) - int(lo) <= 100000:
                reserved.update(range(int(lo), int(hi) + 1))
        inventory.append({"path": rel, "sha256": file_hash(path)})
    # Also exclude the complete hard64 discovery range, not merely selected roots.
    hard = read(ROOT / "docs/experiments/evidence/silver_hard_combat_v1_20260918/source-manifest.json")
    reserved.update(range(hard["source_seed_start"], hard["source_seed_end"] + 1))
    seeds = [n for n in range(24000000, 24010000) if n not in reserved][:512]
    require(len(seeds) == 512, "fresh seed inventory exhausted")
    source = [{"seed": seed, "split": "TRAIN" if i < 384 else
               "VALIDATION" if i < 448 else "LOCKED_TEST"} for i, seed in enumerate(seeds)]
    plan = seal({"schema": SCHEMA, "created_before_labels": True,
                 "baseline_sha": census["sourceHeadAudited"], "sources": source,
                 "pilot_sources": seeds[:16], "source_environment": ENV,
                 "source_simulations": 10000, "ascension": 0, "acts": [1, 2, 3],
                 "vocabulary_sha256": vocab["sha256"], "silver_upstream_sha": SILVER,
                 "teacher_identity": "silver-prior-v1/20260922",
                 "teachers": {"L": {"replicates": 8, "budget": 5000},
                              "J": {"replicates": 8, "budget": 10000}},
                 "selection": {"schema": "hash_early_late_round_robin_v1",
                               "max_source": 24, "max_act": 8, "max_combat": 2,
                               "early_turn_max": 2, "pilot_max_act": 2,
                               "judge": "minimum sha256(root_id) per evaluation source"},
                 "freshness": {"inventory": inventory, "reserved_count": len(reserved),
                               "reserved_sha256": digest(sorted(reserved)),
                               "hard64_all_sources_excluded": True,
                               "limitation": "tracked repository evidence only; remote inventory unavailable"}})
    directory = Path(directory)
    publish(directory / "vocabulary.json", vocab)
    publish(directory / "plan.json", plan)
    publish(directory / "census-cards.json", census["domains"]["cards"])
    return plan


def validate_plan(plan):
    check_seal(plan)
    require(plan["schema"] == SCHEMA and plan["source_environment"] == ENV
            and plan["source_simulations"] == 10000 and plan["ascension"] == 0
            and plan["acts"] == [1, 2, 3] and plan["silver_upstream_sha"] == SILVER,
            "source protocol")
    sources = plan["sources"]
    require(len({s["seed"] for s in sources}) == 512
            and Counter(s["split"] for s in sources) ==
            {"TRAIN": 384, "VALIDATION": 64, "LOCKED_TEST": 64}, "source split accounting")
    require(plan["teachers"] == {"L": {"replicates": 8, "budget": 5000},
                                  "J": {"replicates": 8, "budget": 10000}}, "teacher quality")
    require(len(plan["pilot_sources"]) == 16 and set(plan["pilot_sources"]) <=
            {s["seed"] for s in sources if s["split"] == "TRAIN"}, "pilot split")


def identity_hash(root):
    return hashlib.sha256(root["root_id"].encode()).hexdigest()


def select_source(captures):
    """One early and one later root per combat when available; never backfill acts."""
    by_act = defaultdict(lambda: defaultdict(list))
    ids = set()
    for root in captures:
        rid = root["root_id"]
        require(rid not in ids, "duplicate capture identity")
        ids.add(rid)
        require(root["act"] in (1, 2, 3), "unexpected act")
        by_act[root["act"]][root["combat_id"]].append(root)
    selected = []
    for act in sorted(by_act):
        pool = []
        for combat in by_act[act].values():
            ordered = sorted(combat, key=identity_hash)
            early = [r for r in ordered if r["state"]["state"]["turn"] <= 2]
            late = [r for r in ordered if r["state"]["state"]["turn"] > 2]
            chosen = [group[0] for group in (early, late) if group]
            chosen += [r for r in ordered if r not in chosen][:2 - len(chosen)]
            pool.extend(chosen)
        early = sorted([r for r in pool if r["state"]["state"]["turn"] <= 2], key=identity_hash)
        late = sorted([r for r in pool if r["state"]["state"]["turn"] > 2], key=identity_hash)
        interleaved = []
        for i in range(max(len(early), len(late), 0)):
            interleaved += [group[i] for group in (early, late) if i < len(group)]
        selected += interleaved[:8]
    return selected


def select(plan, captures, sha, pilot=False):
    validate_plan(plan)
    source_splits = {s["seed"]: s["split"] for s in plan["sources"]}
    groups = defaultdict(list)
    for root in captures:
        require(root["source_seed"] in source_splits and root["executable_git_sha"] == sha
                and canonical(root["capture_config"]) == canonical(CAPTURE), "capture provenance/config")
        require(root["state"]["state"]["ascension"] == 0
                and root["state"]["state"]["player"]["characterClass"] == 0, "Ironclad A0 capture")
        groups[root["source_seed"]].append(root)
    selected = []
    for seed in sorted(groups):
        roots = select_source(groups[seed])
        judged = min(roots, key=identity_hash)["root_id"] if roots and source_splits[seed] != "TRAIN" else None
        if pilot:
            require(seed in plan["pilot_sources"], "nonpilot source")
            roots = [r for act in (1, 2, 3) for r in [x for x in roots if x["act"] == act][:2]]
        for root in roots:
            selected.append({"root": root, "split": source_splits[seed],
                             "judge_selected": root["root_id"] == judged})
    return seal({"schema": "silver_prior_selection_v1", "plan_sha256": plan["sha256"],
                 "executable_git_sha": sha, "pilot": pilot, "entries": selected,
                 "capture_sha256": digest(captures)})


def job_for(entry, plan, sha, role="L", fixture=False):
    return {"schema": "silver_prior_label_job_v1", "executable_git_sha": sha,
            "plan_sha256": plan["sha256"], "fixture_only": fixture,
            "teacher_identity": plan["teacher_identity"], "estimator": role,
            "replicates": 2 if fixture else 8,
            "continuation_budget": 8 if fixture else plan["teachers"][role]["budget"],
            **entry}


MASK = (1 << 64) - 1


def fnv(text):
    value = 1469598103934665603
    for byte in text.encode():
        value = ((value ^ byte) * 1099511628211) & MASK
    return value or 1


def replicate_seed(base, index):
    x = base ^ (((index + 1) * 0x9e3779b97f4a7c15) & MASK)
    x = ((x ^ (x >> 30)) * 0xbf58476d1ce4e5b9) & MASK
    x = ((x ^ (x >> 27)) * 0x94d049bb133111eb) & MASK
    return (x ^ (x >> 31)) or 1


def validate_raw(raw, job, allow_fixture=False):
    require(raw["schema"] == "silver_prior_raw_root_v1" and raw["job"] == job,
            "raw job/SHA/schema mismatch")
    require(allow_fixture or not job["fixture_only"], "fixture forbidden for training")
    require(raw["accepted"] and not raw["failures"], "failed whole root")
    root, role = job["root"], job["estimator"]
    require(role in ("L", "J") and (role != "J" or
            (job["split"] != "TRAIN" and job["judge_selected"])), "judge isolation")
    require(raw["evaluator"]["definition"] == "forced_action_original_root_value_v2"
            and raw["evaluator"]["contract"] == "CONTROL"
            and raw["evaluator"]["reuse_mode"] == "none", "evaluator contract")
    native = root["native_order"]
    actions = {a["fingerprint"]: a for a in raw["actions"]}
    require(len(actions) == len(raw["actions"]) == len(native)
            and set(actions) == set(native), "incomplete action surface")
    base = fnv(f'{job["teacher_identity"]}/{root["root_id"]}/{role}')
    values = []
    for fp, semantic in zip(native, root["actions"], strict=True):
        action = actions[fp]
        require(action["accepted"] and action["semantic_action"] == semantic, "action identity")
        reps = action["replicates"]
        require(len(reps) == job["replicates"] and [r["index"] for r in reps] ==
                list(range(job["replicates"])), "missing/duplicate replicate")
        for r in reps:
            for key in ("value", "leaf_root_value", "victory_baseline_correction", "applied_baseline_correction"):
                require(type(r[key]) in (int, float) and math.isfinite(r[key]), "nonfinite label")
            terminal = r["terminal_after_action"]
            require(r["requested_simulations"] == job["continuation_budget"]
                    and r["simulations"] == (0 if terminal else job["continuation_budget"]), "budget")
            denominator = 1 if terminal else r["simulations"]
            require(0 <= r["victories"] <= denominator and (not terminal or
                    r["victories"] == int(r["terminal_victory"])), "victory accounting")
            require(math.isclose(r["applied_baseline_correction"],
                    r["victory_baseline_correction"] * r["victories"] / denominator, abs_tol=1e-10)
                    and math.isclose(r["value"], r["leaf_root_value"] + r["applied_baseline_correction"],
                                     abs_tol=1e-10), "original-root correction")
            require(r["rng_identity"] == replicate_seed(base, r["index"]), "replicate identity/CRN")
            require(r["stochastic"] == (r["immediate_rng_counter_after"] != r["immediate_rng_counter_before"]),
                    "immediate RNG provenance")
        mean = sum(r["value"] for r in reps) / len(reps)
        require(math.isclose(mean, action["mean_corrected_value"], abs_tol=1e-10), "mean label")
        values.append(mean)
    return values


def shard(raw, job, vocab, allow_fixture=False):
    values = validate_raw(raw, job, allow_fixture)
    return seal({"schema": "silver_prior_shard_v1", "replay": raw,
                 "vocabulary_sha256": vocab["sha256"],
                 "observation": project(job["root"], vocab, raw["reference"]),
                 "values": values})


def load_training(path, vocab, expected_job):
    require(expected_job["estimator"] == "L" and expected_job["split"] == "TRAIN", "training split only")
    stored = read(path)
    check_seal(stored)
    expected = shard(stored["replay"], expected_job, vocab)
    require(stored == expected, "projection/label/hash mismatch")
    # This is the complete training-facing contract. No provenance is returned.
    return stored["observation"], stored["values"]


def load_training_corpus(directory):
    """Release-gated iterator; cross-split duplicates never enter training."""
    directory = Path(directory)
    release = read(directory / "release.json")
    check_seal(release)
    require(release["schema"] == "silver_prior_release_v1" and release["training_ready"],
            "corpus has not passed integrity validation")
    binding, selection, vocab, plan = [read(directory / name) for name in
                                      ("binding.json", "selection.json", "vocabulary.json", "plan.json")]
    for value in (binding, selection, plan):
        check_seal(value)
    require(release["binding_sha256"] == binding["sha256"]
            and release["selection_sha256"] == selection["sha256"]
            and binding["plan_sha256"] == plan["sha256"]
            and plan["vocabulary_sha256"] == vocab["sha256"], "release binding")
    checksums = {f["path"]: f["sha256"] for f in release["files"]}
    require(len(checksums) == len(release["files"]), "duplicate checksum entry")
    for entry in selection["entries"]:
        if entry["split"] != "TRAIN" or entry["root"]["root_id"] in release["quarantined_roots"]:
            continue
        relative = f'shards/L/{identity_hash(entry["root"])}.json.gz'
        require(relative in checksums and file_hash(directory / relative) == checksums[relative],
                "release shard checksum")
        yield load_training(directory / relative, vocab,
                            job_for(entry, plan, binding["executable_git_sha"]))


def audit(shards, expected_entries=()):
    """Integrity/coverage only: deliberately never summarizes J or test Q values."""
    counts, acts, encounters, turns, hp, observed = Counter(), Counter(), Counter(), Counter(), Counter(), set()
    sources, combats, roots, duplicates = set(), set(), set(), defaultdict(list)
    for stored in shards:
        check_seal(stored)
        job = stored["replay"]["job"]
        if job["estimator"] != "L":
            continue
        root, obs = job["root"], stored["observation"]
        require(root["root_id"] not in roots, "duplicate root shard")
        roots.add(root["root_id"])
        sources.add(root["source_seed"])
        combats.add((root["source_seed"], root["combat_id"]))
        counts["legal_actions"] += len(obs["candidates"])
        counts["replicate_rows"] += sum(len(a["replicates"]) for a in stored["replay"]["actions"])
        acts[str(root["act"])] += 1
        encounters[str(root["encounter"])] += 1
        turns[str(obs["global"]["turn"])] += 1
        hp[str(obs["player"]["curHp"])] += 1
        observed.update(c["card_id"] for c in obs["cards"])
        normalized = {**obs, "candidates": sorted(obs["candidates"], key=canonical)}
        duplicates[digest(normalized)].append({"root_id": root["root_id"], "split": job["split"]})
    overlap = [group for group in duplicates.values() if len({r["split"] for r in group}) > 1]
    # Fail closed at corpus level until ALL cross-split aliases are quarantined.
    return {"schema": "silver_prior_integrity_report_v1", "source_seeds": len(sources),
            "combats": len(combats), "decision_roots": len(roots), **counts,
            "act": acts, "encounter": encounters, "turn": turns, "raw_hp": hp,
            "compact_vocabulary_observed": sorted(observed), "cross_split_duplicates": overlap,
            "training_ready": not overlap and bool(roots),
            "duplicate_policy": "quarantine every root in each cross-split overlap group before training",
            "intended_roots": len(expected_entries),
            "missing_roots": sorted({e["root"]["root_id"] for e in expected_entries} - roots)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("freeze"); p.add_argument("directory", type=Path)
    p = sub.add_parser("select")
    for key in ("plan", "capture", "output", "sha"):
        p.add_argument(key)
    p.add_argument("--pilot", action="store_true")
    p = sub.add_parser("validate-plan"); p.add_argument("plan")
    args = parser.parse_args()
    if args.command == "freeze":
        result = freeze(args.directory)
        print(canonical({"plan_sha256": result["sha256"], "source_seeds": len(result["sources"])}))
    elif args.command == "validate-plan":
        validate_plan(read(args.plan)); print("plan valid: 384 TRAIN / 64 VALIDATION / 64 LOCKED_TEST")
    else:
        publish(args.output, select(read(args.plan), rows(args.capture), args.sha, args.pilot))


if __name__ == "__main__":
    main()
