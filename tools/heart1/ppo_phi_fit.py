"""Fit the potentials of ppo_phi.py from recorded PPO games (reward screen 2).

    python3 tools/heart1/ppo_phi_fit.py floor-table --games 's1res/*/games-*.csv' --out phi_floor.json
        Phi(f) = P(Heart kill | the game reached floor f), from the final floor and outcome of every game.
    python3 tools/heart1/ppo_phi_fit.py logistic --table phi_floor.json --traj A/parts/*.jsonl.gz \
        --holdout B/parts/*.jsonl.gz --every 4 --out phi_state.json
        L2 logistic regression of the game's Heart kill on ppo_phi.features() of each net decision (of every
        EVERY-th game by seed, to bound parsing time), fit on --traj, scored on --holdout against the floor table.
"""
import argparse
import csv
import glob
import gzip
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ppo_phi  # noqa: E402

NET_SOURCES = ("heart1_ppo", "heart1_ppo_single")
MAX_FLOOR = 56


def cmd_floor_table(argv):
    ap = argparse.ArgumentParser(prog="ppo_phi_fit.py floor-table")
    ap.add_argument("--games", required=True, help="glob of games-NNNN.csv (arm,iteration,seed,heart_kill,floor,net)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    ended = [0] * (MAX_FLOOR + 1)
    kills = 0
    n = 0
    files = sorted(glob.glob(a.games))
    for path in files:
        for r in csv.DictReader(open(path)):
            if r["floor"] == "":
                continue   # a stalled game without a floor: no information on the floor reached
            f = min(int(r["floor"]), MAX_FLOOR)
            ended[f] += 1
            kills += int(r["heart_kill"])
            n += 1
    # A kill ends at the last floor, so every kill reached every floor: P(kill | reached f) = kills / reached(f).
    table, reached = [0.0] * (MAX_FLOOR + 1), n
    for f in range(MAX_FLOOR + 1):
        table[f] = kills / reached if reached else table[f - 1]
        reached -= ended[f]
    out = {"kind": "floor_table", "table": [round(x, 6) for x in table], "games": n, "kills": kills,
           "files": len(files), "source": a.games}
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"{n} games, {kills} kills; phi floor 0 {table[0]:.4f}, 16 {table[16]:.4f}, 33 {table[33]:.4f}, "
          f"50 {table[50]:.4f}, 56 {table[56]:.4f}")


def read_rows(paths, table, every):
    """(features, heart_kill, floor-table phi) per net decision of every EVERY-th game (seed % every == 0)."""
    X, y, base = [], [], []
    for path in paths:
        pending = {}
        with gzip.open(path, "rt") if path.endswith(".gz") else open(path) as f:
            for line in f:
                if not line.strip():
                    continue
                # Cheap seed filter before parsing the (large) record.
                k = line.find('"seed":')
                if k >= 0:
                    seed = int(line[k + 7:].lstrip(' "').split('"')[0].split(",")[0])
                    if seed % every:
                        continue
                row = json.loads(line)
                if row["type"] == "decision" and row["source"] in NET_SOURCES:
                    pending.setdefault(row["seed"], []).append(
                        (ppo_phi.features(table, row, row["record"]), ppo_phi.value(table, row, row["record"])))
                elif row["type"] == "game":
                    win = 1.0 if row["outcome"].get("heart_kill") else 0.0
                    for x, b in pending.pop(row["seed"], []):
                        X.append(x); y.append(win); base.append(b)
    return X, y, base


def logloss(p, y):
    e = 1e-6
    return -sum(t * math.log(max(q, e)) + (1 - t) * math.log(max(1 - q, e)) for q, t in zip(p, y)) / max(len(y), 1)


def cmd_logistic(argv):
    import torch
    ap = argparse.ArgumentParser(prog="ppo_phi_fit.py logistic")
    ap.add_argument("--table", required=True)
    ap.add_argument("--traj", nargs="+", required=True)
    ap.add_argument("--holdout", nargs="+", required=True)
    ap.add_argument("--every", type=int, default=4)
    ap.add_argument("--l2", type=float, default=1e-4)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    table = ppo_phi.load(a.table)
    X, y, _ = read_rows(sorted(a.traj), table, a.every)
    Xh, yh, bh = read_rows(sorted(a.holdout), table, a.every)
    print(f"fit {len(y)} decisions ({sum(y) / max(len(y), 1):.4f} win), holdout {len(yh)}", flush=True)
    Xt = torch.tensor(X, dtype=torch.float64)
    mean, scale = Xt.mean(0), Xt.std(0).clamp_min(1e-6)
    Z, Y = (Xt - mean) / scale, torch.tensor(y, dtype=torch.float64)
    w = torch.zeros(Z.shape[1], dtype=torch.float64, requires_grad=True)
    b = torch.zeros((), dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([w, b], max_iter=500, line_search_fn="strong_wolfe")

    def closure():
        opt.zero_grad()
        loss = torch.nn.functional.binary_cross_entropy_with_logits(Z @ w + b, Y) + a.l2 * (w * w).sum()
        loss.backward()
        return loss
    opt.step(closure)
    m = {"kind": "logistic", "table": table["table"], "features": list(ppo_phi.FEATURES),
         "mean": [float(v) for v in mean], "scale": [float(v) for v in scale],
         "coef": [float(v) for v in w.detach()], "intercept": float(b.detach())}
    zh = (torch.tensor(Xh, dtype=torch.float64) - mean) / scale
    p_state = torch.sigmoid(zh @ w.detach() + b.detach()).tolist()
    m["fit"] = {"decisions": len(y), "holdout_decisions": len(yh), "every": a.every, "l2": a.l2,
                "traj_files": len(a.traj), "holdout_files": len(a.holdout),
                "holdout_logloss_state": logloss(p_state, yh), "holdout_logloss_floor": logloss(bh, yh),
                "holdout_logloss_const": logloss([sum(yh) / max(len(yh), 1)] * len(yh), yh)}
    with open(a.out, "w") as fh:
        json.dump(m, fh, indent=1)
    print(json.dumps(m["fit"]))
    print("coef " + ", ".join(f"{k} {c:+.3f}" for k, c in zip(ppo_phi.FEATURES, m["coef"])))


if __name__ == "__main__":
    cmds = {"floor-table": cmd_floor_table, "logistic": cmd_logistic}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit("usage: ppo_phi_fit.py {floor-table|logistic} ...")
    cmds[sys.argv[1]](sys.argv[2:])
