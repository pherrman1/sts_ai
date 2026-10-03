#!/usr/bin/env python3
"""#397 Stage 2d: unknown-room outcome odds and next card-remove price.

Offline only on the frozen #334 corpus (TRAIN/VALIDATION; no gameplay seeds,
no C++ build, no TEST rows). Both families are functions of public state and
public history plus game rules, never of hidden RNG.

Rules checked against STS1 V2.3.4 `desktop-1.0.jar` (`javap -c -p`):
- ? rooms (`EventHelper.roll`, `resetProbabilities`): chances start each act
  at monster 0.1, shop 0.03, treasure 0.02 (floats). A roll fills 100 slots in
  order monster `(int)(m*100)`, shop `(int)(s*100)` (0 when the current room
  is a shop), treasure `(int)(t*100)`, then event. Tiny Chest forces a chest
  on its fourth ? room; Juzu Bracelet turns a monster result into an event.
  After the roll each chance resets to its base when chosen and otherwise
  grows by its base. Native `getEventRoomOutcomeHelper` matches.
- Remove price (`ShopScreen`): `purgeCost` starts at 75 and grows by 25 per
  paid removal; at shop open the shown price is `purgeCost`, x0.8 with The
  Courier, x0.5 with Membership Card (rounded), and 50 with Smiling Mask.
  Ascension >= 16 multiplies by 1.1 (asc 0 corpus; implemented for parity).

Public reconstruction per trajectory (branches inherit the source prefix
before their deviating screen, as in Stage 2):
- ? nodes: a MAP row whose `pvEvent` exceeds the previous MAP row's marks a ?
  node on that floor. Outcome: a NORMAL fight on that floor -> monster; a
  shop screen -> shop; a treasure screen -> treasure; otherwise event.
  Limitation: with Juzu Bracelet a rolled monster shows as an event, so the
  monster chance is reconstructed as if it were an event (rare).
- Current room is a shop when `pvShop` rose at this row or the ? outcome on
  this floor was a shop.
- Paid removals: shop decision rows whose chosen key is a removal transaction
  (`effect=1:source=4:transaction`) at floor <= F. Checked against every shop
  screen's displayed `removeCost`; STOP below 99% agreement.

Preregistered comparison (frozen before any arm was trained):
- P: 457-feature public-safe baseline. F5: P + `pQMonster`, `pQShop`,
  `pQTreasure`, `pQEvent` (next ? room). F6: P + `nextRemoveCost`.
- Frozen A3 X1 recipe, XGBoost seeds 0..4, 5-seed mean probability; ensemble
  VALIDATION NLL delta vs P with source-clustered paired 95% CI.
- `USEFUL` if delta <= -0.002 and CI upper < 0; `LOW_VALUE` if CI lower >
  -0.002; otherwise INCONCLUSIVE.
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

SEEDS = (0, 1, 2, 3, 4)
MATERIAL_NLL = 0.002
MIN_REMOVE_AGREEMENT = 0.99
REMOVAL = ":source=4:transaction"
F32 = np.float32
BASE = {"monster": F32(0.1), "shop": F32(0.03), "treasure": F32(0.02)}
COLUMNS = {"F5": ["pQMonster", "pQShop", "pQTreasure", "pQEvent"], "F6": ["nextRemoveCost"]}


class RoomsError(ValueError):
    pass


def question_odds(outcomes, current_is_shop, tiny_chest_counter=None, juzu=False):
    """Next ? room outcome probabilities after this act's ? outcomes."""
    m, s, t = BASE["monster"], BASE["shop"], BASE["treasure"]
    for outcome in outcomes:
        m = BASE["monster"] if outcome == "monster" else F32(m + BASE["monster"])
        s = BASE["shop"] if outcome == "shop" else F32(s + BASE["shop"])
        t = BASE["treasure"] if outcome == "treasure" else F32(t + BASE["treasure"])
    if tiny_chest_counter == 3:
        return {"pQMonster": 0.0, "pQShop": 0.0, "pQTreasure": 1.0, "pQEvent": 0.0}
    mi = int(F32(m * F32(100)))
    si = 0 if current_is_shop else int(F32(s * F32(100)))
    ti = int(F32(t * F32(100)))
    mi = min(mi, 100); si = min(si, 100 - mi); ti = min(ti, 100 - mi - si)
    p = {"pQMonster": mi / 100, "pQShop": si / 100, "pQTreasure": ti / 100}
    if juzu:
        p["pQMonster"] = 0.0
    p["pQEvent"] = 1 - p["pQMonster"] - p["pQShop"] - p["pQTreasure"]
    return p


def remove_cost(paid_removals, smiling_mask, courier, membership, ascension=0):
    purge = 75 + 25 * paid_removals
    if smiling_mask:
        return 50
    cost = purge
    for applies, mult in ((ascension >= 16, 1.1), (courier, 0.8), (membership, 0.5)):
        if applies:
            cost = int(np.floor(cost * mult + 0.5))  # MathUtils.round
    return cost


def relic_columns():
    from tools.analyze_vwin_public_info_397 import relic_names
    names = relic_names()
    return {n: f"r{names.index(n)}" for n in ("SMILING_MASK", "THE_COURIER", "MEMBERSHIP_CARD",
                                              "TINY_CHEST", "JUZU_BRACELET")}


def load_trajectories(data, splits):
    """Per (seed, branchId): fights [(floor, roomClass)], screens [(row, floor, screen, removal, removeCost, relics)]."""
    from tools.vwin_refresh_dataset import source_split
    csv.field_size_limit(1 << 30)
    keep = lambda seed: source_split(seed) in splits
    relic_cols = relic_columns()
    fights, screens = defaultdict(list), defaultdict(list)
    for table in data.corpus.tables("combat.csv"):
        if any(keep(s) for s in table.component.source_seeds):
            with table.path.open(newline="") as f:
                for r in csv.DictReader(f):
                    if keep(int(r["sourceSeed"])):
                        fights[int(r["sourceSeed"]), r["branchId"]].append(
                            (int(r["fightIdx"]), int(r["floor"]), r["roomClass"]))
    source_rows = {}
    for table in data.corpus.tables("decision.csv"):
        if not any(keep(s) for s in table.component.source_seeds):
            continue
        with table.path.open(newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            ix = {n: header.index(n) for n in ("sourceSeed", "branchId", "rowIdx", "decisionIdx", "floor",
                                               "screen", "screenContents", "candidates")}
            rix = {k: header.index(v) for k, v in relic_cols.items()}
            for r in reader:
                seed = int(r[ix["sourceSeed"]])
                if not keep(seed):
                    continue
                screen, branch, row = r[ix["screen"]], r[ix["branchId"]], int(r[ix["rowIdx"]])
                removal, cost = False, None
                if screen == "shop":
                    removal = REMOVAL in json.loads(r[ix["candidates"]])["chosenKey"]
                    cost = int(json.loads(r[ix["screenContents"]])["removeCost"])
                owned = {k: float(r[i]) > 0 for k, i in rix.items()}
                screens[seed, branch].append((row, int(r[ix["floor"]]), screen, removal, cost, owned))
                if branch == "source" and int(r[ix["decisionIdx"]]) >= 0:
                    source_rows[seed, int(r[ix["decisionIdx"]])] = row
    source_floor = {}
    for table in data.corpus.tables("decisions.csv"):
        if any(keep(s) for s in table.component.source_seeds):
            with table.path.open(newline="") as f:
                for r in csv.DictReader(f):
                    if keep(int(r["sourceSeed"])) and r["branchId"] == "source":
                        source_floor[int(r["sourceSeed"]), int(r["decisionIdx"])] = (r["type"], int(r["floor"]))
    deviations = {}
    for table in data.corpus.tables("branches.csv"):
        if any(keep(s) for s in table.component.source_seeds):
            with table.path.open(newline="") as f:
                for r in csv.DictReader(f):
                    seed = int(r["sourceSeed"])
                    if keep(seed):
                        kind, floor = source_floor[seed, int(r["decisionIdx"])]
                        deviations[seed, r["branchId"]] = (kind, floor, source_rows.get((seed, int(r["decisionIdx"]))))
    result = {}
    for key in set(fights) | set(screens) | set(deviations):
        seed, branch = key
        f, s = sorted(fights.get(key, [])), sorted(screens.get(key, []), key=lambda x: x[0])
        if branch != "source":
            kind, floor, row = deviations[key]
            sf, ss = sorted(fights.get((seed, "source"), [])), screens.get((seed, "source"), [])
            prefix_s = [x for x in ss if x[1] <= floor] if kind == "MAP" else [x for x in ss if x[0] < row]
            prefix_f = [x for x in sf if x[0] < f[0][0]] if f else [x for x in sf if x[1] <= floor]
            f, s = prefix_f + f, prefix_s + s
        result[key] = ([(x[1], x[2]) for x in f], s)
    return result, deviations


def check_remove_costs(histories):
    agree = total = 0
    for fights, screens in histories.values():
        removals = 0
        seen_rows = set()
        for i, (row, floor, screen, removal, cost, owned) in enumerate(screens):
            if screen != "shop":
                continue
            if cost is not None and cost >= 0:
                total += 1
                agree += cost == remove_cost(removals, owned["SMILING_MASK"], owned["THE_COURIER"],
                                             owned["MEMBERSHIP_CARD"])
            if removal and (floor, row) not in seen_rows:
                removals += 1
                seen_rows.add((floor, row))
    return {"shop_screens": total, "agree": agree, "rate": agree / total if total else None}


def map_trajectories(metadata, X, col):
    """Per trajectory: sorted [(floor, act, pvEvent, pvShop, row index or None)] incl. source prefix."""
    by = defaultdict(list)
    for i, m in enumerate(metadata):
        by[int(m["sourceSeed"]), m["branchId"]].append(
            (int(m["floor"]), int(m["act"]), int(X[i, col["pvEvent"]]), int(X[i, col["pvShop"]]), i))
    for v in by.values():
        v.sort(key=lambda t: (t[0], t[4]))
    out = {}
    for (seed, branch), rows in by.items():
        if branch == "source":
            out[seed, branch] = rows
        else:
            start = rows[0][0]
            prefix = [(f, a, e, s, None) for f, a, e, s, _ in by.get((seed, "source"), []) if f < start]
            out[seed, branch] = prefix + rows
    return out


def derive(metadata, X, names, histories):
    col = {n: i for i, n in enumerate(names)}
    rel = relic_columns()
    out = [None] * len(metadata)
    for key, rows in map_trajectories(metadata, X, col).items():
        fights, screens = histories.get(key, ([], []))
        normal = {f for f, rc in fights if rc == "NORMAL"}
        shop_floors = {s[1] for s in screens if s[2] == "shop"}
        treasure_floors = {s[1] for s in screens if s[2] == "treasure"}
        outcomes, act, prev = [], None, None
        removal_floors = sorted((s[1], s[0]) for s in screens if s[2] == "shop" and s[3])
        for floor, a, pv_event, pv_shop, i in rows:
            if a != act:
                outcomes, act = [], a
            q_here = prev is not None and pv_event > prev[2]
            outcome = None
            if q_here:
                outcome = ("monster" if floor in normal else "shop" if floor in shop_floors
                           else "treasure" if floor in treasure_floors else "event")
                outcomes.append(outcome)
            shop_here = (prev is not None and pv_shop > prev[3]) or outcome == "shop"
            if i is not None:
                x = X[i]
                tiny = int(x[col[rel["TINY_CHEST"]]]) - 1 if x[col[rel["TINY_CHEST"]]] > 0 else None
                odds = question_odds(outcomes, shop_here, tiny, x[col[rel["JUZU_BRACELET"]]] > 0)
                paid = len({r for f, r in removal_floors if f <= floor})
                cost = remove_cost(paid, x[col[rel["SMILING_MASK"]]] > 0, x[col[rel["THE_COURIER"]]] > 0,
                                   x[col[rel["MEMBERSHIP_CARD"]]] > 0, int(x[col["ascension"]]))
                out[i] = {"F5": odds, "F6": {"nextRemoveCost": float(cost)}}
            prev = (floor, a, pv_event, pv_shop)
    if any(o is None for o in out):
        raise RoomsError("rows without derived features")
    return out


def materialize(rows, family):
    return np.array([[r[family][c] for c in COLUMNS[family]] for r in rows], dtype=np.float32)


def label(arm, delta):
    mean, (lo, hi) = delta["mean"], delta["ci95"]
    if mean <= -MATERIAL_NLL and hi < 0:
        return f"{arm}_USEFUL"
    return f"{arm}_LOW_VALUE" if lo > -MATERIAL_NLL else f"{arm}_INCONCLUSIVE"


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
    histories, _ = load_trajectories(data, {"TRAIN", "VALIDATION"})
    remove_check = check_remove_costs(histories)
    if remove_check["rate"] is None or remove_check["rate"] < MIN_REMOVE_AGREEMENT:
        write_json(output / "stop.json", {"reason": "remove-cost reconstruction", "check": remove_check})
        raise RoomsError(f"STOP: remove-cost agreement {remove_check}")
    xt, yt, mt = data.read("TRAIN")
    xv, yv, mv = data.read("VALIDATION")
    dt, dv = derive(mt, xt, names, histories), derive(mv, xv, names, histories)
    cols = [names.index(f) for f in base]
    branches = data.branches("VALIDATION")
    seeds_v = np.array([int(m["sourceSeed"]) for m in mv])
    params = dict(frozen["params"], nthread=threads)
    results, predictions = {}, {}
    for arm in ("P", "F5", "F6"):
        Xt, Xv = xt[:, cols], xv[:, cols]
        features = list(base)
        if arm != "P":
            Xt = np.hstack([Xt, materialize(dt, arm)]); Xv = np.hstack([Xv, materialize(dv, arm)])
            features += COLUMNS[arm]
        variable = Xt.var(axis=0) > 1e-12
        features = [n for n, v in zip(features, variable) if v]
        Xt, Xv = Xt[:, variable], Xv[:, variable]
        per_seed = []
        for seed in SEEDS:
            model, report = train_xgb_fixed(Xt, yt, Xv, yv, features, params=dict(params, seed=seed))
            predictions[f"{arm}_seed{seed}"] = model.predict(Xv)
            per_seed.append({"seed": seed, "tree_count": report["tree_count"],
                             "validation_nll": report["validation_nll"]})
            print(arm, seed, len(features), report["tree_count"], report["validation_nll"], flush=True)
        ensemble = np.mean([predictions[f"{arm}_seed{s}"] for s in SEEDS], axis=0)
        predictions[f"{arm}_ensemble"] = ensemble
        results[arm] = {"feature_count": len(features), "per_seed": per_seed,
                        "validation": evaluate_predictions(yv, ensemble, mv),
                        "siblings": sibling_ranking(mv, ensemble, branches)}
    deltas = {a: clustered_delta(yv, predictions["P_ensemble"], predictions[f"{a}_ensemble"], seeds_v)
              for a in ("F5", "F6")}
    labels = {a: {"label": label(a, d["nll"]), "delta_nll": d["nll"]["mean"], "ci95": d["nll"]["ci95"]}
              for a, d in deltas.items()}
    summary = {fam: {c: [float(np.mean(materialize(dv, fam)[:, j])), float(np.std(materialize(dv, fam)[:, j]))]
                     for j, c in enumerate(COLUMNS[fam])} for fam in ("F5", "F6")}
    np.savez_compressed(output / "validation_predictions.npz", labels=yv, source_seeds=seeds_v, **predictions)
    report = {"schema": "vwin_derived_rooms_397_stage2d_v1", "issue": 397, "tooling": tool_identity(),
              "versions": versions(), "threads": threads,
              "corpus_index": str(Path(index).resolve()), "corpus_sha256": sha256(index),
              "a3_run": str(a3_run.resolve()),
              "a3_hashes": {n: sha256(a3_run / n) for n in ("validation.json", "preflight.json")},
              "remove_cost_check": remove_check, "validation_feature_mean_std": summary,
              "results": results, "paired_deltas": deltas, "labels": labels,
              "test_rows_read": False, "elapsed_seconds": time.time() - started}
    write_json(output / "report.json", report)
    print(json.dumps({"labels": labels, "remove_cost_check": remove_check}, indent=2))
    return report


def _self_test():
    p = question_odds([], False)
    assert p == {"pQMonster": .1, "pQShop": .03, "pQTreasure": .02, "pQEvent": 1 - .15}, p
    p = question_odds(["event", "event"], False)
    assert p["pQMonster"] == .3 and p["pQShop"] == .09 and p["pQTreasure"] == .06, p
    p = question_odds(["event", "monster"], True)
    assert p["pQMonster"] == .1 and p["pQShop"] == 0 and p["pQTreasure"] == .06, p
    assert question_odds(["event"], False, tiny_chest_counter=3)["pQTreasure"] == 1.0
    assert question_odds([], False, juzu=True)["pQMonster"] == 0.0
    many = question_odds(["event"] * 12, False)
    assert abs(sum(many.values()) - 1) < 1e-9 and many["pQEvent"] >= 0
    assert remove_cost(0, False, False, False) == 75 and remove_cost(2, False, False, False) == 125
    assert remove_cost(3, True, True, True) == 50
    assert remove_cost(1, False, True, False) == 80 and remove_cost(0, False, False, True) == 38
    assert remove_cost(0, False, True, True) == 30
    assert set(relic_columns()) == {"SMILING_MASK", "THE_COURIER", "MEMBERSHIP_CARD", "TINY_CHEST", "JUZU_BRACELET"}
    # Map reconstruction: ? at floor 2 (event), shop node at floor 3.
    names = ["pvEvent", "pvShop"]
    meta = [{"sourceSeed": 1, "branchId": "source", "floor": f, "act": 1} for f in (1, 2, 3)]
    X = np.array([[0, 0], [1, 0], [1, 1]], dtype=np.float32)
    traj = map_trajectories(meta, X, {n: i for i, n in enumerate(names)})[1, "source"]
    assert [(t[0], t[2], t[3]) for t in traj] == [(1, 0, 0), (2, 1, 0), (3, 1, 1)]
    print("vwin derived rooms #397 self-test: PASS")
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
