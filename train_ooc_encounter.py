#!/usr/bin/env python3
"""Train an encounter-conditioned next-combat OOC action model."""
import json, os, sys
import numpy as np
import pandas as pd
import torch
from torch import nn

CSV = sys.argv[1] if len(sys.argv) > 1 else "selfplay/ooc_buffer/next_combat_encounter_2000.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "selfplay/models/ooc_encounter_action_2000"
torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "8")))
torch.manual_seed(0)

df = pd.read_csv(CSV)
need = {"seed", "decisionIdx", "actionBits", "screen", "act", "stateFeatures", "encounterLabels"}
missing = need - set(df.columns)
if missing: raise ValueError(f"missing columns: {sorted(missing)}")

rows = []
for rid, row in df.iterrows():
    labels = str(row.encounterLabels)
    for token in labels.split("|"):
        if not token or token == "nan": continue
        eid, prob, win, hp = token.split(":")
        rows.append((rid, int(eid), float(prob), float(win), float(hp)))
if not rows: raise ValueError("no encounter labels")

base = np.stack([np.fromstring(x, sep=",") for x in df.stateFeatures]).astype(np.float32)
if base.shape[1] != 1017: raise ValueError(f"expected 1017 state features, got {base.shape}")
groups = df.seed.to_numpy(np.int64) * 100000 + df.decisionIdx.to_numpy(np.int64)
ug = np.unique(groups); rng = np.random.default_rng(0); rng.shuffle(ug)
cut = max(1, int(.8 * len(ug))); tr_groups = set(ug[:cut])
tr_base = np.array([g in tr_groups for g in groups])
mean = base[tr_base].mean(0); inv = 1 / np.maximum(base[tr_base].std(0), 1e-6)
base = np.clip((base - mean) * inv, -8, 8)

rid = np.asarray([r[0] for r in rows], np.int64)
enc = np.asarray([r[1] for r in rows], np.int64)
prob = np.asarray([r[2] for r in rows], np.float32)
ywin = np.asarray([r[3] for r in rows], np.float32)
hp_abs = np.asarray([r[4] for r in rows], np.float32)
maxhp_by_row = np.asarray([float(str(df.stateFeatures.iloc[int(x)]).split(',')[4]) for x in rid], np.float32)
yhp = np.clip(hp_abs / np.maximum(maxhp_by_row, 1.0), 0, 1)
bits0 = np.asarray([[(int(x) >> i) & 1 for i in range(32)] for x in df.actionBits], np.float32)
bits = bits0[rid]
state = base[rid]
screen = np.clip(df.screen.to_numpy(np.int64)[rid], 0, 15)
act = np.clip(df.act.to_numpy(np.int64)[rid], 0, 3)
tr = tr_base[rid]

class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.s = nn.Sequential(nn.Linear(1017, 256), nn.LayerNorm(256), nn.SiLU(),
                               nn.Linear(256, 128), nn.SiLU())
        self.a = nn.Sequential(nn.Linear(32, 32), nn.SiLU(), nn.Linear(32, 16))
        self.screen = nn.Embedding(16, 8)
        self.act = nn.Embedding(4, 4)
        self.encounter = nn.Embedding(128, 8)
        self.h = nn.Sequential(nn.Linear(164, 96), nn.SiLU(), nn.Linear(96, 2))
    def forward(self, x, bits, screen, act, encounter):
        z = torch.cat((self.s(x), self.a(bits), self.screen(screen), self.act(act),
                       self.encounter(encounter)), 1)
        o = self.h(z)
        return o[:, 0], torch.sigmoid(o[:, 1])

T = [torch.from_numpy(x) for x in (state, bits, screen, act, enc, ywin, yhp, prob)]
itr, iva = np.flatnonzero(tr), np.flatnonzero(~tr)
model = Net(); opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=2e-4)

def pred(ids):
    ids = torch.from_numpy(np.asarray(ids))
    with torch.no_grad():
        wl, hp = model(T[0][ids], T[1][ids], T[2][ids].long(), T[3][ids].long(), T[4][ids].long())
    return torch.sigmoid(wl).numpy(), hp.numpy()

def metrics(ids):
    p, h = pred(ids)
    maxhp = maxhp_by_row[ids]
    out = 10*p + h*maxhp
    # Compare action ranking after probability-weighting encounter predictions.
    action_groups = {}
    for j, rowid in enumerate(rid[ids]):
        key = int(groups[rowid]); action_groups.setdefault(key, []).append(j)
    exact = tied = total = 0
    for key, js in action_groups.items():
        if len(js) == 0: continue
        # Each encounter row belongs to one action; aggregate below by action bits.
        by_action = {}
        for j in js:
            rowid = rid[ids[j]]
            by_action.setdefault(int(df.actionBits.iloc[rowid]), [0., 0.])
            by_action[int(df.actionBits.iloc[rowid])][0] += prob[ids[j]] * out[j]
            by_action[int(df.actionBits.iloc[rowid])][1] += prob[ids[j]] * (10*ywin[ids[j]] + yhp[ids[j]] * maxhp_by_row[ids[j]])
        if len(by_action) < 2: continue
        pa = list(by_action); pv = np.asarray([by_action[a][0] for a in pa]); tv = np.asarray([by_action[a][1] for a in pa])
        exact += int(np.argmax(pv) == np.argmax(tv)); tied += int(np.argmax(pv) in np.flatnonzero(tv == tv.max())); total += 1
    return {"encounter_rows": int(len(ids)), "win_brier": float(np.mean((p-ywin[ids])**2)),
            "hp_mae": float(np.mean(np.abs(h-yhp[ids]))), "best_action": exact/max(1,total),
            "best_or_tied": tied/max(1,total), "groups": total}

best_loss = float("inf"); best_state = None
for epoch in range(1, 121):
    model.train(); order = rng.permutation(itr)
    for lo in range(0, len(order), 512):
        ids = order[lo:lo+512]; ti = torch.from_numpy(ids)
        wl, hp = model(T[0][ti], T[1][ti], T[2][ti].long(), T[3][ti].long(), T[4][ti].long())
        loss = nn.functional.binary_cross_entropy_with_logits(wl, T[5][ti])
        loss = loss + 2*nn.functional.smooth_l1_loss(hp, T[6][ti])
        opt.zero_grad(); loss.backward(); opt.step()
    model.eval(); ti = torch.from_numpy(iva)
    with torch.no_grad():
        wl, hp = model(T[0][ti], T[1][ti], T[2][ti].long(), T[3][ti].long(), T[4][ti].long())
        val_loss = float(nn.functional.binary_cross_entropy_with_logits(wl, T[5][ti]) +
                         2*nn.functional.smooth_l1_loss(hp, T[6][ti]))
    if val_loss < best_loss:
        best_loss = val_loss; best_state = {k:v.detach().clone() for k,v in model.state_dict().items()}
    if epoch == 1 or epoch % 20 == 0:
        print(f"epoch={epoch} val_loss={val_loss:.4f} metrics={metrics(iva)}", flush=True)

model.load_state_dict(best_state); model.eval(); m = metrics(iva)
os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
torch.save({"state_dict": model.state_dict(), "mean": mean, "inv": inv,
            "metrics": m, "features": 1017}, OUT + ".pt")
example = (T[0][:2], T[1][:2], T[2][:2].long(), T[3][:2].long(), T[4][:2].long())
torch.jit.trace(model, example).save(OUT + ".torchscript")
with open(OUT + "_metrics.json", "w") as f: json.dump(m, f, indent=2)
print("best held-out metrics:", m, flush=True)
