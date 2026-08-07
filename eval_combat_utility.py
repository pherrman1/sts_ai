#!/usr/bin/env python3
"""Offline evaluation of a combat_utility_v1 native artifact on fairgen CSVs.

The model predicts a 51-bin categorical over the MCTS terminal utility
R = 0 on loss, 50 + endHp on win (bin 0 = loss; bins 1..50 = endHp/maxHp
fractions on wins). From the one head we derive:

  win prob         = 1 - p(bin 0)           -> win Brier/logloss/ECE,
                                            death BCE (mass around zero)
  HP|win quantiles = cumulative bins 1..50  -> quantile coverage on wins
  expected value   = sum_b p_b * (50 + maxHp * mid_b) -> EV MAE and
                                            reliability deciles vs realized R

Usage: python3 eval_combat_utility.py <model.txt> <fair_v.csv>
       [--max-rows N] [--val-only] [--json out.json]
"""
import json
import os
import sys

import numpy as np
import pandas as pd

from combat_pvnet_parity import (column_groups, extract_state, load_native_model)

MODEL = sys.argv[1] if len(sys.argv) > 1 else "build/v_combat_utility.txt"
VAL_CSV = sys.argv[2] if len(sys.argv) > 2 else "build/fair34_v.csv"
MAX_ROWS = None
VAL_ONLY = False
JSON_OUT = None
i = 3
while i < len(sys.argv):
    if sys.argv[i] == "--max-rows":
        MAX_ROWS = int(sys.argv[i + 1]); i += 2
    elif sys.argv[i] == "--val-only":
        VAL_ONLY = True; i += 1
    elif sys.argv[i] == "--json":
        JSON_OUT = sys.argv[i + 1]; i += 2
    else:
        raise SystemExit(f"unknown arg {sys.argv[i]}")

import torch
torch.set_num_threads(4)

val_header = list(pd.read_csv(VAL_CSV, nrows=0).columns)
extra_excl = ["endTurn", "potionsConsumed"] + [c for c in val_header if c.startswith("pUsed")]
canonical = [c for c in val_header if c not in ("seed", "fightIdx", "won", "endHp", *extra_excl)]
groups = column_groups(canonical)

model, D, H, HDS, L, NB, scalar_sel = load_native_model(MODEL)
assert hasattr(model, "util"), f"{MODEL} is not a combat_utility_v1 model"
WIN_BONUS = 50.0
print(f"[model] utility d={D} h={H} heads={HDS} layers={L} bins={NB}")

BATCH = 1024
VCOLS = canonical + ["seed", "won", "endHp", "maxHp"]


def seed_filter(df):
    if not VAL_ONLY:
        return df
    m = df["seed"].map(lambda s: int(s) % 100
                       < int(float(os.environ.get("UTIL_VAL_FRAC", "0.2")) * 100)
                       ).to_numpy(np.bool_)
    return df[m]


def to_plain(x):
    if isinstance(x, dict):
        return {k: to_plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [to_plain(v) for v in x]
    if isinstance(x, np.ndarray):
        return to_plain(x.tolist())
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    return x


def main():
    n_rows = 0
    acc = {
        "brier": 0.0, "logloss": 0.0, "death_bce": 0.0, "n": 0.0,
        "ece_n": 0.0, "ece_acc": 0.0, "ece_conf": 0.0,
        "qcov": np.zeros(NB - 1), "qcov_n": 0.0,
        "ce": 0.0, "ev_mae": 0.0, "ev_n": 0.0,
        "ev_bin_n": np.zeros(10), "ev_bin_pred": np.zeros(10),
        "ev_bin_actual": np.zeros(10),
    }
    mids = np.zeros(NB)
    mids[1:] = (np.arange(1, NB) - 0.5) / (NB - 1)
    for df in pd.read_csv(VAL_CSV, usecols=VCOLS, chunksize=20000):
        df = seed_filter(df)
        if len(df) == 0:
            continue
        if MAX_ROWS and n_rows + len(df) > MAX_ROWS:
            df = df.iloc[:MAX_ROWS - n_rows]
        st = extract_state(df, *groups)
        z = model.encoder(*[torch.from_numpy(a) for a in st])
        with torch.no_grad():
            probs = torch.softmax(model.util(z), dim=-1).numpy()
        won = df["won"].to_numpy(np.float32)
        hp = df["endHp"].to_numpy(np.float32)
        mh = df["maxHp"].to_numpy(np.float32)
        win = 1.0 - probs[:, 0]
        acc["n"] += len(df)
        acc["brier"] += ((win - won) ** 2).sum()
        eps = 1e-7
        acc["logloss"] += -(won * np.log(win + eps) + (1 - won) * np.log(1 - win + eps)).sum()
        acc["death_bce"] += -((1 - won) * np.log(probs[:, 0] + eps)
                              + won * np.log(1 - probs[:, 0] + eps)).sum()
        bins = np.linspace(0, 1, 11)
        b = np.clip(np.digitize(win, bins) - 1, 0, 9)
        for bi in range(10):
            m = b == bi
            if not m.any():
                continue
            acc["ece_n"] += m.sum()
            acc["ece_acc"] += won[m].mean() * m.sum()
            acc["ece_conf"] += win[m].mean() * m.sum()
        wonm = won > 0.5
        if wonm.any():
            frac = hp[wonm] / (mh[wonm] + 1e-6)
            cdf = np.cumsum(probs[wonm, 1:], axis=1)
            for k in range(NB - 1):
                acc["qcov"][k] += (frac <= cdf[:, k]).sum()
            acc["qcov_n"] += wonm.sum()
        # categorical CE + EV calibration
        true_bin = np.zeros(len(df), np.int64)
        f = np.clip(hp / (mh + 1e-6), 0.0, 1.0)
        true_bin[won > 0.5] = np.clip(np.ceil(f[won > 0.5] * (NB - 1)), 1, NB - 1).astype(np.int64)
        acc["ce"] += -np.log(probs[np.arange(len(df)), true_bin] + eps).sum()
        ev = (probs * (WIN_BONUS + mh[:, None] * mids[None, :])).sum(-1)
        r = np.where(won > 0.5, WIN_BONUS + hp, 0.0)
        acc["ev_mae"] += np.abs(ev - r).sum()
        acc["ev_n"] += len(df)
        q = np.clip(np.digitize(ev, np.percentile(ev, np.arange(0, 101, 10))), 0, 9)
        for bi in range(10):
            m = q == bi
            if not m.any():
                continue
            acc["ev_bin_n"][bi] += m.sum()
            acc["ev_bin_pred"][bi] += ev[m].mean() * m.sum()
            acc["ev_bin_actual"][bi] += r[m].mean() * m.sum()
        n_rows += len(df)
        if MAX_ROWS and n_rows >= MAX_ROWS:
            break
    res = {
        "win_brier": acc["brier"] / max(acc["n"], 1),
        "win_logloss": acc["logloss"] / max(acc["n"], 1),
        "win_ece": abs(acc["ece_acc"] - acc["ece_conf"]) / max(acc["ece_n"], 1),
        "death_bce": acc["death_bce"] / max(acc["n"], 1),
        "bin_ce": acc["ce"] / max(acc["n"], 1),
        "ev_mae": acc["ev_mae"] / max(acc["ev_n"], 1),
        "ev_reliability": (np.abs(acc["ev_bin_pred"] - acc["ev_bin_actual"])
                           / np.maximum(acc["ev_bin_n"], 1)).tolist(),
        "n_states": int(acc["n"]),
    }
    if acc["qcov_n"] > 0:
        res["win_hp_quantile_coverage"] = (acc["qcov"] / acc["qcov_n"]).tolist()
        res["win_hp_quantile_targets"] = (np.arange(1, NB) / (NB - 1)).tolist()
    return res


if __name__ == "__main__":
    out = to_plain({"model": MODEL, "val_only": VAL_ONLY, "value": main()})
    print(json.dumps(out, indent=2))
    if JSON_OUT:
        with open(JSON_OUT, "w") as f:
            json.dump(out, f, indent=2)
        print(f"[eval] wrote {JSON_OUT}")
