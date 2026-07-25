#!/usr/bin/env python3
"""Train an action-value model from checkpoint-oracle teacher traces.

Each row is one legal OOC action with its meanUtility from the all-OOC
checkpoint oracle (MCTS-evaluated encounter distributions at each combat).
The network scores (state + screen + act + action bits) -> utility, and is
evaluated by per-decision-group action ranking.
"""
import json, os, sys

import numpy as np
import pandas as pd
import torch
from torch import nn

CSV = sys.argv[1] if len(sys.argv) > 1 else "selfplay/gate/teacher_checkpoint_16.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "selfplay/models/ooc_checkpoint"
EPOCHS = int(os.environ.get("OOC_CP_EPOCHS", "120"))
BATCH = int(os.environ.get("OOC_CP_BATCH", "512"))
LR = float(os.environ.get("OOC_CP_LR", "2e-3"))
THREADS = int(os.environ.get("OMP_NUM_THREADS", "8"))
DEVICE = os.environ.get("OOC_CP_DEVICE", "cpu")
if not DEVICE.startswith("cuda"):
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
torch.set_num_threads(THREADS)
torch.manual_seed(0)

df = pd.read_csv(CSV)
need = {"seed", "decisionIdx", "action", "screen", "act", "meanUtility", "stateFeatures"}
missing = need - set(df.columns)
if missing:
    raise ValueError(f"missing columns: {sorted(missing)}")

print(f"{len(df):,} rows, {df.seed.nunique()} seeds, "
      f"{len(df.groupby(['seed','decisionIdx']))} decisions", flush=True)

state = np.stack([np.fromstring(x, sep=",") for x in df.stateFeatures]).astype(np.float32)
if state.shape[1] != 1017:
    raise ValueError(f"expected 1017 state features, got {state.shape[1]}")

def parse_bits(x):
    if isinstance(x, str) and x.startswith("bits="):
        return int(x.split("=")[1])
    return int(x)

action_ints = np.array([parse_bits(x) for x in df.action], np.uint32)
bits = np.asarray([[(int(x) >> i) & 1 for i in range(32)] for x in action_ints], np.float32)
screen = np.clip(df.screen.to_numpy(np.int64), 0, 15)
act = np.clip(df.act.to_numpy(np.int64), 0, 3)
utility = df.meanUtility.to_numpy(np.float32)

groups = df.seed.to_numpy(np.int64) * 1000000 + df.decisionIdx.to_numpy(np.int64)
ug = np.unique(groups)
rng = np.random.default_rng(0); rng.shuffle(ug)
cut = max(1, int(0.8 * len(ug)))
tr_groups = set(ug[:cut])
tr = np.array([g in tr_groups for g in groups]); va = ~tr
if va.sum() == 0:
    raise ValueError("need held-out decision groups")
print(f"train: {tr.sum()} rows / {len(tr_groups)} groups, "
      f"val: {va.sum()} rows / {len(ug) - cut} groups", flush=True)

mean = state[tr].mean(0).astype(np.float32)
inv = 1 / np.maximum(state[tr].std(0).astype(np.float32), 1e-6)
state = np.clip((state - mean) * inv, -8, 8)


class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.s = nn.Sequential(nn.Linear(1017, 256), nn.LayerNorm(256), nn.GELU(),
                               nn.Dropout(0.2),
                               nn.Linear(256, 128), nn.GELU())
        self.a = nn.Sequential(nn.Linear(32, 32), nn.GELU(), nn.Dropout(0.2),
                               nn.Linear(32, 16))
        self.screen = nn.Embedding(16, 8)
        self.act_emb = nn.Embedding(4, 4)
        self.h = nn.Sequential(nn.Linear(156, 96), nn.GELU(), nn.Linear(96, 1))

    def forward(self, x, bits, screen, act_val):
        z = torch.cat((self.s(x), self.a(bits), self.screen(screen),
                       self.act_emb(act_val)), 1)
        return self.h(z).squeeze(1)


model = Net().to(DEVICE)
opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=2e-4)

T = [torch.from_numpy(x) for x in (state, bits, screen, act, utility)]
itr, iva = np.flatnonzero(tr), np.flatnonzero(va)


def fwd(ids):
    x = (T[0][ids].to(DEVICE), T[1][ids].to(DEVICE),
         T[2][ids].long().to(DEVICE), T[3][ids].long().to(DEVICE))
    return model(*x)


@torch.no_grad()
def score(ids):
    ids = torch.from_numpy(np.asarray(ids))
    pred = fwd(ids).cpu().numpy()
    truth = T[4][ids].numpy()
    mse = float(np.mean((pred - truth) ** 2))
    best = tied = total = reg = 0
    cand_wins = tree_wins = 0
    pairwise = []
    for g in np.unique(groups[ids]):
        q = np.flatnonzero(groups[ids] == g)
        if len(q) < 2:
            continue
        pv = pred[q]; tv = truth[q]
        best += int(np.argmax(pv) == np.argmax(tv))
        tied += int(np.argmax(pv) in np.flatnonzero(tv == tv.max()))
        reg += tv.max() - tv[np.argmax(pv)]
        total += 1
        # Per-group tree reference: best random-action baseline utility
        pairwise.append((float(tv[np.argmax(pv)]), float(tv.max())))
    pn = np.array(pairwise)
    return {
        "groups": total,
        "rmse": float(np.sqrt(mse)),
        "mae": float(np.mean(np.abs(pred - truth))),
        "best_action": best / max(1, total),
        "best_or_tied": tied / max(1, total),
        "mean_regret": reg / max(1, total),
        "mean_utility": float(np.mean(pred)),
    }


def to_py(obj):
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {k: to_py(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_py(x) for x in obj]
    return obj


best_loss = float("inf"); best_state = None
best_regret = float("inf"); best_rank_state = None
for epoch in range(1, EPOCHS + 1):
    model.train()
    order = rng.permutation(itr)
    losses = []
    for lo in range(0, len(order), BATCH):
        ids = order[lo:lo + BATCH]
        pred = fwd(torch.from_numpy(ids))
        loss = nn.functional.mse_loss(pred, T[4][ids].to(DEVICE))
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        losses.append(float(loss.detach()))
    model.eval()
    ti = torch.from_numpy(iva)
    val_loss = float(nn.functional.mse_loss(fwd(ti), T[4][ti].to(DEVICE)))
    m = score(iva)
    if val_loss < best_loss:
        best_loss = val_loss
        best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    if m["mean_regret"] < best_regret:
        best_regret = m["mean_regret"]
        best_rank_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    if epoch == 1 or epoch % 10 == 0:
        print(f"epoch={epoch:03d} train_mse={np.mean(losses):.4f} "
              f"val_mse={val_loss:.4f} metrics={to_py(m)}", flush=True)

model.load_state_dict(best_rank_state)
eval_metrics = to_py(score(iva))
print(f"\nbest ranking held-out: {eval_metrics}", flush=True)

os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
torch.save({"state_dict": model.cpu().state_dict(), "mean": mean, "inv": inv,
            "metrics": eval_metrics, "features": 1017}, OUT + ".pt")
model.eval()
example = (T[0][:1], T[1][:1], T[2][:1].long(), T[3][:1].long())
torch.jit.trace(model.cpu(), example).save(OUT + ".torchscript")
with open(OUT + "_metrics.json", "w") as f:
    json.dump(eval_metrics, f, indent=2)
print(f"wrote {OUT}.pt, {OUT}.torchscript, {OUT}_metrics.json", flush=True)
