#!/usr/bin/env python3
"""#397 Stage 1: rich `v_win` information-boundary audit and hidden-future ablation.

Classifies every rich-state feature (`richStateHeader`) by what a real player
can know, then retrains the frozen #334 A3 X1 XGBoost recipe on the frozen
TRAIN/VALIDATION corpus with and without the hidden-future fields. Offline
only: no gameplay seeds, no C++ build, no TEST access (the dataset adapter
blocks TEST reads).

Classes (source: `apps/one_combat/run_features.cpp::richFeatureVec`):
- PUBLIC_CURRENT: visible current state (resources, deck, relics, potions,
  keys, act boss, map position and forward-map summaries).
- PUBLIC_HISTORY: determined by the player's own observed history (path room
  counts, potion/rarity pity counters, number of hallway/elite combats
  already entered this act).
- REDUNDANT: deterministic function of other public features.
- HIDDEN_FUTURE: identity read from the simulator's realized future queue.

Code facts behind the encounter fields (`src/game/GameContext.cpp`):
`generateMonsters` builds a fixed-length act queue (act 1: 3 weak + 1 + 12
strong = 16; acts 2-3: 2 + 1 + 12 = 15; elites 10); act 4 clears the
hallway queue and enqueues one elite. Each MONSTER/ELITE room entry consumes
one entry (`getMonsterForRoomCreation`/`getEliteForRoomCreation`) and act
transition resets the offsets. So `monOffset`/`eliteOffset` count combats
already entered this act (public), `remFights`/`remElites` are the fixed act
length minus that count (redundant), while `nextFight0..2`/`nextEliteId` are
the realized hidden queue entries. The run checks the length identities on
every TRAIN/VALIDATION MAP row before training; any violation is a STOP.

Preregistered comparison (frozen before any arm was trained):
- A: the 461 TRAIN-variable A3 features (current contract).
- B: A minus the verified HIDDEN_FUTURE fields (public-safe baseline).
- C: A minus all eight V4-excluded fields (diagnostic: also drops the
  public offset/remaining counts).
- Recipe: the frozen A3 X1 selection (depth 6, eta 0.06, min_child_weight
  30, early stopping on VALIDATION, 4 threads), XGBoost seeds 0, 1, 2.
- Sanity gate: A at seed 0 must reproduce the frozen X1 VALIDATION NLL
  within 1e-9; otherwise STOP (implementation/provenance failure).
- Primary statistic: VALIDATION NLL delta B - A per seed, with the source-
  clustered paired 95% CI (2,000 replicates, seed 0) from
  `clustered_delta`.
- HIDDEN_FUTURE_LEAK_MATERIAL if the mean delta over seeds is >= 0.002 (the
  A3 data-scale materiality threshold) and every seed's CI lower bound is
  > 0; HIDDEN_FUTURE_LEAK_NOT_MATERIAL if the mean delta is < 0.002 and
  every seed's CI upper bound is < 0.002; otherwise INCONCLUSIVE.
- Brier/AUC/ECE, act/pre-boss slices and sibling ranking are secondary.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PUBLIC_CURRENT, PUBLIC_HISTORY = "PUBLIC_CURRENT", "PUBLIC_HISTORY"
REDUNDANT, HIDDEN_FUTURE = "REDUNDANT", "HIDDEN_FUTURE"
CLASSES = (PUBLIC_CURRENT, PUBLIC_HISTORY, REDUNDANT, HIDDEN_FUTURE)

SCALAR_CLASSES = {
    "ascension": (PUBLIC_CURRENT, "run setting"),
    "act": (PUBLIC_CURRENT, "visible"), "floor": (PUBLIC_CURRENT, "visible"),
    "curHp": (PUBLIC_CURRENT, "visible"), "maxHp": (PUBLIC_CURRENT, "visible"),
    "gold": (PUBLIC_CURRENT, "visible"),
    "deckSize": (REDUNDANT, "sum of owned card counts d*"),
    "potionChance": (PUBLIC_HISTORY, "potion-drop pity counter; fixed by observed reward history"),
    "cardRarityFactor": (PUBLIC_HISTORY, "card-rarity pity counter; fixed by observed reward history"),
    "blueKey": (PUBLIC_CURRENT, "visible"), "greenKey": (PUBLIC_CURRENT, "visible"),
    "redKey": (PUBLIC_CURRENT, "visible"),
    "potionCount": (REDUNDANT, "sum of held potions pot*"),
    "potionCapacity": (PUBLIC_CURRENT, "visible slots"),
    "bossId": (PUBLIC_CURRENT, "act boss is shown on the map"),
    "nextEliteId": (HIDDEN_FUTURE, "eliteMonsterList[offset]: realized next elite"),
    "nextFight0": (HIDDEN_FUTURE, "monsterList[offset]: realized next hallway fight"),
    "nextFight1": (HIDDEN_FUTURE, "monsterList[offset+1]: realized hallway fight"),
    "nextFight2": (HIDDEN_FUTURE, "monsterList[offset+2]: realized hallway fight"),
    "remElites": (REDUNDANT, "fixed act elite-queue length minus eliteOffset"),
    "remFights": (REDUNDANT, "fixed act hallway-queue length minus monOffset"),
    "monOffset": (PUBLIC_HISTORY, "hallway combats entered this act"),
    "eliteOffset": (PUBLIC_HISTORY, "elite combats entered this act"),
    **{f"pv{r}": (PUBLIC_HISTORY, "visited map-node count by room type")
       for r in ("Shop", "Rest", "Event", "Elite", "Monster", "Treasure")},
    **{f"bottled{t}Id": (PUBLIC_CURRENT, "chosen bottled card") for t in ("Atk", "Skill", "Pow")},
    **{f"fm{k}": (PUBLIC_CURRENT, "forward summary of the visible act map")
       for k in ("DElite", "DRest", "DShop", "DBoss", "CElite", "CRest", "CShop",
                 "CEvent", "CMonster", "CTreasure")},
    "curMapX": (PUBLIC_CURRENT, "visible"), "curMapY": (PUBLIC_CURRENT, "visible"),
}
BLOCK_CLASSES = {
    "d": (PUBLIC_CURRENT, "owned card count"),
    "u": (PUBLIC_CURRENT, "upgraded card count"),
    "r": (PUBLIC_CURRENT, "owned relic: 1 + relic counter (see relic counter audit)"),
    "pot": (PUBLIC_CURRENT, "held potion count"),
}
V4_EXCLUDED = ("nextEliteId", "nextFight0", "nextFight1", "nextFight2",
               "remElites", "remFights", "monOffset", "eliteOffset")
# Fixed act queue lengths from GameContext::generateMonsters / transitionToAct.
HALLWAY_QUEUE_LENGTH = {1: 16, 2: 15, 3: 15, 4: 0}
ELITE_QUEUE_LENGTH = {1: 10, 2: 10, 3: 10, 4: 1}
MATERIAL_NLL = 0.002
SEEDS = (0, 1, 2)
REPRO_TOLERANCE = 1e-9


class AuditError(ValueError):
    pass


def classify(name):
    if name in SCALAR_CLASSES:
        return SCALAR_CLASSES[name]
    m = re.fullmatch(r"(d|u|r|pot)(\d+)", name)
    if m:
        return BLOCK_CLASSES[m.group(1)]
    raise AuditError(f"unclassified rich feature: {name}")


def inventory(feature_names, selected):
    selected = set(selected)
    rows = [dict(name=n, cls=classify(n)[0], reason=classify(n)[1], train_variable=n in selected)
            for n in feature_names]
    counts = {c: {"all": sum(r["cls"] == c for r in rows),
                  "train_variable": sum(r["cls"] == c and r["train_variable"] for r in rows)}
              for c in CLASSES}
    return rows, counts


def arms(selected):
    hidden = [n for n in selected if classify(n)[0] == HIDDEN_FUTURE]
    return {"A": list(selected),
            "B": [n for n in selected if n not in hidden],
            "C": [n for n in selected if n not in V4_EXCLUDED]}


def queue_identity_violations(X, names):
    """Rows where offset + remaining differs from the fixed act queue length."""
    col = {n: names.index(n) for n in ("act", "monOffset", "remFights", "eliteOffset", "remElites")}
    act = X[:, col["act"]].astype(int)
    if not set(np.unique(act)) <= set(HALLWAY_QUEUE_LENGTH):
        raise AuditError("unknown act in rich rows")
    hall = np.vectorize(HALLWAY_QUEUE_LENGTH.get)(act)
    elite = np.vectorize(ELITE_QUEUE_LENGTH.get)(act)
    return {"hallway": int(np.sum(X[:, col["monOffset"]] + X[:, col["remFights"]] != hall)),
            "elite": int(np.sum(X[:, col["eliteOffset"]] + X[:, col["remElites"]] != elite)),
            "rows": int(len(X))}


def relic_names():
    text = (ROOT / "include/constants/Relics.h").read_text()
    body = text[text.index("enum class RelicId"):]
    body = body[body.index("{") + 1:body.index("}")]
    body = re.sub(r"//[^\n]*", "", body)
    names = []
    for token in body.split(","):
        token = token.strip()
        if token:
            name, _, value = token.partition("=")
            if value.strip() and int(value) != len(names):
                raise AuditError("non-sequential RelicId enum")
            names.append(name.strip())
    return names


def relic_counter_audit(X, names):
    """Relic columns that carry counter values beyond ownership (value > 1)."""
    labels = relic_names()
    result = []
    for i, n in enumerate(names):
        if re.fullmatch(r"r\d+", n):
            column = X[:, i]
            if column.max() > 1:
                rid = int(n[1:])
                result.append(dict(feature=n, relic=labels[rid] if rid < len(labels) else None,
                                   max=float(column.max()), rows_gt1=int(np.sum(column > 1))))
    return result


def verdict(deltas):
    """deltas: per-seed clustered_delta()['nll'] summaries for B - A."""
    means = [d["mean"] for d in deltas]
    mean = float(np.mean(means))
    if mean >= MATERIAL_NLL and all(d["ci95"][0] > 0 for d in deltas):
        label = "HIDDEN_FUTURE_LEAK_MATERIAL"
    elif mean < MATERIAL_NLL and all(d["ci95"][1] < MATERIAL_NLL for d in deltas):
        label = "HIDDEN_FUTURE_LEAK_NOT_MATERIAL"
    else:
        label = "INCONCLUSIVE"
    return {"label": label, "mean_delta_nll": mean, "per_seed_delta_nll": means,
            "materiality": MATERIAL_NLL}


def write_json(path, value):
    with Path(path).open("x") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def run(index, a3_run, output, threads):
    from tools.vwin_refresh_dataset import validated_dataset
    from tools.vwin_refresh_evaluation import evaluate_predictions, sibling_ranking, clustered_delta
    from tools.vwin_refresh_model import sha256, tool_identity
    from tools.vwin_refresh_training import train_xgb_fixed, versions
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    a3_run = Path(a3_run)
    frozen = json.loads((a3_run / "validation.json").read_text())["X1"]["training"]["selected"]
    preflight = json.loads((a3_run / "preflight.json").read_text())
    data = validated_dataset(index)
    names = list(data.feature_names)
    selected = preflight["selected_feature_names"]
    rows, counts = inventory(names, selected)
    arm_features = arms(selected)
    xt, yt, _ = data.read("TRAIN")
    xv, yv, mv = data.read("VALIDATION")
    checks = {"TRAIN": queue_identity_violations(xt, names),
              "VALIDATION": queue_identity_violations(xv, names)}
    if any(c["hallway"] or c["elite"] for c in checks.values()):
        write_json(output / "stop.json", {"reason": "queue length identity violated", "checks": checks})
        raise AuditError("STOP: queue identity violated")
    relics = relic_counter_audit(xt, names)
    branches = data.branches("VALIDATION")
    seeds = np.array([int(m["sourceSeed"]) for m in mv])
    params = dict(frozen["params"], nthread=threads)
    results, predictions = {}, {}
    for arm, features in arm_features.items():
        columns = [names.index(f) for f in features]
        for seed in SEEDS:
            model, report = train_xgb_fixed(xt[:, columns], yt, xv[:, columns], yv, features,
                                            params=dict(params, seed=seed))
            p = model.predict(xv[:, columns])
            predictions[f"{arm}_seed{seed}"] = p
            results[f"{arm}_seed{seed}"] = {
                "feature_count": len(features), "tree_count": report["tree_count"],
                "validation": evaluate_predictions(yv, p, mv),
                "siblings": sibling_ranking(mv, p, branches)}
            print(arm, seed, len(features), report["tree_count"],
                  results[f"{arm}_seed{seed}"]["validation"]["overall"]["nll"], flush=True)
            if arm == "A" and seed == 0:
                drift = abs(report["validation_nll"] - frozen["validation_nll"])
                if drift > REPRO_TOLERANCE or report["tree_count"] != frozen["tree_count"]:
                    write_json(output / "stop.json", {"reason": "A seed 0 does not reproduce frozen X1",
                                                      "drift": drift, "trees": report["tree_count"]})
                    raise AuditError("STOP: frozen X1 not reproduced")
    np.savez_compressed(output / "validation_predictions.npz", labels=yv, source_seeds=seeds,
                        **predictions)
    deltas = {f"{arm}_minus_A": {str(s): clustered_delta(yv, predictions[f"A_seed{s}"],
                                                         predictions[f"{arm}_seed{s}"], seeds)
                                 for s in SEEDS} for arm in ("B", "C")}
    report = {
        "schema": "vwin_public_info_397_stage1_v1", "issue": 397,
        "tooling": tool_identity(), "versions": versions(), "threads": threads,
        "corpus_index": str(Path(index).resolve()), "corpus_sha256": sha256(index),
        "a3_run": str(a3_run.resolve()),
        "a3_hashes": {n: sha256(a3_run / n) for n in ("validation.json", "preflight.json")},
        "frozen_x1": {"params": frozen["params"], "tree_count": frozen["tree_count"],
                      "validation_nll": frozen["validation_nll"]},
        "class_counts": counts, "inventory": rows, "arms": arm_features,
        "queue_identity_checks": checks, "relic_counter_audit": relics,
        "results": results, "paired_deltas": deltas,
        "verdict": verdict([deltas["B_minus_A"][str(s)]["nll"] for s in SEEDS]),
        "diagnostic_C": verdict([deltas["C_minus_A"][str(s)]["nll"] for s in SEEDS]),
        "test_rows_read": False, "elapsed_seconds": time.time() - started}
    write_json(output / "report.json", report)
    print(json.dumps({"verdict": report["verdict"], "diagnostic_C": report["diagnostic_C"],
                      "class_counts": counts, "queue_identity_checks": checks}, indent=2))
    return report


def _self_test():
    header = (["ascension", "act", "floor", "curHp"] + [k for k in SCALAR_CLASSES if k not in
              ("ascension", "act", "floor", "curHp")] + ["d0", "u371", "r5", "pot47"])
    rows, counts = inventory(header, header)
    assert sum(c["all"] for c in counts.values()) == len(header)
    a = arms(header)
    hidden = set(header) - set(a["B"])
    assert hidden == {"nextEliteId", "nextFight0", "nextFight1", "nextFight2"}, hidden
    assert set(header) - set(a["C"]) == set(V4_EXCLUDED)
    assert hidden < set(V4_EXCLUDED)
    try:
        classify("seed")
        raise AssertionError("unknown feature must fail closed")
    except AuditError:
        pass
    names = ["act", "monOffset", "remFights", "eliteOffset", "remElites"]
    good = np.array([[1, 3, 13, 1, 9], [2, 0, 15, 0, 10], [4, 0, 0, 0, 1]], dtype=np.float32)
    assert queue_identity_violations(good, names) == {"hallway": 0, "elite": 0, "rows": 3}
    bad = good.copy(); bad[0, 2] = 12; bad[2, 4] = 0
    assert queue_identity_violations(bad, names) == {"hallway": 1, "elite": 1, "rows": 3}
    assert relic_names()[0] == "AKABEKO"
    ok = lambda m, lo, hi: {"mean": m, "ci95": [lo, hi]}
    assert verdict([ok(.004, .001, .007)] * 3)["label"] == "HIDDEN_FUTURE_LEAK_MATERIAL"
    assert verdict([ok(.0005, -.0005, .0015)] * 3)["label"] == "HIDDEN_FUTURE_LEAK_NOT_MATERIAL"
    assert verdict([ok(.001, -.001, .003)] * 3)["label"] == "INCONCLUSIVE"
    assert verdict([ok(.004, -.001, .009)] * 3)["label"] == "INCONCLUSIVE"
    print("vwin public-info #397 audit self-test: PASS")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--index", help="frozen #334 corpus index JSON")
    parser.add_argument("--a3-run", help="frozen A3 selected/ run directory")
    parser.add_argument("--output", help="new evidence directory (refuses overwrite)")
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
