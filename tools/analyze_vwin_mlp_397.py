#!/usr/bin/env python3
"""#397 follow-up: do the public-history and rule-derived families help an MLP?

Stages 2-2d (ledger-06 §§374-376) tested every family with the A3 X1 XGBoost
recipe only. Trees are invariant to monotone rescaling and cut nonlinear
functions of a counter into thresholds, so a smooth network may gain where a
tree cannot. This run repeats the families with the frozen A3 M1 network.

Offline only on the frozen #334 corpus (TRAIN/VALIDATION; no gameplay seeds,
no C++ build, no TEST rows). Features are built by the already-reviewed
Stage 2/2b/2d code paths (`analyze_vwin_history_397`,
`analyze_vwin_derived_397`, `analyze_vwin_derived_rooms_397`).

Preregistered comparison (frozen before any arm was trained):
- Network and recipe: the frozen A3 M1 selection (`_network`: width -> 64 ->
  GELU -> dropout -> 32 -> GELU -> 1; AdamW lr 1e-4, weight decay 1e-3,
  dropout 0.1; TRAIN-only normalization; batch 8192; at most 60 epochs with
  patience 8 on VALIDATION loss; deterministic CUDA; 4 host threads).
- Sanity gate: the 461-feature A3 set at seed 0 must reproduce the frozen M1
  VALIDATION NLL within 1e-6; otherwise STOP.
- Baseline P: the 457-feature public-safe set. Arms add one family each:
  H1 relics seen not owned, H2 events seen, H3 encounters fought, F1 potion
  drop, F2 rarity block, F3 next elite, F4 next hallway + entropy, F5 ?-room
  odds, F6 next remove price; ALL adds F1-F6 together. N0 adds one standard-
  normal noise column (numpy seed 397) as a null control for how much any
  column change moves this procedure.
- Seeds 0, 1, 2 per arm; arm prediction = mean probability of the 3 seeds.
- Primary: ensemble VALIDATION NLL delta vs P with source-clustered paired 95%
  CI. `USEFUL` if delta <= -0.002, CI upper < 0, and the delta is more
  negative than N0's delta by at least 0.002; `LOW_VALUE` if CI lower >
  -0.002; otherwise INCONCLUSIVE.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SEEDS = (0, 1, 2)
RECIPE = {"lr": 1e-4, "weight_decay": 1e-3, "dropout": 0.1}
FIT = dict(max_epochs=60, patience=8, batch_size=8192)
MATERIAL_NLL = 0.002
REPRO_TOLERANCE = 1e-6
NOISE_SEED = 397
DERIVED = ("F1", "F2", "F3", "F4", "F5", "F6")
HISTORY = ("H1", "H2", "H3")


class MLPAuditError(ValueError):
    pass


def label(arm, delta, null_mean):
    mean, (lo, hi) = delta["mean"], delta["ci95"]
    if mean <= -MATERIAL_NLL and hi < 0 and mean <= null_mean - MATERIAL_NLL:
        return f"{arm}_USEFUL"
    return f"{arm}_LOW_VALUE" if lo > -MATERIAL_NLL else f"{arm}_INCONCLUSIVE"


def noise_column(n_rows, offset):
    rng = np.random.default_rng(NOISE_SEED + offset)
    return rng.standard_normal((n_rows, 1)).astype(np.float32)


def write_json(path, value):
    with Path(path).open("x") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def run(index, a3_run, output, threads, device):
    from tools.vwin_refresh_training import (_configure_cuda_determinism, _fit_mlp, _inputs,
                                             train_normalization, versions, runtime_fingerprint)
    _configure_cuda_determinism(device)
    import torch
    from tools.vwin_refresh_dataset import validated_dataset
    from tools.vwin_refresh_evaluation import evaluate_predictions, sibling_ranking, clustered_delta
    from tools.vwin_refresh_model import sha256, tool_identity
    from tools.analyze_vwin_public_info_397 import arms
    import tools.analyze_vwin_history_397 as hist
    import tools.analyze_vwin_derived_397 as der
    import tools.analyze_vwin_derived_rooms_397 as rooms
    torch.set_num_threads(threads)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    a3_run = Path(a3_run)
    frozen_m1 = json.loads((a3_run / "validation.json").read_text())["M1"]["training"]
    if frozen_m1["selected"]["recipe"] != RECIPE or frozen_m1["selected"]["seed"] != 0:
        raise MLPAuditError("frozen M1 recipe differs from the preregistered recipe")
    preflight = json.loads((a3_run / "preflight.json").read_text())
    data = validated_dataset(index)
    names = list(data.feature_names)
    selected = preflight["selected_feature_names"]
    base = arms(selected)["B"]
    splits = {"TRAIN", "VALIDATION"}
    histories, _, _ = hist.load_histories(data, splits)
    fights = der.load_fights(data, splits)
    room_hist, _ = rooms.load_trajectories(data, splits)
    xt, yt, mt = data.read("TRAIN")
    xv, yv, mv = data.read("VALIDATION")
    # Family blocks (TRAIN-variable columns only, as in the source stages).
    ht, _ = hist.build_family_columns(mt, xt, names, histories)
    hv, _ = hist.build_family_columns(mv, xv, names, histories)
    dt, _ = der.derive_split(xt, mt, names, fights)
    dv, _ = der.derive_split(xv, mv, names, fights)
    rt, rv = rooms.derive(mt, xt, names, room_hist), rooms.derive(mv, xv, names, room_hist)
    blocks = {}
    for fam in HISTORY:
        cols = hist.train_variable_columns(ht[fam])
        blocks[fam] = (cols, hist.materialize(ht[fam], cols), hist.materialize(hv[fam], cols))
    for fam in ("F1", "F2", "F3", "F4"):
        cols = der.F_COLUMNS[fam]
        blocks[fam] = (cols, der.materialize(dt, fam, cols), der.materialize(dv, fam, cols))
    for fam in ("F5", "F6"):
        blocks[fam] = (rooms.COLUMNS[fam], rooms.materialize(rt, fam), rooms.materialize(rv, fam))
    blocks["N0"] = (["noise"], noise_column(len(xt), 0), noise_column(len(xv), 1))
    arm_blocks = {"P": [], **{f: [f] for f in HISTORY + DERIVED}, "ALL": list(DERIVED), "N0": ["N0"]}
    branches = data.branches("VALIDATION")
    seeds_v = np.array([int(m["sourceSeed"]) for m in mv])

    def fit(Xt, Xv, features, seed):
        Xt, yt_, Xv, yv_, feats = _inputs(Xt, yt, Xv, yv, features)
        mean, std = train_normalization(Xt)
        return _fit_mlp(Xt, yt_, Xv, yv_, feats, mean, std, recipe=RECIPE, seed=seed,
                        device=device, **FIT)

    # Sanity gate: reproduce the frozen A3 M1 seed-0 checkpoint.
    cols = [names.index(f) for f in selected]
    model, trial = fit(xt[:, cols], xv[:, cols], selected, 0)
    drift = abs(trial["validation_nll"] - frozen_m1["selected"]["validation_nll"])
    gate = {"validation_nll": trial["validation_nll"], "frozen": frozen_m1["selected"]["validation_nll"],
            "drift": drift, "best_epoch": trial["best_epoch"], "frozen_best_epoch": frozen_m1["selected"]["best_epoch"]}
    print("A_repro", gate, flush=True)
    if drift > REPRO_TOLERANCE or trial["best_epoch"] != frozen_m1["selected"]["best_epoch"]:
        write_json(output / "stop.json", {"reason": "frozen M1 not reproduced", **gate})
        raise MLPAuditError("STOP: frozen M1 not reproduced")
    del model
    base_cols = [names.index(f) for f in base]
    results, predictions = {}, {}
    for arm, fams in arm_blocks.items():
        extra = [blocks[f] for f in fams]
        Xt = np.hstack([xt[:, base_cols]] + [b[1] for b in extra])
        Xv = np.hstack([xv[:, base_cols]] + [b[2] for b in extra])
        variable = Xt.var(axis=0) > 1e-12
        features = [n for n, v in zip(list(base) + [c for b in extra for c in b[0]], variable) if v]
        Xt, Xv = Xt[:, variable], Xv[:, variable]
        per_seed = []
        for seed in SEEDS:
            model, trial = fit(Xt, Xv, features, seed)
            predictions[f"{arm}_seed{seed}"] = model.predict(Xv)
            per_seed.append({k: trial[k] for k in ("seed", "best_epoch", "epochs_run", "validation_nll")})
            print(arm, seed, len(features), trial["best_epoch"], trial["validation_nll"], flush=True)
        ensemble = np.mean([predictions[f"{arm}_seed{s}"] for s in SEEDS], axis=0)
        predictions[f"{arm}_ensemble"] = ensemble
        results[arm] = {"feature_count": len(features), "families": fams, "per_seed": per_seed,
                        "validation": evaluate_predictions(yv, ensemble, mv),
                        "siblings": sibling_ranking(mv, ensemble, branches)}
        del Xt, Xv
    deltas = {arm: clustered_delta(yv, predictions["P_ensemble"], predictions[f"{arm}_ensemble"], seeds_v)
              for arm in arm_blocks if arm != "P"}
    null_mean = deltas["N0"]["nll"]["mean"]
    labels = {arm: {"label": label(arm, d["nll"], null_mean), "delta_nll": d["nll"]["mean"],
                    "ci95": d["nll"]["ci95"]} for arm, d in deltas.items() if arm != "N0"}
    labels["N0"] = {"label": "NULL_CONTROL", "delta_nll": null_mean, "ci95": deltas["N0"]["nll"]["ci95"]}
    np.savez_compressed(output / "validation_predictions.npz", labels=yv, source_seeds=seeds_v, **predictions)
    report = {"schema": "vwin_mlp_397_v1", "issue": 397, "tooling": tool_identity(),
              "runtime": runtime_fingerprint(device), "versions": versions(), "threads": threads,
              "recipe": RECIPE, "fit": FIT, "corpus_index": str(Path(index).resolve()),
              "corpus_sha256": sha256(index), "a3_run": str(a3_run.resolve()),
              "a3_hashes": {n: sha256(a3_run / n) for n in ("validation.json", "preflight.json")},
              "reproduction_gate": gate, "baseline_features": base, "results": results,
              "paired_deltas": deltas, "labels": labels, "test_rows_read": False,
              "elapsed_seconds": time.time() - started}
    write_json(output / "report.json", report)
    print(json.dumps({"labels": labels, "reproduction_gate": gate}, indent=2))
    return report


def _self_test():
    ci = lambda m, lo, hi: {"mean": m, "ci95": [lo, hi]}
    assert label("F2", ci(-.006, -.009, -.003), 0.0) == "F2_USEFUL"
    assert label("F2", ci(-.006, -.009, -.003), -.005) == "F2_INCONCLUSIVE"  # within null shift
    assert label("F2", ci(.001, -.001, .003), 0.0) == "F2_LOW_VALUE"
    assert label("F2", ci(-.001, -.004, .002), 0.0) == "F2_INCONCLUSIVE"
    a, b = noise_column(5, 0), noise_column(5, 0)
    assert a.shape == (5, 1) and np.array_equal(a, b) and not np.array_equal(a, noise_column(5, 1))
    print("vwin mlp #397 self-test: PASS")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--index")
    parser.add_argument("--a3-run")
    parser.add_argument("--output")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    if not (args.index and args.a3_run and args.output):
        parser.error("--index, --a3-run and --output are required")
    run(args.index, args.a3_run, args.output, args.threads, args.device)
    return 0


if __name__ == "__main__":
    sys.exit(main())
