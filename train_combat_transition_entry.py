#!/usr/bin/env python3
"""Train a no-peek, battle-entry combat transition model.

One row per completed fight is used: the first recorded combat decision.  Card
zones are collapsed into an orderless whole-deck bag, and all live-combat
features (opening hand, draw order, monster state/intent, turn, energy, block,
and temporary buffs) are removed.  The sole fight-specific feature is the
encounter ID.  Targets are P(win) and E[end HP / max HP | win].

The exported file deliberately uses the existing ``combat_entity_v1`` format,
so the checkpoint evaluator can load it without any C++ changes.  Its zone
embeddings are tied at export time and every monster path is zeroed, making
inference obey the same no-peek feature contract.
"""
import copy
import glob
import os
import sys

import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import GroupShuffleSplit
from torch import nn


PATTERN = sys.argv[1] if len(sys.argv) > 1 else "selfplay/cbuffer/iter_*.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "selfplay/models/v_combat_transition_entry.txt"
VAL = sys.argv[3] if len(sys.argv) > 3 else OUT.replace(".txt", "_val.csv")
EPOCHS = int(os.environ.get("ENTRY_EPOCHS", "40"))
BATCH = int(os.environ.get("ENTRY_BATCH", "2048"))
THREADS = int(os.environ.get("OMP_NUM_THREADS", "12"))
torch.manual_seed(0)
torch.set_num_threads(THREADS)
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

FILES = sorted(glob.glob(PATTERN))
if not FILES:
    raise SystemExit(f"no combat CSVs match {PATTERN!r}")

ZONES = [[f"{p}{i}" for i in range(371)] for p in ("hd", "dr", "ds", "ex")]
RELICS = [f"r{i}" for i in range(128)]
POTIONS = [f"pot{i}" for i in range(44)]
# These are persistent run-state counters that can affect the next fight.  No
# opening-hand, monster, or already-in-combat field is admitted.
SCALARS = ["ascension", "curHp", "maxHp", "happyFlowerCtr", "incenseBurnerCtr",
           "inkBottleCtr", "inserterCtr", "nunchakuCtr", "penNibCtr",
           "sundialCtr", "panacheCtr"]


def append_first_rows(path, parts):
    use = ["seed", "fightIdx", "encounter", "won", "endHp"] + SCALARS + RELICS + POTIONS
    use += [c for z in ZONES for c in z]
    dtypes = {c: np.int16 for c in use}; dtypes["seed"] = np.int32
    last_key = None
    # A wide row has ~1,700 columns; keep parse chunks deliberately small so
    # this can train from every historical buffer without a multi-GB peak.
    for d in pd.read_csv(path, usecols=use, chunksize=512,
                         dtype=dtypes):
        keys = d["seed"].astype(np.int64) * 1000 + d["fightIdx"].astype(np.int64)
        take = ~keys.duplicated()
        if last_key is not None:
            take.iloc[0] = keys.iloc[0] != last_key
        d = d.loc[take]
        parts[0].append(d["seed"].to_numpy(np.int32))
        parts[1].append(d[SCALARS].to_numpy(np.float32))
        parts[2].append(sum((d[z].to_numpy(np.float32) for z in ZONES)))
        parts[3].append(d[RELICS].to_numpy(np.float32))
        parts[4].append(d[POTIONS].to_numpy(np.float32))
        parts[5].append(d["encounter"].to_numpy(np.int16))
        parts[6].append(d["won"].to_numpy(np.float32))
        parts[7].append(d["endHp"].to_numpy(np.float32))
        last_key = int(keys.iloc[-1])


print("reading one no-peek entry state per fight ...", flush=True)
parts = [[] for _ in range(8)]
for file_idx, path in enumerate(FILES, 1):
    print(f"  [{file_idx}/{len(FILES)}] {path}", flush=True)
    append_first_rows(path, parts)
seed, scalar, deck, relics, potions, encounter, won, endhp = [np.concatenate(x) for x in parts]
del parts
print(f"{len(seed):,} fights from {len(FILES)} buffers", flush=True)

seed = seed.astype(np.int64)
encounter = np.clip(encounter.astype(np.int64), 0, 127)
maxhp = np.maximum(scalar[:, SCALARS.index("maxHp")], 1.0)
hpfrac = np.clip(endhp / maxhp, 0, 1)

tr, va = next(GroupShuffleSplit(1, test_size=.20, random_state=0)
              .split(scalar, won, groups=seed))
mean = scalar[tr].mean(0).astype(np.float32)
inv = 1 / np.maximum(scalar[tr].std(0).astype(np.float32), 1e-6)
scalar = (scalar - mean) * inv


class EntryNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.card = nn.Parameter(torch.randn(371, 16) * .02)
        self.relic = nn.Parameter(torch.randn(128, 8) * .02)
        self.potion = nn.Parameter(torch.randn(44, 4) * .02)
        self.encounter = nn.Embedding(128, 8)
        self.trunk = nn.Sequential(nn.Linear(len(SCALARS) + 16 + 8 + 4 + 8, 128), nn.ReLU(),
                                   nn.Linear(128, 64), nn.ReLU())
        self.win = nn.Linear(64, 1)
        self.hp = nn.Linear(64, 1)

    def forward(self, s, d, r, p, e):
        z = torch.cat((s, d @ self.card, r @ self.relic, p @ self.potion,
                       self.encounter(e)), 1)
        z = self.trunk(z)
        return self.win(z).squeeze(1), self.hp(z).squeeze(1)


tensors = [torch.from_numpy(x) for x in (scalar, deck, relics, potions, encounter, won, hpfrac, maxhp)]
model = EntryNet().to(DEVICE)
opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
rng = np.random.default_rng(0)


def forward(ids):
    s, d, r, p, e = (x[ids].to(DEVICE) for x in tensors[:5])
    return model(s, d, r, p, e)


@torch.no_grad()
def evaluate(ids):
    model.eval(); pp = []; hh = []
    for lo in range(0, len(ids), BATCH):
        wl, hl = forward(torch.from_numpy(ids[lo:lo+BATCH]))
        pp.append(torch.sigmoid(wl)); hh.append(torch.sigmoid(hl))
    p = torch.cat(pp).cpu().numpy(); h = torch.cat(hh).cpu().numpy()
    yw, yh, mh = won[ids], hpfrac[ids], maxhp[ids]
    return {"win_brier": float(np.mean((p-yw)**2)),
            "win_accuracy": float(np.mean((p >= .5) == (yw >= .5))),
            "hp_mae_if_win": float(np.mean(np.abs(h[yw > .5]-yh[yw > .5]))),
            "end_hp_rmse": float(np.sqrt(np.mean((p*h*mh-yw*yh*mh)**2)))}, p, h


best, best_rmse, stale = None, float("inf"), 0
for epoch in range(1, EPOCHS + 1):
    model.train(); losses = []
    # One permutation per epoch, kept outside the batch loop to avoid resampling rows.
    order = rng.permutation(tr)
    for lo in range(0, len(order), BATCH):
        ids = torch.from_numpy(order[lo:lo+BATCH]); wl, hl = forward(ids)
        yw, yh = tensors[5][ids].to(DEVICE), tensors[6][ids].to(DEVICE)
        p, h = torch.sigmoid(wl), torch.sigmoid(hl)
        hp_loss = nn.functional.smooth_l1_loss(h[yw > .5], yh[yw > .5]) if (yw > .5).any() else h.sum()*0
        loss = nn.functional.binary_cross_entropy_with_logits(wl, yw) + 2*hp_loss + nn.functional.mse_loss(p*h, yw*yh)
        opt.zero_grad(set_to_none=True); loss.backward(); opt.step(); losses.append(float(loss.detach()))
    m, _, _ = evaluate(va)
    print(f"epoch {epoch:02d} loss={np.mean(losses):.4f} val={m}", flush=True)
    if m["end_hp_rmse"] < best_rmse - .005:
        best, best_rmse, stale = copy.deepcopy(model.state_dict()), m["end_hp_rmse"], 0
    else:
        stale += 1
        if stale >= 5: break
model.load_state_dict(best)
metrics, p, h = evaluate(va)
print("best validation:", metrics, flush=True)


def write_vec(f, token, x):
    f.write(token + "".join(f" {float(v):.9g}" for v in x.detach().cpu().numpy().astype(np.float32).ravel()) + "\n")


# Format-compatible export.  The loader expects 64 scalar slots and the older
# entity trunk layout; copy our learned weights into the corresponding columns
# and make every excluded feature path identically zero.
canonical = list(pd.read_csv(FILES[0], nrows=0).columns)
old_scalars = [c for c in canonical if c not in {"seed", "fightIdx", "won", "endHp", "encounter"}
               and c not in set(RELICS + POTIONS + [q for z in ZONES for q in z])
               and not (c.startswith("m") and any(c.startswith(f"m{i}") for i in range(5)))]
assert len(old_scalars) == 64
sd = model.state_dict()
with open(OUT, "w") as f:
    f.write("combat_entity_v1\nwin_bonus 50\nnscalar 64\n")
    for name in old_scalars: f.write(f"scalar {name}\n")
    export_mean = np.zeros(64, np.float32); export_inv = np.zeros(64, np.float32)
    for i, name in enumerate(SCALARS):
        j = old_scalars.index(name); export_mean[j] = mean[i]; export_inv[j] = inv[i]
    write_vec(f, "scalar_mean", torch.from_numpy(export_mean)); write_vec(f, "scalar_inv", torch.from_numpy(export_inv))
    write_vec(f, "mon_mean", torch.zeros(7)); write_vec(f, "mon_inv", torch.zeros(7))
    # Same card embedding in all four zones => deck bag, independent of opening hand/draw order.
    write_vec(f, "card", sd["card"].unsqueeze(0).repeat(4, 1, 1))
    write_vec(f, "relic", sd["relic"]); write_vec(f, "potion", sd["potion"]); write_vec(f, "encounter_weight", sd["encounter.weight"])
    write_vec(f, "monster_id_weight", torch.zeros(256, 12)); write_vec(f, "intent_weight", torch.zeros(32, 4))
    write_vec(f, "monster_0_weight", torch.zeros(32, 23)); write_vec(f, "monster_0_bias", torch.zeros(32))
    # Existing entity trunk sees [64 scalar, 64 cards, 8 relic, 4 potion, 8 encounter, 32 monster sum, 32 monster max].
    w = torch.zeros(128, 212)
    for source, name in enumerate(SCALARS):
        w[:, old_scalars.index(name)] = sd["trunk.0.weight"][:, source]
    w[:, 64:80] = sd["trunk.0.weight"][:, len(SCALARS):len(SCALARS)+16]
    w[:, 128:136] = sd["trunk.0.weight"][:, len(SCALARS)+16:len(SCALARS)+24]
    w[:, 136:140] = sd["trunk.0.weight"][:, len(SCALARS)+24:len(SCALARS)+28]
    w[:, 140:148] = sd["trunk.0.weight"][:, len(SCALARS)+28:len(SCALARS)+36]
    write_vec(f, "trunk_0_weight", w); write_vec(f, "trunk_0_bias", sd["trunk.0.bias"])
    write_vec(f, "trunk_2_weight", sd["trunk.2.weight"]); write_vec(f, "trunk_2_bias", sd["trunk.2.bias"])
    write_vec(f, "win_weight", sd["win.weight"]); write_vec(f, "win_bias", sd["win.bias"])
    write_vec(f, "hp_weight", sd["hp.weight"]); write_vec(f, "hp_bias", sd["hp.bias"])

torch.save({"state_dict": sd, "scalars": SCALARS, "scalar_mean": mean, "scalar_inv": inv,
            "metrics": metrics, "contract": "pre-fight state + encounter only"}, OUT + ".pt")
pd.DataFrame({"seed": seed[va], "encounter": encounter[va], "won": won[va], "endHp": endhp[va],
              "pWin": p, "pEndHpFracIfWin": h}).to_csv(VAL, index=False)
print(f"wrote {OUT}, {OUT}.pt, and {VAL}", flush=True)
