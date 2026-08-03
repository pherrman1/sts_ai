#!/usr/bin/env python3
"""Train C_psi: the no-peek pre-combat outcome model (plan 5.4.2, spec A.7-A.8).

C_psi(pre-combat run state: deck, relics, potions, HP, encounter, ascension)
  -> P(death), P(win), E[HP/maxHp | win], 11 HP quantiles (win-conditional),
     P(use potion i) for i in 0..43, expected turns remaining.

Data: the distributional distgen CSV (build/vdist.csv).  Per fight we keep the
FIRST row (verified: every (seed, fightIdx) group's first row has turn==0 in
the current file).  The no-peek entry feature set is copied verbatim from
train_combat_transition_entry.py: the 11 persistent scalars (ascension,
curHp, maxHp, 7 counters), the whole-deck bag = hd+dr+ds+ex zone counts
summed (orderless, so no opening-hand/draw-order information), relic counts
r0-127, potion counts pot0-43, and the encounter id.  No hand, draw-order,
monster, intent, turn, energy, block or temporary-buff feature is admitted.

Labels (all from the distgen suffix):
  won (0/1), endHp (scaled by maxHp), endTurn -> turns_remaining =
  max(0, endTurn - turn) (turn of the entry row is 0, so = endTurn),
  pUsed0..43 (potion type consumed at some point after this snapshot).

Loss = the documented dist-trainer mix + the entry trainer's joint term:
  win BCE + death BCE (y_death = 1 - won)
  + 2.0 * smoothL1(sigmoid(hp), hp_frac | win)         (entry trainer)
  + 1.0 * MSE(sigmoid(win)*sigmoid(hp), won*hp_frac)   (entry trainer joint)
  + 2.0 * pinball(quantiles, hp_frac | win)            (tau = .05..95, 11)
  + 0.5 * potion BCE (masked to fights with >=1 consumed potion, mirroring
                      train_combat_dist.py)            (dist trainer)
  + 0.3 * smoothL1(turns, log1p(turns_remaining))      (dist trainer)
The win BCE is counted once (both trainers include it).

Architecture: the EntityEncoder/CombatDistNet token design from
train_combat_dist.py (dim 128, hidden 256, 4 heads, 2 transformer layers,
attention pooling), with the no-peek input enforced structurally -- the
deviations are intentional:
  * scalar_encoder is Linear(11 -> 128) instead of Linear(64 -> 128): the 11
    persistent scalars are the only scalars used (the dist net's 64 include
    in-fight counters we deliberately exclude).
  * one whole-deck bag token instead of 4 zone tokens with positional
    encoding (zone_pos and the in-fight zone split are dropped).
  * monster-id/intent/continuous encoders and monster tokens are OMITTED
    (stronger than zeroing at export: the features never enter the model).
Heads (mirror CombatDistNet shapes): death, win, hp (sigmoided), 11 raw
quantiles, 44 potion logits, turns (log1p scale).

Export: OUT.txt is a self-contained text format ``combat_cpsi_v1`` documented
below (no C++ loader yet -- it can come later).  OUT.pt holds the state dict +
normalization + metrics; OUT_val.csv holds the held-out per-fight predictions.

combat_cpsi_v1 text format (one vector per line, row-major floats):
  combat_cpsi_v1
  win_bonus <float>
  nscalar <K=11>
  scalar <name>            x K, in the order used here
  dim <128>  hidden <256>  heads <4>  layers <L>  quantiles <11>
  scalar_mean <K>  scalar_inv <K>
  scalar_weight <K*dim>  scalar_bias <dim>
  card_embed <371*dim>
  relic_embed <128*64>  potion_embed <44*32>  encounter_embed <128*32>
  per layer l in 0..L-1:
    layer_l_qkv_weight <3*dim*dim>  layer_l_qkv_bias <3*dim>
    layer_l_proj_weight <dim*dim>  layer_l_proj_bias <dim>
    layer_l_ln1_weight <dim>  layer_l_ln1_bias <dim>
    layer_l_ln2_weight <dim>  layer_l_ln2_bias <dim>
    layer_l_ffn1_weight <hidden*dim>  layer_l_ffn1_bias <hidden>
    layer_l_ffn2_weight <dim*hidden>  layer_l_ffn2_bias <dim>
  pool_weight <dim>  pool_bias <1>
  heads, each *_weight <out*dim> + *_bias <out>:
    death  win  hp  quantile(11)  potion(44)  turns

Env: STRAT_DEVICE (cuda default, falls back to cpu; "device:" line printed),
STRAT_EPOCHS (40), CPSI_BATCH (2048), CPSI_LR (1e-3), CPSI_WD (1e-5),
CPSI_CHUNK_ROWS (1024), CPSI_NQUANTILE (11), CPSI_WIN_BONUS (50),
OMP_NUM_THREADS (12).  The 10.3 GB CSV is read in chunks; only the entry row
per (seed, fightIdx) is kept and compacted into float32 arrays.
"""
import copy
import os
import sys

import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import GroupShuffleSplit
from torch import nn

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/vdist.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "selfplay/models/v_combat_cpsi"
EPOCHS = int(os.environ.get("STRAT_EPOCHS", os.environ.get("CPSI_EPOCHS", "40")))
BATCH = int(os.environ.get("CPSI_BATCH", "2048"))
THREADS = int(os.environ.get("OMP_NUM_THREADS", "12"))
CHUNK = int(os.environ.get("CPSI_CHUNK_ROWS", "1024"))
LR = float(os.environ.get("CPSI_LR", "1e-3"))
WD = float(os.environ.get("CPSI_WD", "1e-5"))
NQUANTILE = int(os.environ.get("CPSI_NQUANTILE", "11"))
WIN_BONUS = float(os.environ.get("CPSI_WIN_BONUS", "50"))
ENTITY_DIM = 128
HIDDEN_DIM = 256
NUM_HEADS = 4
NUM_LAYERS = 2
NCARD = 371
NRELIC = 128
NPOTION = 44
NENCOUNTER = 128

DEVICE = os.environ.get("STRAT_DEVICE", "cuda")
if DEVICE == "cuda" and torch.cuda.is_available():
    print(f"device: cuda ({torch.cuda.get_device_name(0)})", flush=True)
else:
    DEVICE = "cpu"
    print("device: cpu", flush=True)

torch.manual_seed(0)
torch.set_num_threads(THREADS)

ZONES = [[f"{p}{i}" for i in range(NCARD)] for p in ("hd", "dr", "ds", "ex")]
RELICS = [f"r{i}" for i in range(NRELIC)]
POTIONS = [f"pot{i}" for i in range(NPOTION)]
# Persistent run-state counters copied from train_combat_transition_entry.py.
SCALARS = ["ascension", "curHp", "maxHp", "happyFlowerCtr", "incenseBurnerCtr",
           "inkBottleCtr", "inserterCtr", "nunchakuCtr", "penNibCtr",
           "sundialCtr", "panacheCtr"]
POTION_USED = [f"pUsed{i}" for i in range(NPOTION)]

header = list(pd.read_csv(CSV, nrows=0).columns)
LABEL_COLS = ("seed", "fightIdx", "won", "endHp", "endTurn", "potionsConsumed")
canonical = [c for c in header if c not in LABEL_COLS and c not in POTION_USED]
assert len(canonical) == 1766, f"expected the 1766 canonical combat vector, got {len(canonical)}"
for col in ["encounter", "turn"] + SCALARS + RELICS + POTIONS + \
        [c for z in ZONES for c in z] + POTION_USED:
    assert col in header, f"required column {col!r} missing from {CSV} header"


def append_first_rows(path, parts):
    use = (["seed", "fightIdx", "turn", "encounter", "won", "endHp", "endTurn"]
           + SCALARS + RELICS + POTIONS + POTION_USED + [c for z in ZONES for c in z])
    dtypes = {c: np.int16 for c in use}
    dtypes["seed"] = np.int32
    last_key = None
    # First row per (seed, fightIdx) = the fight's entry snapshot.  Wide rows
    # (~1,700 used columns) keep parse chunks small to bound peak memory.
    for d in pd.read_csv(path, usecols=use, chunksize=CHUNK, dtype=dtypes):
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
        parts[8].append(d["turn"].to_numpy(np.float32))
        parts[9].append(d["endTurn"].to_numpy(np.float32))
        parts[10].append(d[POTION_USED].to_numpy(np.float32))
        parts[11].append(d["fightIdx"].to_numpy(np.int16))
        last_key = int(keys.iloc[-1])


print(f"reading one no-peek entry state per fight from {CSV} ...", flush=True)
parts = [[] for _ in range(12)]
append_first_rows(CSV, parts)
seed, scalar, deck, relics, potions, encounter, won, endhp, turn, endturn, pused, fightidx = \
    [np.concatenate(x) for x in parts]
del parts
print(f"{len(seed):,} fights", flush=True)

seed = seed.astype(np.int64)
fightidx = fightidx.astype(np.int64)
encounter = np.clip(encounter.astype(np.int64), 0, NENCOUNTER - 1)
maxhp = np.maximum(scalar[:, SCALARS.index("maxHp")], 1.0)
hpfrac = np.clip(endhp / maxhp, 0, 1)
turns_rem = np.maximum(0.0, endturn - turn).astype(np.float32)
y_death = (won <= 0).astype(np.float32)

# Split by fight (one row per group), 80/20.  seed*1000+fightIdx is
# collision-free for this dataset (max fightIdx 33, max seed 73396).
groups = seed * 1000 + fightidx
tr, va = next(GroupShuffleSplit(1, test_size=.20, random_state=0)
              .split(scalar, groups=groups))
mean = scalar[tr].mean(0).astype(np.float32)
inv = 1 / np.maximum(scalar[tr].std(0).astype(np.float32), 1e-6)
scalar = (scalar - mean) * inv
print(f"[split] train={len(tr):,} val={len(va):,} fights", flush=True)


class TransformerLayer(nn.Module):
    def __init__(self, dim, hidden_dim, num_heads):
        super().__init__()
        self.attn = nn.MultiheadAttention(dim, num_heads, batch_first=True)
        self.ln1 = nn.LayerNorm(dim)
        self.ffn = nn.Sequential(nn.Linear(dim, hidden_dim), nn.GELU(),
                                 nn.Linear(hidden_dim, dim))
        self.ln2 = nn.LayerNorm(dim)

    def forward(self, x):
        a, _ = self.attn(x, x, x)
        x = self.ln1(x + a)
        return self.ln2(x + self.ffn(x))


class CPSINet(nn.Module):
    """No-peek token encoder: 5 tokens (scalar, deck bag, relics, potions,
    encounter), transformer, attention pooling, multi-head outputs."""

    def __init__(self, dim=ENTITY_DIM, hidden_dim=HIDDEN_DIM,
                 num_heads=NUM_HEADS, num_layers=NUM_LAYERS):
        super().__init__()
        self.card_embed = nn.Parameter(torch.randn(NCARD, dim) * .02)
        self.relic_embed = nn.Parameter(torch.randn(NRELIC, 64) * .02)
        self.relic_proj = nn.Linear(64, dim) if 64 != dim else nn.Identity()
        self.potion_embed = nn.Parameter(torch.randn(NPOTION, 32) * .02)
        self.potion_proj = nn.Linear(32, dim) if 32 != dim else nn.Identity()
        self.enc_embed = nn.Embedding(NENCOUNTER, 32)
        self.enc_proj = nn.Linear(32, dim) if 32 != dim else nn.Identity()
        self.scalar_encoder = nn.Sequential(nn.Linear(len(SCALARS), dim), nn.ReLU())
        self.layers = nn.ModuleList([TransformerLayer(dim, hidden_dim, num_heads)
                                     for _ in range(num_layers)])
        self.pool_attn = nn.Linear(dim, 1)
        self.death_head = nn.Linear(dim, 1)
        self.win_head = nn.Linear(dim, 1)
        self.hp_head = nn.Linear(dim, 1)
        self.quantile_head = nn.Linear(dim, NQUANTILE)
        self.potion_head = nn.Linear(dim, NPOTION)
        self.turns_head = nn.Linear(dim, 1)

    def forward(self, s, d, r, p, e):
        tokens = [self.scalar_encoder(s).unsqueeze(1),
                  torch.einsum("bc,ce->be", d, self.card_embed).unsqueeze(1),
                  self.relic_proj(torch.einsum("br,re->be", r, self.relic_embed)).unsqueeze(1),
                  self.potion_proj(torch.einsum("bp,pe->be", p, self.potion_embed)).unsqueeze(1),
                  self.enc_proj(self.enc_embed(e.long())).unsqueeze(1)]
        x = torch.cat(tokens, 1)
        for layer in self.layers:
            x = layer(x)
        attn = self.pool_attn(x).squeeze(-1)
        pooled = (torch.softmax(attn, -1).unsqueeze(-1) * x).sum(1)
        return {"death": self.death_head(pooled).squeeze(-1),
                "win": self.win_head(pooled).squeeze(-1),
                "hp": self.hp_head(pooled).squeeze(-1),
                "quantiles": self.quantile_head(pooled),
                "potion_prob": self.potion_head(pooled),
                "turns": self.turns_head(pooled).squeeze(-1)}


tensors = [torch.from_numpy(x) for x in
           (scalar, deck, relics, potions, encounter, won, hpfrac, maxhp,
            turns_rem, pused, y_death)]
model = CPSINet().to(DEVICE)
print(f"[model] {sum(p.numel() for p in model.parameters()):,} params", flush=True)
opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WD)
rng = np.random.default_rng(0)


def forward(ids):
    s, d, r, p, e = (x[ids].to(DEVICE) for x in tensors[:5])
    return model(s, d, r, p, e)


def compute_loss(preds, ids):
    yw = tensors[5][ids].to(DEVICE)
    yhf = tensors[6][ids].to(DEVICE)
    tr = tensors[8][ids].to(DEVICE)
    pu = tensors[9][ids].to(DEVICE)
    losses = {}
    losses["win"] = nn.functional.binary_cross_entropy_with_logits(preds["win"], yw)
    losses["death"] = nn.functional.binary_cross_entropy_with_logits(
        preds["death"], tensors[10][ids].to(DEVICE))
    p = torch.sigmoid(preds["win"])
    h = torch.sigmoid(preds["hp"])
    hmask = yw > .5
    if hmask.any():
        losses["hp"] = nn.functional.smooth_l1_loss(h[hmask], yhf[hmask])
    else:
        losses["hp"] = h.sum() * 0
    losses["joint"] = nn.functional.mse_loss(p * h, yw * yhf)
    tau = torch.linspace(.05, .95, NQUANTILE, device=DEVICE).view(1, -1)
    if hmask.any():
        diff = yhf[hmask].unsqueeze(-1) - preds["quantiles"][hmask]
        losses["quantile"] = (tau * diff.clamp(min=0) + (1 - tau) * (-diff).clamp(min=0)).mean()
    else:
        losses["quantile"] = torch.tensor(0.0, device=DEVICE)
    pmask = pu.sum(-1) > 0
    if pmask.any():
        losses["potion"] = nn.functional.binary_cross_entropy_with_logits(
            preds["potion_prob"][pmask], pu[pmask])
    else:
        losses["potion"] = 0.01 * preds["potion_prob"].abs().mean()
    losses["turns"] = nn.functional.smooth_l1_loss(preds["turns"], torch.log1p(tr))
    total = (losses["win"] + losses["death"] + 2.0 * losses["hp"] + losses["joint"]
             + 2.0 * losses["quantile"] + 0.5 * losses["potion"] + 0.3 * losses["turns"])
    return total, losses


@torch.no_grad()
def evaluate(ids):
    model.eval()
    pp, hh, dd, qq, pt, tt = [], [], [], [], [], []
    for lo in range(0, len(ids), BATCH):
        b = torch.from_numpy(ids[lo:lo + BATCH])
        out = forward(b)
        pp.append(torch.sigmoid(out["win"])); hh.append(torch.sigmoid(out["hp"]))
        dd.append(torch.sigmoid(out["death"]))
        qq.append(out["quantiles"]); pt.append(torch.sigmoid(out["potion_prob"]))
        tt.append(out["turns"])
    p = torch.cat(pp).cpu().numpy(); h = torch.cat(hh).cpu().numpy()
    d = torch.cat(dd).cpu().numpy(); q = torch.cat(qq).cpu().numpy()
    pu = torch.cat(pt).cpu().numpy(); t = torch.cat(tt).cpu().numpy()
    yw, yhf, mh, tr, yd, pused = (x[ids].numpy() for x in
                                  (tensors[5], tensors[6], tensors[7],
                                   tensors[8], tensors[10], tensors[9]))
    won_rows = yw > .5
    tau = np.linspace(.05, .95, NQUANTILE).reshape(1, -1)
    qd = yhf[won_rows, None] - q[won_rows]
    pinball = (tau * np.maximum(qd, 0) + (1 - tau) * np.maximum(-qd, 0)).mean() \
        if won_rows.any() else float("nan")
    pmask = pused.sum(-1) > 0
    if pmask.any():
        logit = np.log(pu[pmask] / (1 - pu[pmask] + 1e-9))
        pbce = -np.mean(pused[pmask] * logit - np.log1p(np.exp(logit)))
    else:
        pbce = float("nan")
    metrics = {"win_brier": float(np.mean((p - yw) ** 2)),
               "win_accuracy": float(np.mean((p >= .5) == (yw >= .5))),
               "death_brier": float(np.mean((d - yd) ** 2)),
               "hp_mae_if_win": float(np.mean(np.abs(h[won_rows] - yhf[won_rows]))
                                      if won_rows.any() else float("nan")),
               "end_hp_rmse": float(np.sqrt(np.mean((p * h * mh - yw * yhf * mh) ** 2))),
               "quantile_pinball": float(pinball),
               "potion_bce": float(pbce),
               "turns_mae": float(np.mean(np.abs(np.expm1(t) - tr)))}
    return metrics, p, h


best, best_val, stale = None, float("inf"), 0
for epoch in range(1, EPOCHS + 1):
    model.train(); losses = []
    order = rng.permutation(tr)
    for lo in range(0, len(order), BATCH):
        ids = torch.from_numpy(order[lo:lo + BATCH])
        total, _ = compute_loss(forward(ids), ids)
        opt.zero_grad(set_to_none=True); total.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step(); losses.append(float(total.detach()))
    m = evaluate(va)
    if epoch % 10 == 0 or epoch == EPOCHS:
        print(f"epoch {epoch:02d} loss={np.mean(losses):.4f} val={m[0]}", flush=True)
    if m[0]["end_hp_rmse"] < best_val - .005:
        best, best_val, stale = copy.deepcopy(model.state_dict()), m[0]["end_hp_rmse"], 0
    else:
        stale += 1
        if stale >= 5:
            break
model.load_state_dict(best)
metrics, p, h = evaluate(va)
print("best validation:", metrics, flush=True)


def write_vec(f, token, x):
    f.write(token + "".join(f" {float(v):.9g}"
                            for v in x.detach().cpu().numpy().astype(np.float32).ravel()) + "\n")


# Self-contained combat_cpsi_v1 text export (format documented in the header).
sd = model.state_dict()
with open(OUT + ".txt", "w") as f:
    f.write("combat_cpsi_v1\n")
    f.write(f"win_bonus {WIN_BONUS}\n")
    f.write(f"nscalar {len(SCALARS)}\n")
    for name in SCALARS:
        f.write(f"scalar {name}\n")
    f.write(f"dim {ENTITY_DIM} hidden {HIDDEN_DIM} heads {NUM_HEADS} "
            f"layers {len(model.layers)} quantiles {NQUANTILE}\n")
    write_vec(f, "scalar_mean", torch.from_numpy(mean))
    write_vec(f, "scalar_inv", torch.from_numpy(inv))
    write_vec(f, "scalar_weight", sd["scalar_encoder.0.weight"])
    write_vec(f, "scalar_bias", sd["scalar_encoder.0.bias"])
    write_vec(f, "card_embed", sd["card_embed"])
    write_vec(f, "relic_embed", sd["relic_embed"])
    write_vec(f, "potion_embed", sd["potion_embed"])
    write_vec(f, "encounter_embed", sd["enc_embed.weight"])
    for l, layer in enumerate(model.layers):
        pre = f"layers.{l}."
        write_vec(f, f"layer_{l}_qkv_weight", sd[pre + "attn.in_proj_weight"])
        write_vec(f, f"layer_{l}_qkv_bias", sd[pre + "attn.in_proj_bias"])
        write_vec(f, f"layer_{l}_proj_weight", sd[pre + "attn.out_proj.weight"])
        write_vec(f, f"layer_{l}_proj_bias", sd[pre + "attn.out_proj.bias"])
        write_vec(f, f"layer_{l}_ln1_weight", sd[pre + "ln1.weight"])
        write_vec(f, f"layer_{l}_ln1_bias", sd[pre + "ln1.bias"])
        write_vec(f, f"layer_{l}_ln2_weight", sd[pre + "ln2.weight"])
        write_vec(f, f"layer_{l}_ln2_bias", sd[pre + "ln2.bias"])
        write_vec(f, f"layer_{l}_ffn1_weight", sd[pre + "ffn.0.weight"])
        write_vec(f, f"layer_{l}_ffn1_bias", sd[pre + "ffn.0.bias"])
        write_vec(f, f"layer_{l}_ffn2_weight", sd[pre + "ffn.2.weight"])
        write_vec(f, f"layer_{l}_ffn2_bias", sd[pre + "ffn.2.bias"])
    write_vec(f, "pool_weight", sd["pool_attn.weight"])
    write_vec(f, "pool_bias", sd["pool_attn.bias"])
    for name in ("death", "win", "hp", "quantile", "potion", "turns"):
        write_vec(f, f"{name}_weight", sd[f"{name}_head.weight"])
        write_vec(f, f"{name}_bias", sd[f"{name}_head.bias"])

torch.save({"state_dict": sd, "scalars": SCALARS, "scalar_mean": mean, "scalar_inv": inv,
            "metrics": metrics, "contract": "no-peek pre-fight state + encounter",
            "nrows": len(seed), "win_bonus": WIN_BONUS}, OUT + ".pt")
pd.DataFrame({"seed": seed[va], "fightIdx": fightidx[va], "encounter": encounter[va],
              "won": won[va], "endHp": endhp[va], "pWin": p, "pEndHpFracIfWin": h}
             ).to_csv(OUT + "_val.csv", index=False)
print(f"wrote {OUT}.txt, {OUT}.pt, and {OUT}_val.csv", flush=True)
