#!/usr/bin/env python3
"""Rebuild the three near-full Attention-chain inputs that have no committed producer.

The near-full chain reads three files under its `--parent` folder that were
made by uncommitted scripts (#418 retrain blocker B3):

- `full-union-downstream-labels-v1/` (`labels.npz`, `affected_rows.jsonl`,
  `preparation.json`): per-row relic-trajectory constraints and
  escape/Writhing Mass/Ritual Dagger flags, plus the winning rows whose gold
  or Writhing/Ritual outcome needs a joint native target
  (`combat_transition_near_full_downstream.py prepare`);
- `full-union-test-states-v1.json` + `.jsonl`: the TEST rows with their
  RAW pre/post state (`near_full_evaluate`, `qualify`, `final_exact_gold`);
- `brew-native-label-audit-v1.json`: native Entropic Brew generation replay
  and the rows where a generated Brew was itself drunk (`near_full_exposure`,
  `qualify`, `final_exact_gold`).

The definitions here are reconstructed from the consumers and the recorded
evidence counts (near_full_combat_support_2026-09-14/REPORT.md). Before a
retrain relies on them, `compare` must find no difference against the
production inputs on the production corpus (the reproduce-old gate). It
compares content (arrays, row sets and per-row JSON values), not bytes,
because the original scripts' serialization is not recorded.

The population is the `potion-trajectory-v2` cache under the parent, whose
ids must be every corpus row in order: drop out-of-envelope rows before
`potion_trajectory_evaluate prepare` instead of here.

Gate on the production corpus (no clean tree needed):
  python3 -c "from tools import ctm_near_full_inputs as m; m.build(PARENT, CORPUS, OUT, 'gate')"
  ctm_near_full_inputs.py compare --old PARENT --new OUT

usage:
  ctm_near_full_inputs.py produce --parent DIR --out DIR --sha GIT_SHA
  ctm_near_full_inputs.py compare --old DIR --new DIR
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from tools import combat_transition_composed as c
from tools import combat_transition_composed_evaluate as e
from tools import combat_transition_gold as gold
from tools import combat_transition_near_full_support as support
from tools import combat_transition_potion_trajectory as t
from tools import combat_transition_potion_trajectory_evaluate as trajectory
from tools import combat_transition_relic_legality as relic
from tools import combat_transition_sparse_evaluate as sparse

LABELS = "full-union-downstream-labels-v1"
TEST_STATES = "full-union-test-states-v1"
BREW_AUDIT = "brew-native-label-audit-v1.json"
BREW = c.base._POTION_IDS["ENTROPIC_BREW"]
SMOKE = c.base._POTION_IDS["SMOKE_BOMB"]
DAGGER = c.base._CARD_IDS["RITUAL_DAGGER"]
BLOOM = c.base._RELIC_IDS["MARK_OF_THE_BLOOM"]
OMAMORI = c.base._RELIC_IDS["OMAMORI"]


def produce(parent: Path, out: Path, sha: str) -> dict:
    sparse.frozen(sha)
    _, _, meta = trajectory.load(parent / "potion-trajectory-v2")  # verifies the frozen source data
    return build(parent, e.CORPUS, out, sha)


def build(parent: Path, corpus: Path, out: Path, sha: str) -> dict:
    """Produce the inputs without the clean-tree and source-data checks (used by the reproduce-old gate)."""
    if out.exists():
        raise ValueError("refusing overwrite")
    folder = parent / "potion-trajectory-v2"
    meta = json.loads((folder / "preparation.json").read_text())
    if c.base.sha256(folder / "cache.npz") != meta["cacheSha256"]:
        raise ValueError("trajectory cache differs from its receipt")
    with np.load(folder / "cache.npz") as raw:
        cache = {k: raw[k] for k in ("ids", "source", "split", "win")}
    n = len(cache["ids"])
    if not np.array_equal(cache["ids"], np.arange(n)):
        raise ValueError("trajectory cache ids must be every corpus row in order")
    escaped = np.zeros(n, bool); writhing = np.zeros(n, bool); dagger = np.zeros(n, bool)
    observed = np.zeros((n, len(c.TRAINED_GROUPS)), bool)
    compatible = {g: np.ones((n, relic.HEAD_CLASSES[g]), bool) for g in c.TRAINED_GROUPS}
    affected, tests, examples = [], [], []
    test_counts = Counter(); brew_counts = Counter(); rounds_hist = Counter()
    original = c.base.supported_reasons
    with support.candidate_contract() as (_original, certified):
        for index, row in enumerate(c.base.iter_rows(corpus)):
            if index >= n or row["sourceSeed"] != int(cache["source"][index]):
                raise ValueError("corpus alignment differs")
            pre, post, pi = row["transition"]["pre"], row["transition"]["post"], row["predictorInput"]
            outcome = row["transition"]["combatOutcome"]
            win = outcome == c.base.WIN
            if win != bool(cache["win"][index]):
                raise ValueError(f"win label differs at {index}")
            escaped[index] = bool(post["smokeBombUsed"])
            writhing[index] = pi["globals"]["encounter"] == c.base.WRITHING_MASS_ID
            dagger[index] = any(card["id"] == DAGGER for card in pre["deck"])
            bloom = any(r["id"] == BLOOM for r in pre["relics"])
            # Omamori is the Writhing Mass event's target, not a trajectory
            # relic; strip it as combat_transition_sparse_validity does.
            strip = lambda relics: [r for r in relics if r["id"] != OMAMORI]
            constraints = relic.trajectory_constraints(strip(pre["relics"]), strip(post["relics"]),
                                                       pi["globals"]["encounter"], bloom)
            for j, g in enumerate(c.TRAINED_GROUPS):
                if g in constraints:
                    observed[index, j] = True
                    compatible[g][index] = np.isin(np.arange(relic.HEAD_CLASSES[g]), list(constraints[g]))
            reasons = original(pi, pre)
            if win and (writhing[index] or dagger[index] or any(gold.gold_reason(r) for r in reasons)):
                affected.append(dict(index=index, pre=pre, post=post, pi=pi))
            if int(cache["split"][index]) == 2:
                old = not reasons and certified(pi)
                tests.append(dict(index=index, pre=pre, post=post, pi=pi, outcome=outcome, old=old))
                test_counts["rows"] += 1; test_counts["previous179" if old else "recovered"] += 1
            if BREW in pre["potions"] or SMOKE in pre["potions"]:
                state = dict(pre["combatRng"][4]); target = post["combatRng"][4]; generated = []
                while state["counter"] < target["counter"]:
                    generated.append(t.brew.draw_native(state))
                if state != target:
                    raise ValueError(f"native Brew generation RNG mismatch at {index}")
                rounds = len(generated) // int(pre["potionCapacity"])
                brew_counts["rows"] += 1; brew_counts["win" if win else "death"] += 1
                brew_counts["generatedRounds"] += rounds; rounds_hist[str(rounds)] += 1
                brew_counts["escapeRows"] += int(escaped[index])
                brew_counts["consumedBrewRows"] += int(BREW in pre["potions"] and rounds > 0)
                # Recursive: more generation rounds than Brews held, so a
                # generated Brew was itself drunk.
                if rounds > pre["potions"].count(BREW):
                    brew_counts["recursiveBrewConsumption"] += 1
                    examples.append(dict(index=index, source=row["sourceSeed"], fight=row["fightIdx"], rounds=rounds,
                                         generated=generated, prePotions=pre["potions"], postPotions=post["potions"]))
            if index % 100000 == 0:
                print("near-full inputs", index, n, flush=True)
    if len(tests) != int((cache["split"] == 2).sum()) or index + 1 != n:
        raise ValueError("population differs from the trajectory cache")
    labels_dir = out / LABELS
    labels_dir.mkdir(parents=True)
    np.savez_compressed(labels_dir / "labels.npz", escaped=escaped, writhing=writhing, dagger=dagger, observed=observed,
                        **{f"compatible_{g}": v for g, v in compatible.items()})
    with (labels_dir / "affected_rows.jsonl").open("x") as stream:
        for record in affected:
            stream.write(json.dumps(record) + "\n")
    labels_meta = dict(sourceSha=sha, hashes=meta["hashes"], rows=n, survivors=int(cache["win"].sum()),
                       observedRows=int(observed.any(-1).sum()), affectedRows=len(affected),
                       preparationCacheSha256=meta["cacheSha256"], supportedChanged=False,
                       labelsSha256=c.base.sha256(labels_dir / "labels.npz"),
                       rawSha256=c.base.sha256(labels_dir / "affected_rows.jsonl"))
    c.base.json_dump(labels_dir / "preparation.json", labels_meta)
    with (out / f"{TEST_STATES}.jsonl").open("x") as stream:
        for record in tests:
            stream.write(json.dumps(record) + "\n")
    test_meta = dict(sourceSha=sha, corpusSha256=c.base.sha256(corpus), counts=dict(test_counts),
                     snapshotSha256=c.base.sha256(out / f"{TEST_STATES}.jsonl"))
    c.base.json_dump(out / f"{TEST_STATES}.json", test_meta)
    audit = dict(sourceSha=sha, counts=dict(brew_counts), generationRounds=dict(rounds_hist), problems={},
                 recursiveExamples=examples)
    c.base.json_dump(out / BREW_AUDIT, audit)
    summary = dict(labels={k: labels_meta[k] for k in ("rows", "survivors", "observedRows", "affectedRows")},
                   testStates=test_meta["counts"], brewAudit=audit["counts"])
    print(json.dumps(summary, indent=1))
    return summary


def _jsonl(path: Path) -> dict[int, dict]:
    with path.open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    return {int(r["index"]): r for r in rows}


def _rows_diff(name, old: dict, new: dict, keys) -> dict:
    only_old = sorted(set(old) - set(new)); only_new = sorted(set(new) - set(old))
    differing = [i for i in sorted(set(old) & set(new)) if any(old[i].get(k) != new[i].get(k) for k in keys)]
    return dict(name=name, old=len(old), new=len(new), onlyOld=len(only_old), onlyNew=len(only_new),
                differing=len(differing), examples=dict(onlyOld=only_old[:10], onlyNew=only_new[:10],
                                                        differing=differing[:10]))


def compare(old: Path, new: Path) -> dict:
    """Content diff of produced inputs against the production ones; empty `problems` passes."""
    problems = []
    with np.load(old / LABELS / "labels.npz") as a, np.load(new / LABELS / "labels.npz") as b:
        arrays = {}
        for k in sorted(set(a.files) | set(b.files)):
            if k not in a.files or k not in b.files:
                arrays[k] = "missing on one side"
            elif a[k].shape != b[k].shape or a[k].dtype != b[k].dtype:
                arrays[k] = f"shape/dtype {a[k].shape}/{a[k].dtype} vs {b[k].shape}/{b[k].dtype}"
            else:
                rows = np.flatnonzero((a[k] != b[k]).reshape(len(a[k]), -1).any(-1))
                arrays[k] = dict(differingRows=int(len(rows)), examples=rows[:10].tolist())
        problems += [k for k, v in arrays.items() if not (isinstance(v, dict) and v["differingRows"] == 0)]
    affected = _rows_diff("affected_rows", _jsonl(old / LABELS / "affected_rows.jsonl"),
                          _jsonl(new / LABELS / "affected_rows.jsonl"), ("pre", "post", "pi"))
    tests = _rows_diff("test_states", _jsonl(old / f"{TEST_STATES}.jsonl"), _jsonl(new / f"{TEST_STATES}.jsonl"),
                       ("pre", "post", "pi", "outcome", "old"))
    order = lambda root: [json.loads(l)["index"] for l in (root / f"{TEST_STATES}.jsonl").read_text().splitlines()]
    tests["sameOrder"] = order(old) == order(new)
    a = json.loads((old / BREW_AUDIT).read_text()); b = json.loads((new / BREW_AUDIT).read_text())
    brew = _rows_diff("brew_recursive", {r["index"]: r for r in a["recursiveExamples"]},
                      {r["index"]: r for r in b["recursiveExamples"]},
                      ("source", "fight", "rounds", "generated", "prePotions", "postPotions"))
    brew["counts"] = dict(old=a["counts"], new=b["counts"])
    brew["generationRounds"] = dict(old=a["generationRounds"], new=b["generationRounds"])
    for d in (affected, tests, brew):
        if d["onlyOld"] or d["onlyNew"] or d["differing"]:
            problems.append(d["name"])
    if not tests["sameOrder"]:
        problems.append("test_states order")
    # Consumers read only recursiveExamples; the counts are reported, not gated.
    result = dict(problems=problems, labels=arrays, affectedRows=affected, testStates=tests, brewAudit=brew)
    print(json.dumps(result, indent=1))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("produce")
    p.add_argument("--parent", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--sha", required=True)
    p = sub.add_parser("compare")
    p.add_argument("--old", required=True, type=Path)
    p.add_argument("--new", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "produce":
        produce(args.parent, args.out, args.sha)
    else:
        raise SystemExit(1 if compare(args.old, args.new)["problems"] else 0)


if __name__ == "__main__":
    main()
