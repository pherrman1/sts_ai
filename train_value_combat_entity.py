#!/usr/bin/env python3
"""Train an entity-aware, multi-head combat value model.

The model encodes card zones, relics, potions, encounters, and monsters as
entities instead of treating their integer IDs as continuous scalar values. It
predicts P(fight win) and remaining-HP fraction conditional on a win. Search can
then derive a risk-aware scalar utility:

    P(win) * (win_bonus + E[end HP | win])

The replay CSV is streamed and sampled by whole fight. Validation is also split
by fight, never by adjacent decision rows from the same trajectory.
"""
import copy
import os
import re
import sys
import gc
import numpy as np
import pandas as pd
import torch
from torch import nn
import xgboost as xgb


CSV = sys.argv[1] if len(sys.argv) > 1 else "selfplay/cbuffer/_train_combat.csv"
TEACHER = sys.argv[2] if len(sys.argv) > 2 else ""
OUT = sys.argv[3] if len(sys.argv) > 3 else "build/v_combat_entity.txt"
VAL = sys.argv[4] if len(sys.argv) > 4 else "build/v_combat_entity_val.csv"

SAMPLE_MOD = max(1, int(os.environ.get("ENTITY_SAMPLE_MOD", "2")))
EPOCHS = int(os.environ.get("ENTITY_EPOCHS", "15"))
BATCH = int(os.environ.get("ENTITY_BATCH", "4096"))
THREADS = int(os.environ.get("OMP_NUM_THREADS", "16"))
WIN_BONUS = float(os.environ.get("ENTITY_WIN_BONUS", "50"))
CHUNK = int(os.environ.get("ENTITY_CHUNK_ROWS", "5000"))
DEVICE = os.environ.get("ENTITY_DEVICE", "cuda")
if DEVICE == "cuda" and torch.cuda.is_available():
    print(f"[GPU] {torch.cuda.get_device_name(0)}", flush=True)
else:
    DEVICE = "cpu"
torch.set_num_threads(THREADS)
torch.manual_seed(0)


def mix64(x):
    x = np.asarray(x, dtype=np.uint64)
    x = x ^ (x >> np.uint64(30))
    x = x * np.uint64(0xbf58476d1ce4e5b9)
    x = x ^ (x >> np.uint64(27))
    x = x * np.uint64(0x94d049bb133111eb)
    return x ^ (x >> np.uint64(31))


header = list(pd.read_csv(CSV, nrows=0).columns)
canonical = [c for c in header if c not in ("seed", "fightIdx", "won", "endHp")]
zones = [[f"{p}{i}" for i in range(371)] for p in ("hd", "dr", "ds", "ex")]
relic_cols = [f"r{i}" for i in range(128)]
potion_cols = [f"pot{i}" for i in range(44)]
monster_cols = [[f"m{i}{s}" for s in
                 ("Id", "Hp", "Block", "Str", "Intent", "Atk", "Vuln", "Weak", "Poison")]
                for i in range(5)]
monster_flat = [c for row in monster_cols for c in row]
entity_cols = set(relic_cols + potion_cols + monster_flat + ["encounter"]
                  + [c for z in zones for c in z])
scalar_cols = [c for c in canonical if c not in entity_cols]
assert len(canonical) == 1766 and len(scalar_cols) == 64

teacher = None
teacher_features = []
if os.path.exists(TEACHER):
    try:
        teacher = xgb.Booster(); teacher.load_model(TEACHER)
        teacher_features = list(teacher.feature_names)
        print(f"[teacher] loaded {TEACHER} ({len(teacher_features)} features)", flush=True)
    except Exception as e:
        print(f"[WARN] teacher not loadable ({e})", flush=True)
        teacher = None
dtypes = {c: (np.int32 if c in ("seed", "fightIdx") else np.int16) for c in header}


def extract(df):
    n = len(df)
    scalar = df[scalar_cols].to_numpy(np.float32)
    cards = np.stack([df[z].to_numpy(np.uint8) for z in zones], axis=1)
    relics = df[relic_cols].to_numpy(np.uint8)
    potions = df[potion_cols].to_numpy(np.uint8)
    encounter = np.clip(df["encounter"].to_numpy(np.int64), 0, 127).astype(np.uint8)
    mids = np.empty((n, 5), np.int16)
    intents = np.empty((n, 5), np.uint8)
    mcont = np.empty((n, 5, 7), np.float32)
    mmask = np.empty((n, 5), np.bool_)
    for i, cols in enumerate(monster_cols):
        mids[:, i] = np.clip(df[cols[0]].to_numpy(np.int64), 0, 255)
        hp = df[cols[1]].to_numpy(np.float32)
        intents[:, i] = np.clip(df[cols[4]].to_numpy(np.int64), 0, 31)
        # HP, block, strength, attack, vulnerable, weak, poison.
        mcont[:, i] = df[[cols[j] for j in (1, 2, 3, 5, 6, 7, 8)]].to_numpy(np.float32)
        mmask[:, i] = hp > 0
    return scalar, cards, relics, potions, encounter, mids, intents, mcont, mmask


parts = [[] for _ in range(14)]
seen = kept = 0
print(f"streaming {CSV}; keeping about 1/{SAMPLE_MOD} of whole fights ...", flush=True)
for ci, df in enumerate(pd.read_csv(CSV, dtype=dtypes, chunksize=CHUNK)):
    seed = df["seed"].to_numpy(np.uint64)
    fight = df["fightIdx"].to_numpy(np.uint64)
    group = seed * np.uint64(1000) + fight
    keep = (mix64(group + np.uint64(0x9e3779b97f4a7c15))
            % np.uint64(SAMPLE_MOD)) == 0
    seen += len(df)
    if keep.any():
        p = df.loc[keep]
        arrays = extract(p)
        for dst, a in zip(parts[:9], arrays): dst.append(a)
        won = p["won"].to_numpy(np.float32)
        maxhp = np.maximum(p["maxHp"].to_numpy(np.float32), 1.0)
        endhp = p["endHp"].to_numpy(np.float32)
        hpfrac = np.clip(endhp / maxhp, 0, 1).astype(np.float32)
        # Teacher comparison (optional)
        if teacher is not None:
            tp = teacher.predict(xgb.DMatrix(p[teacher_features].to_numpy(np.float32),
                                            feature_names=teacher_features)).astype(np.float32)
        else:
            tp = np.zeros(len(p), np.float32)
        for dst, a in zip(parts[9:], (won, hpfrac, maxhp, group[keep], tp)): dst.append(a)
        kept += int(keep.sum())
    if ci % 50 == 0:
        print(f"  scanned {seen:,}, kept {kept:,}", flush=True)
print(f"sampled {kept:,}/{seen:,} rows", flush=True)

data = [np.concatenate(p) for p in parts]
del parts; gc.collect()
(scalar, cards, relics, potions, encounter, mids, intents, mcont, mmask,
 won, hpfrac, maxhp, group, teacher_pred) = data
is_val = (mix64(group + np.uint64(0xd1b54a32d192ed03)) % np.uint64(10)) == 0
tr = np.flatnonzero(~is_val); va = np.flatnonzero(is_val)
print(f"fight-group split: train {len(tr):,}, validation {len(va):,}", flush=True)

scalar_mean = scalar[tr].mean(0, dtype=np.float64).astype(np.float32)
scalar_inv = 1 / np.maximum(scalar[tr].std(0, dtype=np.float64).astype(np.float32), 1e-6)
mon_train = mcont[tr][mmask[tr]]
mon_mean = mon_train.mean(0, dtype=np.float64).astype(np.float32)
mon_inv = 1 / np.maximum(mon_train.std(0, dtype=np.float64).astype(np.float32), 1e-6)
scalar -= scalar_mean; scalar *= scalar_inv
mcont -= mon_mean; mcont *= mon_inv
mcont *= mmask[..., None]


class EntityCombatNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.card = nn.Parameter(torch.randn(4, 371, 32) * 0.02)
        self.relic = nn.Parameter(torch.randn(128, 16) * 0.02)
        self.potion = nn.Parameter(torch.randn(44, 8) * 0.02)
        self.encounter = nn.Embedding(128, 16)
        self.monster_id = nn.Embedding(256, 16)
        self.intent = nn.Embedding(32, 8)
        self.monster = nn.Sequential(nn.Linear(31, 32), nn.ReLU())
        self.trunk = nn.Sequential(nn.Linear(296, 128), nn.ReLU(),
                                   nn.Linear(128, 64), nn.ReLU())
        self.win = nn.Linear(64, 1)
        self.hp = nn.Linear(64, 1)

    def forward(self, scalar, cards, relics, potions, encounter,
                mids, intents, mcont, mmask):
        card = torch.einsum("bzc,zce->bze", cards, self.card).flatten(1)
        relic = relics @ self.relic
        potion = potions @ self.potion
        enc = self.encounter(encounter)
        mon = torch.cat((self.monster_id(mids), self.intent(intents), mcont), -1)
        mon = self.monster(mon) * mmask.unsqueeze(-1)
        mon_sum = mon.sum(1)
        mon_max = mon.masked_fill(~mmask.unsqueeze(-1), -1e9).max(1).values
        mon_max = torch.where(mmask.any(1, keepdim=True), mon_max, torch.zeros_like(mon_max))
        z = torch.cat((scalar, card, relic, potion, enc, mon_sum, mon_max), 1)
        z = self.trunk(z)
        return self.win(z).squeeze(1), self.hp(z).squeeze(1)


arrays = [scalar, cards, relics, potions, encounter, mids, intents, mcont, mmask,
          won, hpfrac, maxhp, teacher_pred]
tensors = [torch.from_numpy(a) for a in arrays]
model = EntityCombatNet().to(DEVICE)
opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
bce = nn.BCEWithLogitsLoss(reduction="none")


def batch_forward(ids):
    s, c, r, p, e, mi, it, mc, mm = [x[ids].to(DEVICE) for x in tensors[:9]]
    return model(s, c.float(), r.float(), p.float(), e.long(), mi.long(),
                 it.long(), mc, mm)


@torch.no_grad()
def evaluate(indices):
    model.eval(); ps, hs = [], []
    for lo in range(0, len(indices), BATCH):
        ids = torch.from_numpy(indices[lo:lo+BATCH])
        wl, hl = batch_forward(ids)
        ps.append(torch.sigmoid(wl).cpu()); hs.append(torch.sigmoid(hl).cpu())
    p = torch.cat(ps).numpy(); h = torch.cat(hs).numpy()
    yw = won[indices]; yh = hpfrac[indices]
    pred_end = p * h * maxhp[indices]
    actual_end = yw * yh * maxhp[indices]
    win_brier = float(np.mean((p-yw)**2))
    win_acc = float(np.mean((p >= .5) == (yw >= .5)))
    hp_mae = float(np.mean(np.abs(h[yw > .5]-yh[yw > .5])))
    end_rmse = float(np.sqrt(np.mean((pred_end-actual_end)**2)))
    teacher_rmse = float(np.sqrt(np.mean((teacher_pred[indices]-actual_end)**2))) if teacher is not None else 0.0
    utility = p * (WIN_BONUS + h * maxhp[indices])
    return dict(brier=win_brier, acc=win_acc, hp_mae=hp_mae,
                end_rmse=end_rmse, teacher_rmse=teacher_rmse), p, h, utility


best = None; best_metric = float("inf"); stale = 0
rng = np.random.default_rng(0)
print(f"training entity model on {THREADS} CPU threads ...", flush=True)
for epoch in range(1, EPOCHS+1):
    model.train(); order = rng.permutation(tr); losses = []
    for lo in range(0, len(order), BATCH):
        ids_np = order[lo:lo+BATCH]
        ids = torch.from_numpy(ids_np)
        win_logit, hp_logit = batch_forward(ids)
        yw = tensors[9][ids].to(DEVICE); yh = tensors[10][ids].to(DEVICE)
        p = torch.sigmoid(win_logit); h = torch.sigmoid(hp_logit)
        loss_win = bce(win_logit, yw).mean()
        mask = yw > .5
        loss_hp = nn.functional.smooth_l1_loss(h[mask], yh[mask]) if mask.any() else h.sum()*0
        loss_joint = nn.functional.mse_loss(p*h, yw*yh)
        loss = loss_win + 2.0*loss_hp + loss_joint
        opt.zero_grad(set_to_none=True); loss.backward(); opt.step()
        losses.append(float(loss.detach()))
    metrics, _, _, _ = evaluate(va)
    print(f"epoch {epoch:02d} loss={np.mean(losses):.5f} "
          f"val brier={metrics['brier']:.4f} acc={metrics['acc']:.3f} "
          f"hpMAE={metrics['hp_mae']:.4f} endRMSE={metrics['end_rmse']:.3f} "
          f"rmse={metrics['end_rmse']:.3f}"
          + (f" teacherRMSE={metrics['teacher_rmse']:.3f}" if teacher is not None else ""), flush=True)
    if metrics["end_rmse"] < best_metric - .02:
        best_metric = metrics["end_rmse"]; best = copy.deepcopy(model.state_dict()); stale = 0
    else:
        stale += 1
        if stale >= 3: break
model.load_state_dict(best)
metrics, vp, vh, vu = evaluate(va)
print("best fight-group metrics:", metrics, flush=True)
torch.save(dict(state_dict=model.state_dict(), scalar_cols=scalar_cols,
                scalar_mean=scalar_mean, scalar_inv=scalar_inv,
                mon_mean=mon_mean, mon_inv=mon_inv, win_bonus=WIN_BONUS), OUT + ".pt")


def write_values(f, token, value):
    a = value.detach().cpu().numpy() if torch.is_tensor(value) else np.asarray(value)
    f.write(token)
    for v in a.astype(np.float32).ravel(): f.write(f" {float(v):.9g}")
    f.write("\n")


sd = model.state_dict()
with open(OUT, "w") as f:
    f.write("combat_entity_v1\n")
    f.write(f"win_bonus {WIN_BONUS:.9g}\n")
    f.write(f"nscalar {len(scalar_cols)}\n")
    for name in scalar_cols: f.write(f"scalar {name}\n")
    write_values(f, "scalar_mean", scalar_mean); write_values(f, "scalar_inv", scalar_inv)
    write_values(f, "mon_mean", mon_mean); write_values(f, "mon_inv", mon_inv)
    for token in ("card", "relic", "potion", "encounter.weight", "monster_id.weight",
                  "intent.weight", "monster.0.weight", "monster.0.bias",
                  "trunk.0.weight", "trunk.0.bias", "trunk.2.weight", "trunk.2.bias",
                  "win.weight", "win.bias", "hp.weight", "hp.bias"):
        write_values(f, token.replace(".", "_"), sd[token])
print(f"wrote {OUT} and {OUT}.pt", flush=True)

# Canonical parity rows with both heads and the derived scalar utility.
sample = pd.read_csv(CSV, dtype=dtypes, nrows=200)
sa = list(extract(sample))
sa[0][:] = (sa[0] - scalar_mean) * scalar_inv
sa[7][:] = (sa[7] - mon_mean) * mon_inv
sa[7] *= sa[8][..., None]
with torch.no_grad():
    model = model.cpu()
    args = [torch.from_numpy(x) for x in sa]
    wl, hl = model(args[0], args[1].float(), args[2].float(), args[3].float(),
                   args[4].long(), args[5].long(), args[6].long(), args[7], args[8])
    pp = torch.sigmoid(wl).numpy(); hh = torch.sigmoid(hl).numpy()
pred = pp * (WIN_BONUS + hh * sample["maxHp"].to_numpy(np.float32))
vout = sample[canonical].copy(); vout["pyWin"] = pp; vout["pyHpFrac"] = hh; vout["pyPred"] = pred
vout.to_csv(VAL, index=False)
print(f"wrote {VAL}: {len(vout)} parity rows", flush=True)
