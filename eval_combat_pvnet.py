#!/usr/bin/env python3
"""Offline evaluation of a CombatPVNet native artifact on fairgen CSVs.

Policy metrics (per decision group, teacher = visit distribution):
  cross-entropy, KL(teacher||model), top-1 agreement, top-3 recall,
  expected teacher regret (1 - p* of the model's argmax action),
  mean group size and mean teacher entropy.

Value metrics (per state, teacher = won/endHp/maxHp):
  win Brier score, win log loss, ECE (10 reliability bins),
  death BCE, quantile coverage per tau (wins only, endHp/maxHp).

By default all rows of the CSVs are evaluated; --val-only restricts to the
trainer's deterministic validation seeds (seed % 100 < 100*PVNET_VAL_FRAC).

Usage: python3 eval_combat_pvnet.py <model.txt> <fair_v.csv> <fair_p.csv>
       [--max-rows N] [--val-only] [--json out.json]
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import torch

from combat_pvnet_parity import (column_groups, encode_states, evaluate_heads,
                                 load_native_model)

MODEL = sys.argv[1] if len(sys.argv) > 1 else "models/v_combat_pvnet.txt"
VAL_CSV = sys.argv[2] if len(sys.argv) > 2 else "build/fair_v.csv"
POL_CSV = sys.argv[3] if len(sys.argv) > 3 else "build/fair_p.csv"
MAX_ROWS = None
VAL_ONLY = False
JSON_OUT = None
i = 4
while i < len(sys.argv):
    if sys.argv[i] == "--max-rows":
        MAX_ROWS = int(sys.argv[i + 1]); i += 2
    elif sys.argv[i] == "--val-only":
        VAL_ONLY = True; i += 1
    elif sys.argv[i] == "--json":
        JSON_OUT = sys.argv[i + 1]; i += 2
    else:
        raise SystemExit(f"unknown arg {sys.argv[i]}")
torch.set_num_threads(4)

val_header = list(pd.read_csv(VAL_CSV, nrows=0).columns)
extra_excl = ["endTurn", "potionsConsumed"] + [c for c in val_header if c.startswith("pUsed")]
canonical = [c for c in val_header if c not in ("seed", "fightIdx", "won", "endHp", *extra_excl)]
groups = column_groups(canonical)

pol_header = list(pd.read_csv(POL_CSV, nrows=0).columns)
POL_META = ("seed", "fightIdx", "decIdx", "visit", "total")
action_names = [c for c in pol_header if c not in canonical and c not in POL_META]
# §3.5: fairgen policy rows carry extra subset-content action features; the
# PVNet action encoder reads the first 14.
if len(action_names) < 14:
    raise SystemExit(f"expected >=14 action features, got {len(action_names)}")
action_names = action_names[:14]

model, D, H, HDS, L, NQ, scalar_sel = load_native_model(MODEL)
print(f"[model] d={D} h={H} heads={HDS} layers={L} nq={NQ}")

BATCH = 512
VCOLS = canonical + ["seed", "won", "endHp", "maxHp"]
PCOLS = canonical + action_names + ["seed", "fightIdx", "decIdx", "visit", "total"]


def seed_filter(df):
    if not VAL_ONLY:
        return df
    m = df["seed"].map(lambda s: int(s) % 100
                       < int(float(os.environ.get("PVNET_VAL_FRAC", "0.2")) * 100)
                       ).to_numpy(np.bool_)
    return df[m]


# ── Value metrics ───────────────────────────────────────────────────────────
def value_metrics():
    n_rows = 0
    acc = {
        "brier": 0.0, "logloss": 0.0, "death_bce": 0.0, "n": 0.0,
        "ece_n": 0.0, "ece_acc": 0.0, "ece_conf": 0.0,
        "qcov": np.zeros(NQ), "qcov_n": 0.0,
    }
    tau = torch.linspace(0.05, 0.95, NQ).numpy()
    for df in pd.read_csv(VAL_CSV, usecols=VCOLS, chunksize=20000):
        df = seed_filter(df)
        if len(df) == 0:
            continue
        if MAX_ROWS and n_rows + len(df) > MAX_ROWS:
            df = df.iloc[:MAX_ROWS - n_rows]
        z = encode_states(model, df[canonical], groups)
        _, win, death, q, _, _ = evaluate_heads(model, z, np.zeros((len(df), 14), np.float32))
        won = df["won"].to_numpy(np.float32)
        hp = df["endHp"].to_numpy(np.float32)
        mh = df["maxHp"].to_numpy(np.float32)
        acc["n"] += len(df)
        acc["brier"] += ((win - won) ** 2).sum()
        eps = 1e-7
        acc["logloss"] += -(won * np.log(win + eps) + (1 - won) * np.log(1 - win + eps)).sum()
        acc["death_bce"] += -(won * np.log(death + eps) + (1 - won) * np.log(1 - death + eps)).sum()
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
            for k in range(NQ):
                acc["qcov"][k] += (frac <= q[wonm, k]).sum()
            acc["qcov_n"] += wonm.sum()
        n_rows += len(df)
        if MAX_ROWS and n_rows >= MAX_ROWS:
            break
    res = {
        "win_brier": acc["brier"] / max(acc["n"], 1),
        "win_logloss": acc["logloss"] / max(acc["n"], 1),
        "death_bce": acc["death_bce"] / max(acc["n"], 1),
        "win_ece": abs(acc["ece_acc"] - acc["ece_conf"]) / max(acc["ece_n"], 1),
        "n_states": int(acc["n"]),
    }
    if acc["qcov_n"] > 0:
        res["quantile_coverage"] = (acc["qcov"] / acc["qcov_n"]).tolist()
        res["quantile_targets"] = tau.tolist()
    return res


# ── Policy metrics ──────────────────────────────────────────────────────────
def softmax(x):
    x = x - x.max()
    e = np.exp(x)
    return e / e.sum()


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


def policy_metrics():
    acc = {"ce": 0.0, "kl": 0.0, "top1": 0.0, "top3": 0.0, "regret": 0.0,
           "n_groups": 0.0, "n_actions": 0.0, "entropy": 0.0}
    n_rows = 0
    for df in pd.read_csv(POL_CSV, usecols=PCOLS, chunksize=20000):
        df = seed_filter(df)
        if len(df) < 2:
            continue
        if MAX_ROWS and n_rows + len(df) > MAX_ROWS:
            df = df.iloc[:MAX_ROWS - n_rows]
        seeds = df["seed"].to_numpy(np.int64)
        fights = df["fightIdx"].to_numpy(np.int32)
        decs = df["decIdx"].to_numpy(np.int32)
        changes = (seeds[1:] != seeds[:-1]) | (fights[1:] != fights[:-1]) | (decs[1:] != decs[:-1])
        boundaries = np.where(changes)[0] + 1
        g_starts = np.concatenate([[0], boundaries])
        g_ends = np.concatenate([boundaries, [len(df)]])
        valid = (g_ends - g_starts) >= 2
        g_starts = g_starts[valid]
        g_ends = g_ends[valid]
        if len(g_starts) == 0:
            continue
        df_batch = pd.DataFrame(df[canonical].to_numpy(np.float32)[g_starts],
                                columns=canonical)
        z_all = encode_states(model, df_batch, groups)
        visit_arr = df["visit"].to_numpy(np.int32)
        total_arr = df["total"].to_numpy(np.int32)
        action_arr = df[action_names].to_numpy(np.float32)
        for gi in range(len(g_starts)):
            gs, ge = g_starts[gi], g_ends[gi]
            tot = int(total_arr[gs])
            if tot <= 0:
                continue
            n_act = ge - gs
            zt = torch.from_numpy(z_all[gi:gi + 1].repeat(n_act, axis=0))
            logits = model.policy(zt, torch.from_numpy(action_arr[gs:ge]))
            logits = logits.detach().numpy()
            p = softmax(logits)
            target = visit_arr[gs:ge].astype(np.float64) / tot
            eps = 1e-9
            q = p + eps
            acc["ce"] += -(target * np.log(q)).sum()
            acc["kl"] += (target * np.log((target + eps) / q)).sum()
            acc["top1"] += int(np.argmax(p) == np.argmax(target))
            acc["top3"] += int(np.argmax(target) in np.argsort(p)[-3:])
            acc["regret"] += 1.0 - target[np.argmax(p)]
            acc["entropy"] += -(target * np.log(target + eps)).sum()
            acc["n_groups"] += 1
            acc["n_actions"] += n_act
        n_rows += len(df)
        if MAX_ROWS and n_rows >= MAX_ROWS:
            break
    ng = max(acc["n_groups"], 1)
    return {
        "policy_ce": acc["ce"] / ng,
        "policy_kl": acc["kl"] / ng,
        "top1_agreement": acc["top1"] / ng,
        "top3_recall": acc["top3"] / ng,
        "expected_teacher_regret": acc["regret"] / ng,
        "mean_teacher_entropy": acc["entropy"] / ng,
        "n_groups": int(acc["n_groups"]),
        "n_actions": int(acc["n_actions"]),
    }


print("[eval] value metrics...", flush=True)
vm = value_metrics()
print("[eval] policy metrics...", flush=True)
pm = policy_metrics()
out = to_plain({"model": MODEL, "val_only": VAL_ONLY, "value": vm, "policy": pm})
print(json.dumps(out, indent=2))
if JSON_OUT:
    with open(JSON_OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"[eval] wrote {JSON_OUT}")
