#!/usr/bin/env python3
"""Train a shared-state entity policy prior from MCTS visit distributions.

The tree prior scores every (state, action) row independently.  This model first
encodes the combat state once, using learned embeddings for card zones, relics,
potions, encounters, monster identities and intents.  A small action encoder then
scores every legal edge by compatibility with that shared state representation.

Training uses a grouped cross-entropy loss against each decision's normalized
MCTS visits.  Sampling and validation splitting happen by whole fight, so adjacent
decisions from one trajectory cannot leak across train and validation.

Usage:
  train_policy_entity.py POLICY.csv[,POLICY2.csv,...] TREE_REFERENCE.json OUT.txt VAL.csv

TREE_REFERENCE may be "none".  When supplied, its predictions are measured on the
same held-out fights as the NN; it is never used as a training target.
"""
import copy
import gc
import math
import os
import sys

import numpy as np
import pandas as pd
import torch
from torch import nn

try:
    import xgboost as xgb
except ImportError:
    xgb = None


CSV_ARG = sys.argv[1] if len(sys.argv) > 1 else "selfplay/pbuffer/_train.csv"
CSVS = [p for p in CSV_ARG.split(",") if p]
CSV = CSVS[0]
TREE_REFERENCE = sys.argv[2] if len(sys.argv) > 2 else "none"
OUT = sys.argv[3] if len(sys.argv) > 3 else "build/policy_entity.txt"
VAL = sys.argv[4] if len(sys.argv) > 4 else "build/policy_entity_val.csv"

SAMPLE_MOD = max(1, int(os.environ.get("POLICY_ENTITY_SAMPLE_MOD", "2")))
EPOCHS = int(os.environ.get("POLICY_ENTITY_EPOCHS", "18"))
BATCH_DECISIONS = int(os.environ.get("POLICY_ENTITY_BATCH", "512"))
THREADS = int(os.environ.get("OMP_NUM_THREADS", "8"))
CHUNK = int(os.environ.get("POLICY_ENTITY_CHUNK_ROWS", "5000"))
MAX_ROWS = int(os.environ.get("POLICY_ENTITY_MAX_ROWS", "0"))
LABEL_SMOOTH = float(os.environ.get("POLICY_ENTITY_LABEL_SMOOTH", "0.01"))
DEVICE = os.environ.get("POLICY_ENTITY_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
torch.manual_seed(0)
torch.set_num_threads(THREADS)
if DEVICE.startswith("cuda"):
    # Leave headroom for the desktop/display and other GPU work.  The model is
    # tiny; this guards against the CSV-side tensors accidentally filling VRAM.
    torch.cuda.set_per_process_memory_fraction(
        float(os.environ.get("POLICY_ENTITY_GPU_FRACTION", "0.70")))

KEYS = ("seed", "fightIdx", "decIdx", "visit", "total")
ACTION_NAMES = [
    "aIsCard", "aIsPotion", "aIsEndTurn", "aIsSelect",
    "aCardId", "aCardCost", "aCardUpg", "aCardAtk", "aCardSkl", "aCardPow",
    "aTargetsEnemy", "aTargetHp", "aPlayOrder", "aObtainWeight",
]
ACTION_SCALARS = [c for c in ACTION_NAMES if c != "aCardId"]


def mix64(x):
    x = np.asarray(x, dtype=np.uint64)
    x = x ^ (x >> np.uint64(30))
    x = x * np.uint64(0xBF58476D1CE4E5B9)
    x = x ^ (x >> np.uint64(27))
    x = x * np.uint64(0x94D049BB133111EB)
    return x ^ (x >> np.uint64(31))


header = list(pd.read_csv(CSV, nrows=0).columns)
for path in CSVS[1:]:
    if list(pd.read_csv(path, nrows=0).columns) != header:
        raise RuntimeError(f"policy feature schema differs in {path}")
missing = set(KEYS + tuple(ACTION_NAMES)) - set(header)
if missing:
    raise RuntimeError(f"policy CSV is missing columns: {sorted(missing)}")
canonical_policy = [c for c in header if c not in KEYS]
canonical_state = [c for c in canonical_policy if c not in ACTION_NAMES]

zones = [[f"{p}{i}" for i in range(371)] for p in ("hd", "dr", "ds", "ex")]
relic_cols = [f"r{i}" for i in range(128)]
potion_cols = [f"pot{i}" for i in range(44)]
monster_cols = [[f"m{i}{s}" for s in
                 ("Id", "Hp", "Block", "Str", "Intent", "Atk", "Vuln", "Weak", "Poison")]
                for i in range(5)]
monster_flat = [c for row in monster_cols for c in row]
entity_cols = set(relic_cols + potion_cols + monster_flat + ["encounter"]
                  + [c for z in zones for c in z])
scalar_cols = [c for c in canonical_state if c not in entity_cols]
if len(canonical_state) != 1766 or len(canonical_policy) != 1780 or len(scalar_cols) != 64:
    raise RuntimeError(
        f"unexpected feature layout: state={len(canonical_state)}, "
        f"policy={len(canonical_policy)}, scalar={len(scalar_cols)}")

dtypes = {c: (np.int32 if c in ("seed", "fightIdx", "decIdx") else np.int16)
          for c in header}

tree = None
tree_features = None
if TREE_REFERENCE.lower() != "none":
    if xgb is None:
        raise RuntimeError("xgboost is required when TREE_REFERENCE is supplied")
    tree = xgb.Booster()
    tree.load_model(TREE_REFERENCE)
    tree_features = list(tree.feature_names)


def extract_state(df):
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
        mcont[:, i] = df[[cols[j] for j in (1, 2, 3, 5, 6, 7, 8)]].to_numpy(np.float32)
        mmask[:, i] = hp > 0
    return scalar, cards, relics, potions, encounter, mids, intents, mcont, mmask


# Decision-level state arrays (0:9), then flat action scalars/card/visits,
# per-decision edge counts/fight ids, and optional reference logits.  Collapsing
# each complete decision while streaming avoids storing ~5.4 duplicate copies of
# the 1,766-wide state -- this is what makes a ten-iteration replay window fit.
parts = [[] for _ in range(15)]
seen = kept = decisions = 0


def consume_complete(df):
    global seen, kept, decisions
    if len(df) == 0:
        return
    seed = df["seed"].to_numpy(np.uint64)
    fight = df["fightIdx"].to_numpy(np.uint64)
    decision = df["decIdx"].to_numpy(np.uint64)
    fight_group = seed * np.uint64(1000) + fight
    decision_group = fight_group * np.uint64(10000) + decision
    keep = (mix64(fight_group + np.uint64(0x9E3779B97F4A7C15))
            % np.uint64(SAMPLE_MOD)) == 0
    seen += len(df)
    if not keep.any():
        return
    p = df.loc[keep]
    pg = decision_group[keep]
    pf = fight_group[keep]
    local_starts = np.r_[0, np.flatnonzero(np.diff(pg)) + 1]
    local_ends = np.r_[local_starts[1:], len(pg)]
    arrays = extract_state(p)
    for dst, a in zip(parts[:9], arrays):
        dst.append(a[local_starts].copy())
    parts[9].append(p[ACTION_SCALARS].to_numpy(np.float32))
    parts[10].append(p["aCardId"].to_numpy(np.int16))
    parts[11].append(p["visit"].to_numpy(np.float32))
    parts[12].append((local_ends-local_starts).astype(np.int16))
    parts[13].append(pf[local_starts].copy())
    if tree is not None:
        dm = xgb.DMatrix(p[tree_features].to_numpy(np.float32),
                         feature_names=tree_features)
        parts[14].append(tree.predict(dm).astype(np.float32))
    else:
        parts[14].append(np.zeros(len(p), np.float32))
    kept += len(p)
    decisions += len(local_starts)


print(f"streaming {len(CSVS)} replay file(s); keeping about 1/{SAMPLE_MOD} "
      "of whole fights ...", flush=True)
chunk_no = 0
for fi, path in enumerate(CSVS, 1):
    print(f"[{fi}/{len(CSVS)}] {path}", flush=True)
    carry = None
    for df in pd.read_csv(path, dtype=dtypes, chunksize=CHUNK,
                          nrows=MAX_ROWS or None):
        if carry is not None:
            df = pd.concat((carry, df), ignore_index=True)
        fg = (df["seed"].to_numpy(np.uint64) * np.uint64(1000)
              + df["fightIdx"].to_numpy(np.uint64))
        dg = fg * np.uint64(10000) + df["decIdx"].to_numpy(np.uint64)
        last_start = int(np.flatnonzero(dg != dg[-1])[-1] + 1) if np.any(dg != dg[-1]) else 0
        consume_complete(df.iloc[:last_start])
        carry = df.iloc[last_start:].copy()
        chunk_no += 1
        if chunk_no % 50 == 0:
            print(f"  scanned {seen:,}, kept {kept:,}, decisions {decisions:,}", flush=True)
    consume_complete(carry)
print(f"sampled {kept:,}/{seen:,} action edges in {decisions:,} decisions", flush=True)

state = [np.concatenate(p) for p in parts[:9]]
action_scalar = np.concatenate(parts[9])
action_card = np.concatenate(parts[10])
visit = np.concatenate(parts[11])
counts = np.concatenate(parts[12]).astype(np.int64)
decision_fight = np.concatenate(parts[13])
tree_logit = np.concatenate(parts[14])
del parts
gc.collect()
starts = np.r_[0, np.cumsum(counts[:-1])]
ends = starts + counts
if counts.max() > 64:
    raise RuntimeError(f"decision has {counts.max()} edges; native prior supports at most 64")
if not np.all(np.add.reduceat(visit, starts) > 0):
    raise RuntimeError("found a decision with zero total visits")
target = visit / np.repeat(np.add.reduceat(visit, starts), counts)
del visit
gc.collect()
ndec = len(starts)
print(f"collapsed to {ndec:,} decisions, {len(target):,} edges "
      f"({len(target)/ndec:.2f} edges/decision, max {counts.max()})", flush=True)

is_val = (mix64(decision_fight + np.uint64(0xD1B54A32D192ED03)) % np.uint64(10)) == 0
tr = np.flatnonzero(~is_val)
va = np.flatnonzero(is_val)
print(f"fight-group split: train {len(tr):,}, validation {len(va):,}", flush=True)

scalar, cards, relics, potions, encounter, mids, intents, mcont, mmask = state
scalar_mean = scalar[tr].mean(0, dtype=np.float64).astype(np.float32)
scalar_inv = 1 / np.maximum(scalar[tr].std(0, dtype=np.float64).astype(np.float32), 1e-6)
mon_train = mcont[tr][mmask[tr]]
mon_mean = mon_train.mean(0, dtype=np.float64).astype(np.float32)
mon_inv = 1 / np.maximum(mon_train.std(0, dtype=np.float64).astype(np.float32), 1e-6)

# Action statistics are computed only from edges owned by training decisions.
train_dec_mask = np.zeros(ndec, np.bool_)
train_dec_mask[tr] = True
train_edge_mask = np.repeat(train_dec_mask, counts)
action_mean = action_scalar[train_edge_mask].mean(0, dtype=np.float64).astype(np.float32)
action_inv = 1 / np.maximum(
    action_scalar[train_edge_mask].std(0, dtype=np.float64).astype(np.float32), 1e-6)
del train_dec_mask, train_edge_mask, mon_train

scalar -= scalar_mean
scalar *= scalar_inv
mcont -= mon_mean
mcont *= mon_inv
mcont *= mmask[..., None]
action_scalar -= action_mean
action_scalar *= action_inv


class EntityPolicyNet(nn.Module):
    """Factorized state/action encoders with a learned compatibility score."""
    def __init__(self):
        super().__init__()
        self.card = nn.Parameter(torch.randn(4, 371, 12) * 0.02)
        self.relic = nn.Parameter(torch.randn(128, 8) * 0.02)
        self.potion = nn.Parameter(torch.randn(44, 4) * 0.02)
        self.encounter = nn.Embedding(128, 8)
        self.monster_id = nn.Embedding(256, 12)
        self.intent = nn.Embedding(32, 4)
        self.monster = nn.Sequential(nn.Linear(23, 24), nn.ReLU())
        self.state = nn.Sequential(nn.Linear(180, 64), nn.ReLU())
        self.action_card = nn.Embedding(371, 16)
        self.action = nn.Sequential(nn.Linear(29, 64), nn.ReLU())
        self.action_bias = nn.Linear(29, 1)

    def encode_state(self, scalar, cards, relics, potions, encounter,
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
        return self.state(z)

    def encode_action(self, scalar, card_id):
        valid = card_id >= 0
        cid = card_id.clamp(0, 370)
        card = self.action_card(cid) * valid.unsqueeze(1)
        z = torch.cat((scalar, card), 1)
        return self.action(z), self.action_bias(z).squeeze(1)

    def score(self, state_hidden, action_scalar, action_card, owner):
        ah, bias = self.encode_action(action_scalar, action_card)
        return (state_hidden[owner] * ah).sum(1) / math.sqrt(64.0) + bias


state_tensors = [torch.from_numpy(a) for a in state]
action_scalar_t = torch.from_numpy(action_scalar)
action_card_t = torch.from_numpy(action_card.astype(np.int64, copy=False))
target_t = torch.from_numpy(target.astype(np.float32, copy=False))


def state_forward(ids, model):
    s, c, r, p, e, mi, it, mc, mm = [x[ids] for x in state_tensors]
    return model.encode_state(s.to(DEVICE), c.to(DEVICE, dtype=torch.float32),
                              r.to(DEVICE, dtype=torch.float32),
                              p.to(DEVICE, dtype=torch.float32), e.to(DEVICE, dtype=torch.long),
                              mi.to(DEVICE, dtype=torch.long), it.to(DEVICE, dtype=torch.long),
                              mc.to(DEVICE), mm.to(DEVICE))


def batch_edges(decision_ids):
    lengths = counts[decision_ids]
    edge_ids = np.concatenate([np.arange(starts[d], ends[d], dtype=np.int64)
                               for d in decision_ids])
    owner = np.repeat(np.arange(len(decision_ids), dtype=np.int64), lengths)
    return (torch.from_numpy(edge_ids), torch.from_numpy(owner),
            torch.from_numpy(lengths.astype(np.int64, copy=False)))


def grouped_log_probs(logits, owner, lengths, n):
    neg_inf = torch.full((n,), -torch.inf, dtype=logits.dtype, device=logits.device)
    maxima = neg_inf.scatter_reduce(0, owner, logits, reduce="amax", include_self=True)
    sums = torch.zeros(n, dtype=logits.dtype, device=logits.device).scatter_add_(
        0, owner, torch.exp(logits - maxima[owner]))
    return logits - maxima[owner] - torch.log(sums[owner]), lengths


@torch.no_grad()
def collect_logits(model, decision_ids):
    model.eval()
    out = []
    for lo in range(0, len(decision_ids), BATCH_DECISIONS):
        d = decision_ids[lo:lo+BATCH_DECISIONS]
        ids = torch.from_numpy(d.astype(np.int64, copy=False))
        edge, owner, _ = batch_edges(d)
        sh = state_forward(ids, model)
        out.append(model.score(sh, action_scalar_t[edge].to(DEVICE),
                               action_card_t[edge].to(DEVICE), owner.to(DEVICE)).cpu())
    return torch.cat(out).numpy()


def decision_metrics(decision_ids, logits, label):
    top1 = captured = mass_best = ce = 0.0
    pos = 0
    for d in decision_ids:
        n = counts[d]
        p = logits[pos:pos+n]
        y = target[starts[d]:ends[d]]
        pred = int(np.argmax(p))
        best = int(np.argmax(y))
        pe = np.exp(p - p.max())
        pe /= pe.sum()
        top1 += pred == best
        captured += y[pred]
        mass_best += pe[best]
        ce -= float(np.sum(y * np.log(np.maximum(pe, 1e-12))))
        pos += n
    m = len(decision_ids)
    metrics = dict(top1=top1/m, captured=captured/m, mass_best=mass_best/m, ce=ce/m)
    print(f"{label}: top1={metrics['top1']:.4f} captured={metrics['captured']:.4f} "
          f"mass_best={metrics['mass_best']:.4f} cross_entropy={metrics['ce']:.4f}", flush=True)
    return metrics


model = EntityPolicyNet().to(DEVICE)
opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
best = None
best_ce = float("inf")
stale = 0
rng = np.random.default_rng(0)
print(f"training entity policy on {DEVICE} (CPU preprocessing threads={THREADS}) ...", flush=True)
for epoch in range(1, EPOCHS + 1):
    model.train()
    order = rng.permutation(tr)
    losses = []
    for lo in range(0, len(order), BATCH_DECISIONS):
        d = order[lo:lo+BATCH_DECISIONS]
        ids = torch.from_numpy(d.astype(np.int64, copy=False))
        edge, owner, lengths = batch_edges(d)
        sh = state_forward(ids, model)
        edge_scalar = action_scalar_t[edge].to(DEVICE)
        edge_card = action_card_t[edge].to(DEVICE)
        owner_device = owner.to(DEVICE)
        lengths_device = lengths.to(DEVICE)
        logits = model.score(sh, edge_scalar, edge_card, owner_device)
        logp, _ = grouped_log_probs(logits, owner_device, lengths_device, len(d))
        y = target_t[edge].to(DEVICE)
        if LABEL_SMOOTH > 0:
            y = ((1.0 - LABEL_SMOOTH) * y
                 + LABEL_SMOOTH / lengths_device[owner_device])
        loss = -(y * logp).sum() / len(d)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        opt.step()
        losses.append(float(loss.detach()))

    val_logits = collect_logits(model, va)
    vm = decision_metrics(va, val_logits, f"epoch {epoch:02d} val")
    print(f"epoch {epoch:02d} train_loss={np.mean(losses):.5f}", flush=True)
    previous_best = best_ce
    if vm["ce"] < best_ce:
        best_ce = vm["ce"]
        best = copy.deepcopy(model.state_dict())
    if vm["ce"] < previous_best - 0.001:
        stale = 0
    else:
        stale += 1
        if stale >= 3:
            break

model.load_state_dict(best)
nn_logits = collect_logits(model, va)
nn_metrics = decision_metrics(va, nn_logits, "BEST entity NN")

if tree is not None:
    # collect_logits orders edges decision-by-decision; the source CSV has that same
    # order, but validation decisions are non-contiguous, so gather the reference.
    tree_val = np.concatenate([tree_logit[starts[d]:ends[d]] for d in va])
    tree_metrics = decision_metrics(va, tree_val, "reference 100-tree")
else:
    tree_metrics = None

torch.save(dict(state_dict=model.state_dict(), scalar_cols=scalar_cols,
                action_scalars=ACTION_SCALARS, scalar_mean=scalar_mean,
                scalar_inv=scalar_inv, mon_mean=mon_mean, mon_inv=mon_inv,
                action_mean=action_mean, action_inv=action_inv,
                nn_metrics=nn_metrics, tree_metrics=tree_metrics), OUT + ".pt")


def write_values(f, token, value):
    a = value.detach().cpu().numpy() if torch.is_tensor(value) else np.asarray(value)
    f.write(token)
    for v in a.astype(np.float32).ravel():
        f.write(f" {float(v):.9g}")
    f.write("\n")


sd = model.state_dict()
with open(OUT, "w") as f:
    f.write("combat_policy_entity_v1\n")
    f.write(f"nscalar {len(scalar_cols)}\n")
    for name in scalar_cols:
        f.write(f"scalar {name}\n")
    f.write(f"nactionscalar {len(ACTION_SCALARS)}\n")
    for name in ACTION_SCALARS:
        f.write(f"action_scalar {name}\n")
    write_values(f, "scalar_mean", scalar_mean)
    write_values(f, "scalar_inv", scalar_inv)
    write_values(f, "mon_mean", mon_mean)
    write_values(f, "mon_inv", mon_inv)
    write_values(f, "action_mean", action_mean)
    write_values(f, "action_inv", action_inv)
    for token in ("card", "relic", "potion", "encounter.weight", "monster_id.weight",
                  "intent.weight", "monster.0.weight", "monster.0.bias",
                  "state.0.weight", "state.0.bias", "action_card.weight",
                  "action.0.weight", "action.0.bias", "action_bias.weight",
                  "action_bias.bias"):
        write_values(f, token.replace(".", "_"), sd[token])
print(f"wrote {OUT} and {OUT}.pt", flush=True)

# Canonical parity rows: one row per action edge and the Python logit last.
sample = pd.read_csv(CSV, dtype=dtypes, nrows=200)
sa = list(extract_state(sample))
sa[0][:] = (sa[0] - scalar_mean) * scalar_inv
sa[7][:] = (sa[7] - mon_mean) * mon_inv
sa[7] *= sa[8][..., None]
aa = sample[ACTION_SCALARS].to_numpy(np.float32)
aa = (aa - action_mean) * action_inv
ac = sample["aCardId"].to_numpy(np.int64)
with torch.no_grad():
    args = [torch.from_numpy(x) for x in sa]
    sh = model.encode_state(args[0].to(DEVICE), args[1].to(DEVICE, dtype=torch.float32),
                            args[2].to(DEVICE, dtype=torch.float32),
                            args[3].to(DEVICE, dtype=torch.float32),
                            args[4].to(DEVICE, dtype=torch.long),
                            args[5].to(DEVICE, dtype=torch.long),
                            args[6].to(DEVICE, dtype=torch.long), args[7].to(DEVICE),
                            args[8].to(DEVICE))
    owner = torch.arange(len(sample), dtype=torch.int64, device=DEVICE)
    pred = model.score(sh, torch.from_numpy(aa).to(DEVICE),
                       torch.from_numpy(ac).to(DEVICE), owner).cpu().numpy()
vout = sample[canonical_policy].copy()
vout["pyLogit"] = pred
vout.to_csv(VAL, index=False)
print(f"wrote {VAL}: {len(vout)} parity rows", flush=True)
