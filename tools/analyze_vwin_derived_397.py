#!/usr/bin/env python3
"""#397 Stages 2b-2c: rule-derived public probabilities for run-win prediction.

Offline only on the frozen #334 corpus (TRAIN/VALIDATION; no gameplay seeds,
no C++ build, no TEST rows). Every feature is a function of the row's public
state plus public fight history and game rules; it never reads the simulator's
realized queues, so two runs with the same public history get the same value.

Rules were checked against STS1 V2.3.4 `desktop-1.0.jar` (SHA-256
`cfad868a...`, `javap -c -p -constants`):
- Potion drop (`AbstractRoom.addPotionToRewards`): chance 40 + blizzard
  potion mod (`potionChance`), 100 with White Beast Statue; a reward with four
  or more items gets 0 (context-dependent, not modelled here).
- Card rarity (`AbstractDungeon.rollRarity`, `AbstractRoom.getCardRarity`,
  `MonsterRoomElite`): roll = cardRng 0..99 + `cardRarityFactor`; rare if
  roll < rare chance (3 normal, 10 elite; N'loth's Gift multiplies by 3),
  uncommon if roll < rare + uncommon (37 normal, 40 elite). After each card a
  common lowers the factor by 1 (floor -40) and a rare resets it to 5. Cards
  per reward: 3, +1 Question Card, -2 Busted Crown. Prayer Wheel adds a second
  normal-room card reward (native `createMonsterCombatReward`; **Inference**
  that Java's reward screen matches, not separately disassembled).
- Encounter queues (`AbstractDungeon.populateMonsterList`,
  `populateFirstStrongEnemy`, `Exordium/TheCity/TheBeyond.generate*`): weak
  list (3 in act 1, else 2), then one first strong encounter drawn from the
  strong weights minus `generateExclusions()` of the last weak encounter, then
  strong encounters; every non-first-strong draw rejects the previous and the
  second-previous list entry. Elites reject the previous elite. Weights and
  exclusions are the Java constants below. Each MONSTER/ELITE room consumes the
  next queue entry, so the observed hallway/elite fights of the current act are
  exactly the queue prefix and the next entry's public distribution is the
  renormalized weights after those rules. The run cross-checks the observed
  prefix lengths against `monOffset`/`eliteOffset` on every row.
  Native `populateFirstStrongEnemy` applied the act-1 exclusions only until
  #407 added the act 2 and 3 exclusions; corpora generated before that fix
  follow the act-1-only rule at that one queue position.

Preregistered comparison (frozen before any arm was trained):
- P: the 457-feature public-safe baseline (#397 Stage 1).
- F1d: P minus `potionChance` plus `pPotionDrop`; F1b: P plus `pPotionDrop`.
- F2d: P minus `cardRarityFactor` plus the rarity block (per-card C/U/R for
  normal and elite rewards; per normal/elite reward P(>=1 rare), P(>=1
  uncommon or rare), expected rares, expected uncommons); F2b: P plus it.
- F3: P plus `pNextElite_<encounter>` (current-act elite distribution).
- F4: P plus `pNextFight_<encounter>` and `nextFightEntropy`.
- Frozen A3 X1 recipe, XGBoost seeds 0..4, 5-seed mean probability per arm;
  ensemble VALIDATION NLL delta vs P with the source-clustered paired 95% CI.
- F1/F2: `DERIVED_REPLACES_RAW` if the derived-only CI upper bound < +0.002;
  `DERIVED_ADDS_SIGNAL` if raw+derived delta <= -0.002 with CI upper < 0.
- F3/F4: `USEFUL` if delta <= -0.002 and CI upper < 0; `LOW_VALUE` if CI
  lower > -0.002; otherwise INCONCLUSIVE.
- STOP if more than 0.5% of rows disagree with `monOffset`/`eliteOffset`.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
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
MAX_OFFSET_MISMATCH = 0.005

# Corpus `combat.csv` names; weights/exclusions from the V2.3.4 dungeon classes.
WEAK = {
    1: {"Cultist": 2, "Jaw Worm": 2, "Two Louse": 2, "Small Slimes": 2},
    2: {"Spheric Guardian": 2, "Chosen": 2, "Shell Parasite": 2, "Three Byrds": 2, "Two Thieves": 2},
    3: {"Three Darklings": 2, "Orb Walker": 2, "Three Shapes": 2},
}
STRONG = {
    1: {"Blue Slaver": 2, "Gremlin Gang": 1, "Looter": 2, "Large Slime": 2, "Lots Of Slimes": 1,
        "Exordium Thugs": 1.5, "Exordium Wildlife": 1.5, "Red Slaver": 1, "Three Louse": 2,
        "Two Fungi Beasts": 2},
    2: {"Chosen And Byrds": 2, "Sentry And Sphere": 2, "Snake Plant": 6, "Snecko": 4,
        "Centurion And Healer": 6, "Cultist And Chosen": 3, "Three Cultist": 3,
        "Shelled Parasite And Fungi": 3},
    3: {"Spire Growth": 1, "Transient": 1, "Four Shapes": 1, "Maw": 1, "Sphere And Two Shapes": 1,
        "Jaw Worm Horde": 1, "Three Darklings": 1, "Writhing Mass": 1},
}
FIRST_STRONG_EXCLUSIONS = {
    1: {"Looter": {"Exordium Thugs"}, "Blue Slaver": {"Red Slaver", "Exordium Thugs"},
        "Two Louse": {"Three Louse"}, "Small Slimes": {"Large Slime", "Lots Of Slimes"}},
    2: {"Spheric Guardian": {"Sentry And Sphere"}, "Three Byrds": {"Chosen And Byrds"},
        "Chosen": {"Chosen And Byrds", "Cultist And Chosen"}},
    3: {"Three Darklings": {"Three Darklings"}, "Orb Walker": {"Orb Walker"},
        "Three Shapes": {"Four Shapes"}},
}
WEAK_COUNT = {1: 3, 2: 2, 3: 2}
ELITES = {1: ("Gremlin Nob", "Lagavulin", "Three Sentries"),
          2: ("Gremlin Leader", "Slavers", "Book Of Stabbing"),
          3: ("Giant Head", "Nemesis", "Reptomancer")}
ALL_HALLWAY = sorted({n for d in (WEAK, STRONG) for a in d.values() for n in a})
ALL_ELITES = sorted({n for a in ELITES.values() for n in a})
RARITY = {"normal": (3, 37), "elite": (10, 40)}


class DerivedError(ValueError):
    pass


def _normalize(weights):
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()} if total else {}


def next_hallway_distribution(act, observed):
    """Public distribution of the next hallway encounter given this act's prefix."""
    if act not in WEAK:
        return {}
    k = len(observed)
    if k >= WEAK_COUNT[act] + 1 + 12:
        return {}  # queue regenerated; not modelled
    if k < WEAK_COUNT[act]:
        weights = dict(WEAK[act])
        for prev in observed[-2:]:
            weights.pop(prev, None)
    elif k == WEAK_COUNT[act]:
        excluded = FIRST_STRONG_EXCLUSIONS[act].get(observed[-1], set())
        weights = {n: w for n, w in STRONG[act].items() if n not in excluded}
    else:
        weights = dict(STRONG[act])
        for prev in observed[-2:]:
            weights.pop(prev, None)
    return _normalize(weights)


def next_elite_distribution(act, observed):
    if act not in ELITES:
        return {}
    weights = {n: 1.0 for n in ELITES[act]}
    if observed:
        weights.pop(observed[-1], None)
    return _normalize(weights)


def card_rarity(factor, context, nloth):
    rare, unc = RARITY[context]
    if nloth:
        rare *= 3
    p_r = min(max(rare - factor, 0), 100) / 100
    p_ru = min(max(rare + unc - factor, 0), 100) / 100
    return p_r, p_ru - p_r, 1 - p_ru


def reward_summary(factor, context, nloth, cards, rewards=1):
    """Exact DP over the sequential pity updates for `rewards` card rewards."""
    dist = {int(factor): 1.0}
    e_r = e_u = 0.0
    no_r = {int(factor): 1.0}
    no_ur = {int(factor): 1.0}
    for _ in range(cards * rewards):
        nd, nnr, nnur = defaultdict(float), defaultdict(float), defaultdict(float)
        for f, p in dist.items():
            pr, pu, pc = card_rarity(f, context, nloth)
            e_r += p * pr
            e_u += p * pu
            nd[5] += p * pr; nd[f] += p * pu; nd[max(f - 1, -40)] += p * pc
        for f, p in no_r.items():
            pr, pu, pc = card_rarity(f, context, nloth)
            nnr[f] += p * pu; nnr[max(f - 1, -40)] += p * pc
        for f, p in no_ur.items():
            nnur[max(f - 1, -40)] += p * card_rarity(f, context, nloth)[2]
        dist, no_r, no_ur = nd, nnr, nnur
    return 1 - sum(no_r.values()), 1 - sum(no_ur.values()), e_r, e_u


def entropy(dist):
    return -sum(p * math.log(p) for p in dist.values() if p > 0)


def relic_index():
    from tools.analyze_vwin_public_info_397 import relic_names
    names = relic_names()
    return {n: f"r{names.index(n)}" for n in ("WHITE_BEAST_STATUE", "NLOTHS_GIFT", "QUESTION_CARD",
                                              "BUSTED_CROWN", "PRAYER_WHEEL")}


def row_derived(x, col, relics, hallway, elites, act):
    owned = lambda n: x[col[relics[n]]] > 0
    out = {"F1": {"pPotionDrop": 1.0 if owned("WHITE_BEAST_STATUE")
                  else min(max(40 + x[col["potionChance"]], 0), 100) / 100}}
    f = int(x[col["cardRarityFactor"]])
    nloth = owned("NLOTHS_GIFT")
    cards = 3 + owned("QUESTION_CARD") - 2 * owned("BUSTED_CROWN")
    f2 = {}
    for context, rewards in (("normal", 2 if owned("PRAYER_WHEEL") else 1), ("elite", 1)):
        pr, pu, pc = card_rarity(f, context, nloth)
        f2.update({f"pRare_{context}": pr, f"pUncommon_{context}": pu, f"pCommon_{context}": pc})
        anyr, anyu, er, eu = reward_summary(f, context, nloth, cards, rewards)
        f2.update({f"pAnyRare_{context}": anyr, f"pAnyUncommonPlus_{context}": anyu,
                   f"eRare_{context}": er, f"eUncommon_{context}": eu})
    out["F2"] = f2
    out["F3"] = {f"pNextElite_{n}": p for n, p in next_elite_distribution(act, elites).items()}
    dist = next_hallway_distribution(act, hallway)
    out["F4"] = {f"pNextFight_{n}": p for n, p in dist.items()}
    out["F4"]["nextFightEntropy"] = entropy(dist)
    return out


F_COLUMNS = {
    "F1": ["pPotionDrop"],
    "F2": [f"{s}_{c}" for c in ("normal", "elite") for s in
           ("pRare", "pUncommon", "pCommon", "pAnyRare", "pAnyUncommonPlus", "eRare", "eUncommon")],
    "F3": [f"pNextElite_{n}" for n in ALL_ELITES],
    "F4": [f"pNextFight_{n}" for n in ALL_HALLWAY] + ["nextFightEntropy"],
}
ARMS = {"P": ([], None), "F1d": (["F1"], "potionChance"), "F1b": (["F1"], None),
        "F2d": (["F2"], "cardRarityFactor"), "F2b": (["F2"], None),
        "F3": (["F3"], None), "F4": (["F4"], None)}


def load_fights(data, splits):
    """Per (seed, branchId): fights (fightIdx, floor, act, roomClass, encounter), prefix included."""
    from tools.vwin_refresh_dataset import source_split
    from tools.analyze_vwin_history_397 import Trajectory, history_items
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
                        (int(r["fightIdx"]), int(r["floor"]), int(r["act"]), r["roomClass"], r["encounter"]))
    source_floor = {}
    for table in data.corpus.tables("decisions.csv"):
        if not any(keep(s) for s in table.component.source_seeds):
            continue
        with table.path.open(newline="") as f:
            for r in csv.DictReader(f):
                seed = int(r["sourceSeed"])
                if keep(seed) and r["branchId"] == "source":
                    source_floor[seed, int(r["decisionIdx"])] = (r["type"], int(r["floor"]))
    branches = {}
    for table in data.corpus.tables("branches.csv"):
        if not any(keep(s) for s in table.component.source_seeds):
            continue
        with table.path.open(newline="") as f:
            for r in csv.DictReader(f):
                seed = int(r["sourceSeed"])
                if keep(seed):
                    kind, floor = source_floor[seed, int(r["decisionIdx"])]
                    branches[seed, r["branchId"]] = dict(kind="MAP" if kind == "MAP" else "OTHER",
                                                         floor=floor, row=-1)
    for traj in trajectories.values():
        traj.fights.sort()
    result = {}
    for key in set(trajectories) | set(branches):
        seed, branch = key
        if branch == "source":
            result[key] = trajectories[key].fights
        else:
            fights, _, _ = history_items(trajectories[seed, "source"], trajectories[key], branches[key])
            result[key] = fights
    return result


def derive_split(X, metadata, names, fights_by_traj):
    col = {n: i for i, n in enumerate(names)}
    relics = relic_index()
    rows, mismatches = [], {"hallway": 0, "elite": 0}
    for i, m in enumerate(metadata):
        act, floor = int(m["act"]), int(m["floor"])
        fights = fights_by_traj.get((int(m["sourceSeed"]), m["branchId"]), [])
        hallway = [f[4] for f in fights if f[2] == act and f[3] == "NORMAL" and f[1] <= floor]
        elites = [f[4] for f in fights if f[2] == act and f[3] == "ELITE" and f[1] <= floor]
        if act in WEAK:
            mismatches["hallway"] += len(hallway) != int(X[i, col["monOffset"]])
            mismatches["elite"] += len(elites) != int(X[i, col["eliteOffset"]])
        rows.append(row_derived(X[i], col, relics, hallway, elites, act))
    return rows, mismatches


def materialize(rows, family, columns):
    M = np.zeros((len(rows), len(columns)), dtype=np.float32)
    index = {c: j for j, c in enumerate(columns)}
    for i, r in enumerate(rows):
        for c, v in r[family].items():
            M[i, index[c]] = v
    return M


def label(arm, delta):
    mean, (lo, hi) = delta["mean"], delta["ci95"]
    if arm.endswith("d"):
        return "DERIVED_REPLACES_RAW" if hi < MATERIAL_NLL else "DERIVED_NOT_SHOWN_EQUIVALENT"
    if arm.endswith("b"):
        return "DERIVED_ADDS_SIGNAL" if mean <= -MATERIAL_NLL and hi < 0 else "DERIVED_ADDS_NO_CLEAR_SIGNAL"
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
    fights = load_fights(data, {"TRAIN", "VALIDATION"})
    xt, yt, mt = data.read("TRAIN")
    xv, yv, mv = data.read("VALIDATION")
    dt, mis_t = derive_split(xt, mt, names, fights)
    dv, mis_v = derive_split(xv, mv, names, fights)
    checks = {"TRAIN": mis_t, "VALIDATION": mis_v}
    worst = max(mis_t["hallway"], mis_t["elite"]) / len(mt), max(mis_v["hallway"], mis_v["elite"]) / len(mv)
    if max(worst) > MAX_OFFSET_MISMATCH:
        write_json(output / "stop.json", {"reason": "offset cross-check", "checks": checks})
        raise DerivedError("STOP: observed fight prefix disagrees with queue offsets")
    branches = data.branches("VALIDATION")
    seeds_v = np.array([int(m["sourceSeed"]) for m in mv])
    params = dict(frozen["params"], nthread=threads)
    results, predictions = {}, {}
    for arm, (families, dropped) in ARMS.items():
        feats = [f for f in base if f != dropped]
        cols = [names.index(f) for f in feats]
        extra_t = [materialize(dt, fam, F_COLUMNS[fam]) for fam in families]
        extra_v = [materialize(dv, fam, F_COLUMNS[fam]) for fam in families]
        extra_names = [c for fam in families for c in F_COLUMNS[fam]]
        Xt = np.hstack([xt[:, cols], *extra_t]); Xv = np.hstack([xv[:, cols], *extra_v])
        variable = Xt.var(axis=0) > 1e-12
        features = [n for n, v in zip(feats + extra_names, variable) if v]
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
        results[arm] = {"feature_count": len(features), "dropped_raw": dropped,
                        "added": [n for n in extra_names if n in features], "per_seed": per_seed,
                        "validation": evaluate_predictions(yv, ensemble, mv),
                        "siblings": sibling_ranking(mv, ensemble, branches)}
        del Xt, Xv
    deltas, labels = {}, {}
    for arm in ARMS:
        if arm == "P":
            continue
        deltas[arm] = clustered_delta(yv, predictions["P_ensemble"], predictions[f"{arm}_ensemble"], seeds_v)
        labels[arm] = {"label": label(arm, deltas[arm]["nll"]), "delta_nll": deltas[arm]["nll"]["mean"],
                       "ci95": deltas[arm]["nll"]["ci95"]}
    np.savez_compressed(output / "validation_predictions.npz", labels=yv, source_seeds=seeds_v, **predictions)
    report = {"schema": "vwin_derived_397_stage2bc_v1", "issue": 397, "tooling": tool_identity(),
              "versions": versions(), "threads": threads,
              "corpus_index": str(Path(index).resolve()), "corpus_sha256": sha256(index),
              "a3_run": str(a3_run.resolve()),
              "a3_hashes": {n: sha256(a3_run / n) for n in ("validation.json", "preflight.json")},
              "baseline_features": base, "offset_cross_check": checks, "results": results,
              "paired_deltas": deltas, "labels": labels, "test_rows_read": False,
              "elapsed_seconds": time.time() - started}
    write_json(output / "report.json", report)
    print(json.dumps({"labels": labels, "offset_cross_check": checks}, indent=2))
    return report


def _self_test():
    # Act 1 weak phase: first draw uses the full weak weights.
    assert next_hallway_distribution(1, []) == {n: .25 for n in WEAK[1]}
    d = next_hallway_distribution(1, ["Cultist", "Jaw Worm"])
    assert d == {"Two Louse": .5, "Small Slimes": .5}, d
    # First strong after Small Slimes excludes both slime encounters.
    d = next_hallway_distribution(1, ["Cultist", "Jaw Worm", "Small Slimes"])
    assert "Large Slime" not in d and "Lots Of Slimes" not in d and abs(sum(d.values()) - 1) < 1e-12
    assert abs(d["Blue Slaver"] - 2 / 13) < 1e-12
    # Strong phase rejects the previous two list entries, including a weak one.
    d = next_hallway_distribution(3, ["Three Darklings", "Orb Walker", "Maw"])
    assert "Maw" not in d and "Orb Walker" not in d and abs(d["Three Darklings"] - 1 / 7) < 1e-12
    d = next_hallway_distribution(3, ["Orb Walker", "Three Darklings"])
    assert "Three Darklings" not in d and len(d) == 7
    assert next_elite_distribution(2, []) == {n: 1 / 3 for n in ELITES[2]}
    assert next_elite_distribution(1, ["Lagavulin"]) == {"Gremlin Nob": .5, "Three Sentries": .5}
    assert next_elite_distribution(4, []) == {} and next_hallway_distribution(4, []) == {}
    assert card_rarity(5, "normal", False) == (0.0, .35, .65)
    pr, pu, pc = card_rarity(-40, "elite", False)
    assert abs(pr - .5) < 1e-12 and abs(pu - .4) < 1e-12 and abs(pc - .1) < 1e-12
    assert abs(card_rarity(0, "normal", True)[0] - .09) < 1e-12
    # One card: reward summary equals the per-card probabilities.
    anyr, anyu, er, eu = reward_summary(0, "normal", False, 1)
    assert abs(anyr - .03) < 1e-12 and abs(anyu - .40) < 1e-12 and abs(er - .03) < 1e-12
    # Two cards from factor 5: first card cannot be rare; a common lowers to 4.
    anyr, _, er, _ = reward_summary(5, "normal", False, 2)
    assert anyr == 0.0 and er == 0.0  # factor 5 then 5/4: rare needs roll < 3 - f
    # Factor 2: P(R)=.01, P(U)=.37, P(C)=.62; second card rare .01 after U, .02 after C.
    anyr, _, _, _ = reward_summary(2, "normal", False, 2)
    assert abs(anyr - (1 - (.37 * .99 + .62 * .98))) < 1e-12, anyr
    assert abs(entropy({"a": .5, "b": .5}) - math.log(2)) < 1e-12
    assert len(ALL_HALLWAY) == len(set(ALL_HALLWAY)) and "Three Darklings" in ALL_HALLWAY
    print("vwin derived #397 self-test: PASS")
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
