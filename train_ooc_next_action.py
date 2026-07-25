#!/usr/bin/env python3
"""Train/evaluate an action-conditioned next-combat OOC model."""
import json, os, sys
import numpy as np
import pandas as pd
import torch
from torch import nn

CSV = sys.argv[1] if len(sys.argv) > 1 else "selfplay/ooc_buffer/next_combat_2000.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "selfplay/models/ooc_next_action"
torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "8")))
torch.manual_seed(0)

df = pd.read_csv(CSV)
need = {"seed", "decisionIdx", "actionBits", "screen", "act",
        "allEncounterWin", "allEncounterHp", "stateFeatures"}
missing = need - set(df.columns)
if missing:
    raise ValueError(f"missing columns: {sorted(missing)}")
state = np.stack([np.fromstring(x, sep=",") for x in df.stateFeatures]).astype(np.float32)
if state.shape[1] != 1017:
    raise ValueError(f"expected 1017 state features, got {state.shape}")

groups = df.seed.to_numpy(np.int64) * 100000 + df.decisionIdx.to_numpy(np.int64)
ug = np.unique(groups)
rng = np.random.default_rng(0); rng.shuffle(ug)
cut = max(1, int(.8 * len(ug)))
tr_groups = set(ug[:cut])
tr = np.array([g in tr_groups for g in groups]); va = ~tr
if va.sum() == 0: raise ValueError("need held-out decision groups")

mean = state[tr].mean(0); inv = 1 / np.maximum(state[tr].std(0), 1e-6)
state = np.clip((state - mean) * inv, -8, 8)
bits = np.asarray([[(int(x) >> i) & 1 for i in range(32)] for x in df.actionBits], np.float32)
screen = np.clip(df.screen.to_numpy(np.int64), 0, 15)
act = np.clip(df.act.to_numpy(np.int64), 0, 3)
maxhp = np.maximum(state[:, 4] * 0 + np.asarray([float(x.split(',')[4]) for x in df.stateFeatures]), 1)
ywin = df.allEncounterWin.to_numpy(np.float32)
yhp = np.clip(df.allEncounterHp.to_numpy(np.float32) / maxhp, 0, 1)
yscore = 10 * ywin + df.allEncounterHp.to_numpy(np.float32)

class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.s = nn.Sequential(nn.Linear(1017, 256), nn.LayerNorm(256), nn.SiLU(),
                               nn.Linear(256, 128), nn.SiLU())
        self.a = nn.Sequential(nn.Linear(32, 32), nn.SiLU(), nn.Linear(32, 16))
        self.screen = nn.Embedding(16, 8)
        self.act = nn.Embedding(4, 4)
        self.h = nn.Sequential(nn.Linear(156, 96), nn.SiLU(), nn.Linear(96, 2))

    def forward(self, x, bits, screen, act):
        z = torch.cat((self.s(x), self.a(bits), self.screen(screen), self.act(act)), 1)
        o = self.h(z)
        return o[:, 0], torch.sigmoid(o[:, 1])

model = Net()
opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=2e-4)
T = [torch.from_numpy(x) for x in (state, bits, screen, act, ywin, yhp)]
itr, iva = np.flatnonzero(tr), np.flatnonzero(va)

def pred(ids):
    ids = torch.from_numpy(np.asarray(ids))
    with torch.no_grad():
        wl, hp = model(T[0][ids], T[1][ids], T[2][ids].long(), T[3][ids].long())
    return torch.sigmoid(wl).numpy(), hp.numpy()

def score(ids):
    p, h = pred(ids); out = 10*p + h*maxhp[ids]
    best = tied = total = 0
    for g in np.unique(groups[ids]):
        q = np.flatnonzero(groups[ids] == g)
        if len(q) < 2: continue
        truth = yscore[ids[q]]; guess = out[q]
        best += int(np.argmax(guess) == np.argmax(truth))
        tied += int(np.argmax(guess) in np.flatnonzero(truth == truth.max()))
        total += 1
    return {"groups": total, "win_brier": float(np.mean((p-ywin[ids])**2)),
            "win_acc": float(np.mean((p >= .5) == (ywin[ids] >= .5))),
            "hp_frac_mae": float(np.mean(np.abs(h-yhp[ids]))),
            "best_action": best/max(1,total), "best_or_tied": tied/max(1,total)}

best_loss = float("inf"); best_state = None
for epoch in range(1, 121):
    model.train(); order = rng.permutation(itr)
    for lo in range(0, len(order), 512):
        ids = order[lo:lo+512]; ti = torch.from_numpy(ids)
        wl, hp = model(T[0][ti], T[1][ti], T[2][ti].long(), T[3][ti].long())
        loss = nn.functional.binary_cross_entropy_with_logits(wl, T[4][ti])
        loss = loss + 2*nn.functional.smooth_l1_loss(hp, T[5][ti])
        opt.zero_grad(); loss.backward(); opt.step()
    model.eval(); ti = torch.from_numpy(iva)
    with torch.no_grad():
        wl, hp = model(T[0][ti], T[1][ti], T[2][ti].long(), T[3][ti].long())
        val_loss = float(nn.functional.binary_cross_entropy_with_logits(wl, T[4][ti])
                         + 2*nn.functional.smooth_l1_loss(hp, T[5][ti]))
    if val_loss < best_loss:
        best_loss = val_loss; best_state = {k:v.detach().clone() for k,v in model.state_dict().items()}
    if epoch == 1 or epoch % 20 == 0:
        print(f"epoch={epoch} val_loss={val_loss:.4f} metrics={score(iva)}", flush=True)

model.load_state_dict(best_state); metrics = score(iva)
os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
torch.save({"state_dict": model.state_dict(), "mean": mean, "inv": inv,
            "metrics": metrics, "features": 1017}, OUT + ".pt")
model.eval()
example = (T[0][:2], T[1][:2], T[2][:2].long(), T[3][:2].long())
torch.jit.trace(model, example).save(OUT + ".torchscript")
with open(OUT + "_metrics.json", "w") as f: json.dump(metrics, f, indent=2)
print("best held-out metrics:", metrics, flush=True)
