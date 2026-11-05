"""Per-screen policy movement between stored nets: KL(net_a || last net) on one iteration's decision records.

PPO diagnostics findings 2026-11-05 (LONG_B: rewards 51-60% of the KL mass, shop 19%, map 13%). Scores the first
--max-decisions net decisions of iteration --iteration's parts with every --nets net (torch mirror, temperature 1)
and reports, for each listed net against the last one, mean KL, argmax agreement, per screen and per act, plus each
net's entropy per screen. Writes kl_summary.json and L4_policy_movement.png to --out only.

    python3 tools/heart1/longb_kl.py --run ~/ppo-longb/LONG_B --iteration 163 \
        --nets net-0106 net-0152 net-0162 net-0163 --out OUT_DIR

Nets are RUN/NAME.bin (--net-dir overrides), parts RUN/parts/traj-NNNN-pK.jsonl.gz (--traj-dir overrides); the
featurisation uses the last net's trim_map. Read only. Needs numpy, matplotlib and torch. For the KL of each update
inside a run, ppo_train --diag 1 logs kl_update per screen on the full batch.
"""
import argparse
import glob
import gzip
import json
import os
import sys
import time

import numpy as np
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ppo_model import PolicyNet, featurize, collate, batch_to  # noqa: E402

PAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, INK3, SURF, GRID = "#0b0b0b", "#52514e", "#8a8984", "#fcfcfb", "#e6e5e1"
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "axes.grid": True,
                     "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.spines.left": False, "axes.titlesize": 10.5, "axes.titleweight": "bold", "axes.titlelocation": "left",
                     "font.size": 9, "legend.frameon": False, "legend.fontsize": 8.5, "xtick.major.size": 0, "ytick.major.size": 0})
SCREEN = {1: "event", 2: "rewards", 3: "boss relic", 4: "card select", 5: "map", 6: "treasure", 7: "rest", 8: "shop"}
ap = argparse.ArgumentParser(prog="longb_kl.py", description=__doc__.split("\n\n")[0])
ap.add_argument("--run", required=True, help="the learner's arm directory")
ap.add_argument("--iteration", type=int, required=True, help="iteration whose decision records are scored")
ap.add_argument("--nets", nargs="+", required=True, help="net names (NAME.bin), oldest first; the last is the reference")
ap.add_argument("--net-dir", help="directory of the nets (default RUN)")
ap.add_argument("--traj-dir", help="directory of traj-NNNN-pK.jsonl.gz (default RUN/parts)")
ap.add_argument("--max-decisions", type=int, default=12000)
ap.add_argument("--threads", type=int, default=4)
ap.add_argument("--out", required=True)
A = ap.parse_args()
if len(A.nets) < 2:
    sys.exit("--nets needs at least two nets")
NETS = A.net_dir or A.run
TRAJ = A.traj_dir or os.path.join(A.run, "parts")
OUT, MAXD, IT = A.out, A.max_decisions, A.iteration
_o, _r = os.path.abspath(OUT), os.path.abspath(A.run)
if _o == _r or _o.startswith(_r + os.sep):
    sys.exit("--out must not be inside --run (the run directory is read only)")
os.makedirs(OUT, exist_ok=True)
torch.set_num_threads(A.threads)

rows = []
paths = sorted(glob.glob(os.path.join(TRAJ, f"traj-{IT:04d}-p*.jsonl.gz")), key=lambda x: int(x.split("-p")[-1].split(".")[0]))
if not paths:
    sys.exit(f"no {TRAJ}/traj-{IT:04d}-p*.jsonl.gz")
for p in paths:
    with gzip.open(p, "rt") as f:
        for line in f:
            r = json.loads(line)
            if r["type"] == "decision" and r["source"] == "heart1_ppo":
                rows.append(r)
    if len(rows) >= MAXD:
        break
rows = rows[:MAXD]
print("decisions", len(rows), flush=True)
trim = PolicyNet.from_bin(os.path.join(NETS, f"{A.nets[-1]}.bin")).trim_map
feats = [featurize(r["record"], trim) for r in rows]
screen = np.array([r["screen"] for r in rows]); act = np.array([r["act"] for r in rows]); n = np.array([r["n"] for r in rows])
chosen = np.array([r["chosen"] for r in rows])


def logps(name):
    net = PolicyNet.from_bin(os.path.join(NETS, f"{name}.bin")); net.eval()
    out = []
    t0 = time.time()
    with torch.no_grad():
        for i in range(0, len(feats), 64):
            b = collate(feats[i:i + 64])
            lg = net(batch_to(b, torch.device("cpu")))[0].float()
            lp = torch.log_softmax(lg, -1)
            for k in range(lp.shape[0]):
                out.append(lp[k, :n[i + k]].numpy())
    print(name, "done", round(time.time() - t0), "s", flush=True)
    return out


nets = list(A.nets)
LP = {m: logps(m) for m in nets}


def kl(a, b):
    return np.array([float((np.exp(x) * (x - y)).sum()) for x, y in zip(LP[a], LP[b])])


def ent(a):
    return np.array([float(-(np.exp(x) * x).sum()) for x in LP[a]])


def agree(a, b):
    return np.array([int(np.argmax(x) == np.argmax(y)) for x, y in zip(LP[a], LP[b])])


pairs = [(a, nets[-1], f"{a} vs {nets[-1]}") for a in reversed(nets[:-1])]   # nearest first
res = {"n": len(rows), "pairs": {}}
for a, b, lab in pairs:
    k = kl(a, b); ag = agree(a, b)
    per = {}
    for sc in sorted(set(screen.tolist())):
        m = screen == sc
        per[SCREEN.get(int(sc), str(sc))] = {"n": int(m.sum()), "kl_mean": float(k[m].mean()), "kl_share": float(k[m].sum() / k.sum()),
                                           "argmax_agree": float(ag[m].mean()), "share_decisions": float(m.mean())}
    per_act = {int(x): {"n": int((act == x).sum()), "kl_mean": float(k[act == x].mean()), "argmax_agree": float(ag[act == x].mean())} for x in (1, 2, 3, 4)}
    res["pairs"][lab] = {"kl_mean": float(k.mean()), "argmax_agree": float(ag.mean()), "per_screen": per, "per_act": per_act}
res["entropy"] = {m: {SCREEN.get(int(sc), str(sc)): float(ent(m)[screen == sc].mean()) for sc in sorted(set(screen.tolist()))} for m in nets}
res["entropy_all"] = {m: float(ent(m).mean()) for m in nets}
json.dump(res, open(os.path.join(OUT, "kl_summary.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != "pairs"}, indent=1))
for lab, v in res["pairs"].items():
    print(lab, "KL", round(v["kl_mean"], 4), "agree", round(v["argmax_agree"], 3))
    for sc, d in v["per_screen"].items():
        print(f"   {sc:12s} n={d['n']:5d} KL={d['kl_mean']:.4f} share={d['kl_share']*100:5.1f}% agree={d['argmax_agree']:.3f}")

first = pairs[0][2]
names = [s for s in ("rewards", "map", "shop", "event", "rest", "card select", "boss relic", "treasure") if s in res["pairs"][first]["per_screen"]]
fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
xs = np.arange(len(names)); w = 0.8 / len(pairs)
for j, (a, b, lab) in enumerate(pairs):
    axes[0].bar(xs + (j - (len(pairs) - 1) / 2) * w, [res["pairs"][lab]["per_screen"][s]["kl_mean"] for s in names], w, color=PAL[j], label=lab)
    axes[1].bar(xs + (j - (len(pairs) - 1) / 2) * w, [res["pairs"][lab]["per_screen"][s]["kl_share"] * 100 for s in names], w, color=PAL[j], label=lab)
axes[1].plot(xs, [res["pairs"][first]["per_screen"][s]["share_decisions"] * 100 for s in names], "o", color=INK, ms=5, label="share of decisions", zorder=4)
axes[0].set_title(f"Mean KL(old net ‖ {nets[-1]}) per decision, by screen"); axes[0].set_ylabel("KL (nats)")
axes[1].set_title("Share of the total KL mass by screen (dots: share of decisions)"); axes[1].set_ylabel("%")
for ax in axes[:2]:
    ax.set_xticks(xs); ax.set_xticklabels(names, rotation=20); ax.legend()
ax = axes[2]
for j, m in enumerate(nets):
    wd = 0.8 / len(nets)
    ax.bar(xs + (j - (len(nets) - 1) / 2) * wd, [res["entropy"][m][s] for s in names], wd, color=PAL[j % len(PAL)], label=m)
ax.set_xticks(xs); ax.set_xticklabels(names, rotation=20); ax.set_title(f"Choice entropy per screen, {len(nets)} nets of the run"); ax.legend()
fig.suptitle(f"Where the policy moves — {len(rows):,} iteration-{IT} decisions scored by {len(nets)} stored nets (temperature 1)",
             x=0.01, ha="left", fontsize=12, weight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.94)); fig.savefig(os.path.join(OUT, "L4_policy_movement.png"), dpi=160)
