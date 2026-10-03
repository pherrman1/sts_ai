#!/usr/bin/env python3
"""#397 Stage 2: public-history feature families for run-win prediction.

Offline only on the frozen #334 corpus: TRAIN/VALIDATION rows, no gameplay
seeds, no C++ build, no TEST rows (TEST sources are skipped before any
history table row is used; the dataset adapter blocks TEST feature reads).

History is reconstructed per trajectory from recorded public observations:
- fights: `combat.csv` (`fightIdx`, `floor`, `encounter`);
- event identities: `decision.csv` event screens (`eventId`);
- relic offers: `decision.csv` shop `relics`, `boss_relic` `relics` and
  reward-screen `relics`.
Branch files start at their deviating screen (branch `rowIdx` 0) and keep the
source's `fightIdx` numbering, so a branch's prefix is the source's history
before the deviation: source decision rows with `rowIdx` below the deviating
source row (MAP deviations: source rows with `floor` <= deviation floor) and
source fights with `fightIdx` below the branch's first fight. A MAP row at
floor F sees every item recorded at floor <= F, because the map action follows
all screens of floor F. Screens with a single option are not captured by the
decision sink, so an event whose only captured screen is a singleton has no
recorded identity; the coverage report counts those from the manifest logs.

Families (one conceptual variable each, added to the public-safe baseline):
- H1 relic history: `relicSeenNotOwned_<id>` = offered at or before this row
  and not owned in the row's own rich `r<id>` column.
- H2 event history: `eventSeen_<id>` = event identity observed.
- H3 encounter history: `fought_<encounter>` = fights against that encounter.
New columns are kept only when TRAIN-variable (same 1e-12 rule as A3).

Preregistered comparison (frozen before any arm was trained):
- Baseline P: the #397 Stage 1 public-safe set (A3 TRAIN-variable mask minus
  `nextEliteId`, `nextFight0..2`; 457 features).
- Arms P+H1, P+H2, P+H3. Recipe: frozen A3 X1 parameters, XGBoost seeds
  0..4; each arm's prediction is the mean probability of its five seeds
  (Stage 1 showed single-seed noise of ~0.007-0.010 NLL).
- Primary: ensemble VALIDATION NLL delta (arm - P), source-clustered paired
  95% CI (2,000 replicates, seed 0).
- `<FAMILY>_HISTORY_USEFUL` if delta <= -0.002 and CI upper < 0;
  `<FAMILY>_HISTORY_LOW_VALUE` if CI lower > -0.002; otherwise INCONCLUSIVE.
- Secondary: per-seed deltas, Brier/AUC/ECE, act/pre-boss slices, sibling
  ranking. Derived public probabilities (Stage 2b-2d) are separate work.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAMILIES = ("H1", "H2", "H3")
SEEDS = (0, 1, 2, 3, 4)
MATERIAL_NLL = 0.002
VARIANCE_THRESHOLD = 1e-12


class HistoryError(ValueError):
    pass


class Trajectory:
    """Public observations in recorded order for one source or branch."""

    def __init__(self):
        self.fights = []   # (fightIdx, floor, encounter)
        self.screens = []  # (rowIdx, floor, events(set), relics(set))


def screen_observations(screen, contents):
    events, relics = set(), set()
    if screen == "event":
        events.add(int(contents["eventId"]))
    elif screen in ("shop",):
        relics.update(int(r["id"]) for r in contents.get("relics", []))
    elif screen in ("boss_relic", "rewards"):
        relics.update(int(r) for r in contents.get("relics", []))
    return events, relics


def history_items(source, branch=None, deviation=None):
    """Return (fights, screens) of the full trajectory, prefix included.

    deviation: dict(kind='MAP'|'OTHER', floor=int, row=int|None) for branches.
    """
    if branch is None:
        return list(source.fights), list(source.screens)
    if deviation["kind"] == "MAP":
        prefix = [s for s in source.screens if s[1] <= deviation["floor"]]
    else:
        prefix = [s for s in source.screens if s[0] < deviation["row"]]
    if branch.fights:
        first = min(f[0] for f in branch.fights)
        fight_prefix = [f for f in source.fights if f[0] < first]
        ambiguous = False
    else:
        fight_prefix = [f for f in source.fights if f[1] <= deviation["floor"]]
        ambiguous = any(f[1] == deviation["floor"] for f in source.fights)
    # Prefix screens get negative order keys; floor carries the cut-off.
    return fight_prefix + list(branch.fights), prefix + list(branch.screens), ambiguous


def row_features(fights, screens, floor):
    """Public history visible at a MAP row on `floor` (items at floor <= floor)."""
    fought = defaultdict(int)
    for _, f, enc in fights:
        if f <= floor:
            fought[enc] += 1
    events, relics = set(), set()
    for _, f, ev, rel in screens:
        if f <= floor:
            events |= ev
            relics |= rel
    return fought, events, relics


def load_histories(data, splits):
    """Per (seed, branchId): (fights, screens, ambiguous_fight_prefix)."""
    from tools.vwin_refresh_dataset import source_split
    csv.field_size_limit(1 << 30)
    keep = lambda seed: source_split(seed) in splits
    trajectories = defaultdict(Trajectory)
    for table in data.corpus.tables("combat.csv"):
        if not any(keep(s) for s in table.component.source_seeds):
            continue
        with table.path.open(newline="") as f:
            for r in csv.DictReader(f):
                seed = int(r["sourceSeed"])
                if keep(seed):
                    trajectories[seed, r["branchId"]].fights.append(
                        (int(r["fightIdx"]), int(r["floor"]), r["encounter"]))
    source_rows = {}  # (seed, decisionIdx) -> rowIdx in source decision.csv
    for table in data.corpus.tables("decision.csv"):
        if not any(keep(s) for s in table.component.source_seeds):
            continue
        with table.path.open(newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            ix = {n: header.index(n) for n in ("sourceSeed", "branchId", "rowIdx", "decisionIdx",
                                               "floor", "screen", "screenContents")}
            for r in reader:
                seed = int(r[ix["sourceSeed"]])
                if not keep(seed):
                    continue
                branch, row = r[ix["branchId"]], int(r[ix["rowIdx"]])
                ev, rel = screen_observations(r[ix["screen"]], json.loads(r[ix["screenContents"]]))
                trajectories[seed, branch].screens.append((row, int(r[ix["floor"]]), ev, rel))
                if branch == "source" and int(r[ix["decisionIdx"]]) >= 0:
                    source_rows[seed, int(r[ix["decisionIdx"]])] = row
    source_floor = {}
    for table in data.corpus.tables("decisions.csv"):
        if not any(keep(s) for s in table.component.source_seeds):
            continue
        with table.path.open(newline="") as f:
            for r in csv.DictReader(f):
                seed = int(r["sourceSeed"])
                if keep(seed) and r["branchId"] == "source":
                    source_floor[seed, int(r["decisionIdx"])] = (r["type"], int(r["floor"]))
    deviations = {}
    for table in data.corpus.tables("branches.csv"):
        if not any(keep(s) for s in table.component.source_seeds):
            continue
        with table.path.open(newline="") as f:
            for r in csv.DictReader(f):
                seed = int(r["sourceSeed"])
                if not keep(seed):
                    continue
                idx = int(r["decisionIdx"])
                kind, floor = source_floor[seed, idx]
                if kind == "MAP":
                    deviations[seed, r["branchId"]] = dict(kind="MAP", floor=floor, row=None)
                else:
                    if (seed, idx) not in source_rows:
                        raise HistoryError(f"deviation row missing in source decision.csv: {seed} {idx}")
                    deviations[seed, r["branchId"]] = dict(kind="OTHER", floor=floor,
                                                          row=source_rows[seed, idx])
    result, ambiguous = {}, 0
    for (seed, branch), traj in trajectories.items():
        traj.fights.sort(); traj.screens.sort(key=lambda s: s[0])
    for (seed, branch), traj in list(trajectories.items()):
        if branch == "source":
            result[seed, branch] = (traj.fights, traj.screens)
        else:
            if (seed, branch) not in deviations:
                raise HistoryError(f"branch without deviation record: {seed} {branch}")
            fights, screens, amb = history_items(trajectories[seed, "source"], traj,
                                                 deviations[seed, branch])
            ambiguous += amb
            result[seed, branch] = (fights, screens)
    return result, ambiguous, len(deviations)


def event_identity_gaps(data, splits):
    """Captured vs singleton (identity-less) event screens from manifest logs."""
    from tools.vwin_refresh_dataset import source_split
    captured = singleton = 0
    for component in data.corpus.components:
        if not any(source_split(s) in splits for s in component.source_seeds):
            continue
        sink = json.loads(component.manifest_path.read_text())["decisionSink"]
        for trajectory in sink["trajectories"]:
            for entry in trajectory["decisionLog"]:
                if entry["screen"] == "event":
                    if entry["rowIdx"] >= 0:
                        captured += 1
                    elif entry["optionCount"] <= 1:
                        singleton += 1
    return {"captured_event_screens": captured, "singleton_event_screens": singleton}


def build_family_columns(metadata, X, names, histories):
    """Raw per-row family columns (all IDs observed anywhere in the split)."""
    relic_cols = {n: names.index(n) for n in names if n.startswith("r") and n[1:].isdigit()}
    per_row = []
    missing = 0
    for i, m in enumerate(metadata):
        key = (int(m["sourceSeed"]), m["branchId"])
        if key not in histories:
            missing += 1
            per_row.append((defaultdict(int), set(), set()))
            continue
        fights, screens = histories[key]
        per_row.append(row_features(fights, screens, int(m["floor"])))
    out = {}
    for fam, extract in (("H1", lambda i, h: {f"relicSeenNotOwned_{r}": 1.0 for r in h[2]
                                             if X[i, relic_cols[f"r{r}"]] == 0}),
                         ("H2", lambda i, h: {f"eventSeen_{e}": 1.0 for e in h[1]}),
                         ("H3", lambda i, h: {f"fought_{k}": float(v) for k, v in h[0].items()})):
        out[fam] = [extract(i, h) for i, h in enumerate(per_row)]
    return out, missing


def materialize(rows, columns):
    index = {c: j for j, c in enumerate(columns)}
    M = np.zeros((len(rows), len(columns)), dtype=np.float32)
    for i, row in enumerate(rows):
        for c, v in row.items():
            if c in index:
                M[i, index[c]] = v
    return M


def train_variable_columns(rows):
    """Columns that are not constant over all rows (absent entries count as 0)."""
    values, counts = defaultdict(set), defaultdict(int)
    for row in rows:
        for c, v in row.items():
            values[c].add(v)
            counts[c] += 1
    return sorted(c for c, vals in values.items() if len(vals) > 1 or counts[c] < len(rows))


def verdict(family, delta):
    mean, (lo, hi) = delta["mean"], delta["ci95"]
    if mean <= -MATERIAL_NLL and hi < 0:
        label = f"{family}_HISTORY_USEFUL"
    elif lo > -MATERIAL_NLL:
        label = f"{family}_HISTORY_LOW_VALUE"
    else:
        label = f"{family}_HISTORY_INCONCLUSIVE"
    return {"label": label, "delta_nll": mean, "ci95": [lo, hi]}


def write_json(path, value):
    with Path(path).open("x") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def run(index, a3_run, output, threads):
    from tools.vwin_refresh_dataset import validated_dataset
    from tools.vwin_refresh_evaluation import evaluate_predictions, sibling_ranking, clustered_delta
    from tools.vwin_refresh_model import sha256, tool_identity
    from tools.vwin_refresh_training import train_xgb_fixed, versions
    from tools.analyze_vwin_public_info_397 import arms
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    a3_run = Path(a3_run)
    frozen = json.loads((a3_run / "validation.json").read_text())["X1"]["training"]["selected"]
    preflight = json.loads((a3_run / "preflight.json").read_text())
    data = validated_dataset(index)
    names = list(data.feature_names)
    base = arms(preflight["selected_feature_names"])["B"]
    histories, ambiguous, branch_count = load_histories(data, {"TRAIN", "VALIDATION"})
    gaps = event_identity_gaps(data, {"TRAIN", "VALIDATION"})
    xt, yt, mt = data.read("TRAIN")
    xv, yv, mv = data.read("VALIDATION")
    ft, missing_t = build_family_columns(mt, xt, names, histories)
    fv, missing_v = build_family_columns(mv, xv, names, histories)
    if missing_t or missing_v:
        write_json(output / "stop.json", {"missing_train": missing_t, "missing_validation": missing_v})
        raise HistoryError("STOP: MAP rows without reconstructed history")
    base_cols = [names.index(f) for f in base]
    family_columns = {fam: train_variable_columns(ft[fam]) for fam in FAMILIES}
    branches = data.branches("VALIDATION")
    seeds_v = np.array([int(m["sourceSeed"]) for m in mv])
    params = dict(frozen["params"], nthread=threads)
    results, predictions = {}, {}
    for arm in ("P",) + FAMILIES:
        extra = family_columns.get(arm, [])
        Xt = np.hstack([xt[:, base_cols], materialize(ft[arm], extra)]) if extra else xt[:, base_cols]
        Xv = np.hstack([xv[:, base_cols], materialize(fv[arm], extra)]) if extra else xv[:, base_cols]
        features = list(base) + extra
        per_seed = []
        for seed in SEEDS:
            model, report = train_xgb_fixed(Xt, yt, Xv, yv, features, params=dict(params, seed=seed))
            p = model.predict(Xv)
            predictions[f"{arm}_seed{seed}"] = p
            per_seed.append({"seed": seed, "tree_count": report["tree_count"],
                             "validation_nll": report["validation_nll"]})
            print(arm, seed, len(features), report["tree_count"], report["validation_nll"], flush=True)
        ensemble = np.mean([predictions[f"{arm}_seed{s}"] for s in SEEDS], axis=0)
        predictions[f"{arm}_ensemble"] = ensemble
        results[arm] = {"feature_count": len(features), "new_columns": extra, "per_seed": per_seed,
                        "validation": evaluate_predictions(yv, ensemble, mv),
                        "siblings": sibling_ranking(mv, ensemble, branches)}
        del Xt, Xv
    deltas, verdicts = {}, {}
    for fam in FAMILIES:
        deltas[fam] = {"ensemble": clustered_delta(yv, predictions["P_ensemble"],
                                                   predictions[f"{fam}_ensemble"], seeds_v),
                       "per_seed": {str(s): clustered_delta(yv, predictions[f"P_seed{s}"],
                                                            predictions[f"{fam}_seed{s}"], seeds_v)["nll"]
                                    for s in SEEDS}}
        verdicts[fam] = verdict(fam, deltas[fam]["ensemble"]["nll"])
    np.savez_compressed(output / "validation_predictions.npz", labels=yv, source_seeds=seeds_v, **predictions)
    report = {
        "schema": "vwin_history_397_stage2_v1", "issue": 397, "tooling": tool_identity(),
        "versions": versions(), "threads": threads,
        "corpus_index": str(Path(index).resolve()), "corpus_sha256": sha256(index),
        "a3_run": str(a3_run.resolve()),
        "a3_hashes": {n: sha256(a3_run / n) for n in ("validation.json", "preflight.json")},
        "baseline_features": base, "coverage": {
            "trajectories": len(histories), "branches": branch_count,
            "ambiguous_branch_fight_prefixes": ambiguous, **gaps,
            "train_rows": len(mt), "validation_rows": len(mv)},
        "results": results, "paired_deltas": deltas, "verdicts": verdicts,
        "test_rows_read": False, "elapsed_seconds": time.time() - started}
    write_json(output / "report.json", report)
    print(json.dumps({"verdicts": verdicts, "coverage": report["coverage"],
                      "new_columns": {f: len(family_columns[f]) for f in FAMILIES}}, indent=2))
    return report


def _self_test():
    src, br = Trajectory(), Trajectory()
    src.fights = [(0, 1, "Cultist"), (1, 3, "Small Slimes"), (2, 5, "Lagavulin")]
    src.screens = [(0, 0, {5}, set()), (1, 2, set(), {87, 67}), (2, 3, {34}, set()), (3, 6, set(), {9})]
    fights, screens = history_items(src)
    fought, events, relics = row_features(fights, screens, 3)
    assert dict(fought) == {"Cultist": 1, "Small Slimes": 1} and events == {5, 34} and relics == {87, 67}
    # OTHER deviation at source row 2 (floor 3); branch row 0 is the deviating screen.
    br.fights = [(2, 5, "Gremlin Nob")]
    br.screens = [(0, 3, {34}, set()), (1, 4, set(), {20})]
    fights, screens, amb = history_items(src, br, dict(kind="OTHER", floor=3, row=2))
    assert not amb and [f[2] for f in fights] == ["Cultist", "Small Slimes", "Gremlin Nob"]
    fought, events, relics = row_features(fights, screens, 4)
    assert events == {5, 34} and relics == {87, 67, 20} and "Lagavulin" not in fought
    # MAP deviation at floor 2 without branch fights: prefix by floor.
    fights, screens, amb = history_items(src, Trajectory(), dict(kind="MAP", floor=2, row=None))
    assert [f[2] for f in fights] == ["Cultist"] and not amb
    assert {s[0] for s in screens} == {0, 1}
    rows = [{"a": 1.0}, {"a": 1.0}, {}, {"b": 2.0, "a": 1.0}]
    assert train_variable_columns(rows) == ["a", "b"]
    assert train_variable_columns([{"a": 1.0}, {"a": 1.0}]) == []
    M = materialize(rows, ["a", "b"])
    assert M.tolist() == [[1, 0], [1, 0], [0, 0], [1, 2]]
    ev, rel = screen_observations("shop", {"relics": [{"id": 3}, {"id": 4}]})
    assert rel == {3, 4} and not ev
    assert screen_observations("boss_relic", {"relics": [1, 2, 3]})[1] == {1, 2, 3}
    assert screen_observations("event", {"eventId": 41})[0] == {41}
    ci = lambda m, lo, hi: {"mean": m, "ci95": [lo, hi]}
    assert verdict("H1", ci(-.004, -.007, -.001))["label"] == "H1_HISTORY_USEFUL"
    assert verdict("H1", ci(.0, -.0015, .0015))["label"] == "H1_HISTORY_LOW_VALUE"
    assert verdict("H1", ci(-.001, -.004, .002))["label"] == "H1_HISTORY_INCONCLUSIVE"
    print("vwin history #397 self-test: PASS")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--index")
    parser.add_argument("--a3-run")
    parser.add_argument("--output")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    if not (args.index and args.a3_run and args.output):
        parser.error("--index, --a3-run and --output are required")
    run(args.index, args.a3_run, args.output, args.threads)
    return 0


if __name__ == "__main__":
    sys.exit(main())
