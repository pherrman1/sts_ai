#!/usr/bin/env python3
"""DeepSets combat value net: V_combat(state) -> expected fight end HP.

Architecture: treats the combat state as permutation-invariant sets of
cards (by zone), relics, potions, and monsters. Each element gets a learned
embedding, summed within its set, then concatenated with a scalar encoder
→ MLP → scalar end-HP prediction.

Why DeepSets: XGBoost/CatBoost trees split one feature at a time and are
architecturally weak at card synergies (Corruption+Dead Branch, etc. are
AND-interactions over sparse card-count columns). DeepSets learns per-card
embeddings so the MLP sees rich interaction features in the pooled latent.

Format tag: combat_deepsets_v1.  Loaded by CombatValueNet::load() through
the same STS_VNET path.  Parity-tested via vnettest mode.

Usage:
  .venv/bin/python3 train_combat_deepsets.py [csv] [out.txt] [epochs]

Env vars:
  DS_EPOCHS, DS_BATCH, DS_LR, DS_WD,
  DS_DCARD (default 64), DS_DRELIC (32), DS_DPOT (16),
  DS_DMON (32), DS_DENC (16), DS_DSCALAR (32),
  DS_H1 (128), DS_H2 (64)
"""
import sys, os, time
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import r2_score

# ── constants matching CombatValueNet.cpp offsets ──
_NBASE  = 26    # ascension..potions
_NPOW   = 24    # pDemonForm..pFrail
_NREL   = 128   # r0..r127
_NCARD  = 371   # card IDs per zone
_NZONE  = 4     # hand, draw, discard, exhaust
_NENAGG = 2     # incomingDmg, nAttacking
_NMON   = 5     # monster slots
_NMFEAT = 9     # features per monster slot
_NPOT   = 44    # potion IDs
_NMISC  = 5     # gold, potionCap, cardsPlayed, attacksPlayed, skillsPlayed
_NRELCT = 8     # relic counters

# Offsets within the 1766-element canonical feature vector
_BASE_OFF    = 0
_POW_OFF     = _NBASE
_RELIC_OFF   = _POW_OFF + _NPOW
_HAND_OFF    = _RELIC_OFF + _NREL
_DRAW_OFF    = _HAND_OFF + _NCARD
_DISC_OFF    = _DRAW_OFF + _NCARD
_EXH_OFF     = _DISC_OFF + _NCARD
_ENAGG_OFF   = _EXH_OFF  + _NCARD
_MON_OFF     = _ENAGG_OFF + _NENAGG
_POT_OFF     = _MON_OFF + _NMON * _NMFEAT
_MISC_OFF    = _POT_OFF + _NPOT
_RELCT_OFF   = _MISC_OFF + _NMISC
_TOTAL       = _RELCT_OFF + _NRELCT

# Scalar indices: base + powers + enemy agg + misc + relic counters
_SCALAR_IDXS = (
    list(range(_BASE_OFF, _POW_OFF + _NPOW)) +
    list(range(_ENAGG_OFF, _ENAGG_OFF + _NENAGG)) +
    list(range(_MISC_OFF, _MISC_OFF + _NMISC)) +
    list(range(_RELCT_OFF, _RELCT_OFF + _NRELCT))
)

# Encounter feature index (must match CombatValueNet.cpp: encounter is feature index 1)
_ENC_IDX = 1


# ── Model ──

class CombatDeepSet(nn.Module):
    def __init__(self, d_card=64, d_relic=32, d_pot=16, d_mon=32, d_enc=16,
                 d_scalar=32, h1=128, h2=64, n_enc=256):
        super().__init__()
        # Card embeddings: one per card ID, shared across all 4 zones.
        # sum-pool = counts @ E (matmul) — same trick as train_deckset.py.
        self.card_embed = nn.Parameter(torch.randn(_NCARD, d_card) * 0.02)
        self.relic_embed = nn.Embedding(_NREL, d_relic)
        self.potion_embed = nn.Embedding(_NPOT, d_pot)
        self.encounter_embed = nn.Embedding(n_enc, d_enc)

        # Monster encoder: 9 → d_mon → d_mon (2-layer MLP per slot)
        self.mon_w1 = nn.Parameter(torch.randn(d_mon, _NMFEAT) * 0.1)
        self.mon_b1 = nn.Parameter(torch.zeros(d_mon))
        self.mon_w2 = nn.Parameter(torch.randn(d_mon, d_mon) * 0.1)
        self.mon_b2 = nn.Parameter(torch.zeros(d_mon))

        # Scalar encoder
        n_scal = len(_SCALAR_IDXS)
        self.scalar_w = nn.Parameter(torch.randn(d_scalar, n_scal) * 0.1)
        self.scalar_b = nn.Parameter(torch.zeros(d_scalar))

        # Pooled vector dim
        self.n_scal = len(_SCALAR_IDXS)
        self.register_buffer('scalar_mean', torch.zeros(self.n_scal))
        self.register_buffer('scalar_inv', torch.ones(self.n_scal))

        concat_dim = (d_card +        # sum-pool hand
                      d_card +        # sum-pool draw
                      d_card +        # sum-pool discard
                      d_card +        # sum-pool exhaust
                      d_relic +       # sum-pool relics
                      d_pot +         # sum-pool potions
                      d_mon +         # mean-pool monsters
                      d_enc +         # encounter embedding
                      d_scalar)       # scalar encoding

        self.mlp = nn.Sequential(
            nn.Linear(concat_dim, h1), nn.ReLU(),
            nn.Linear(h1, h2), nn.ReLU(),
            nn.Linear(h2, 1),
        )

    def forward(self, x):
        """x: (B, _TOTAL) float32 tensor — canonical feature vector."""
        B = x.shape[0]

        # ── cards: sum-pool per zone ──
        hand = x[:, _HAND_OFF:_HAND_OFF+_NCARD]       # (B, 371)
        draw = x[:, _DRAW_OFF:_DRAW_OFF+_NCARD]
        disc = x[:, _DISC_OFF:_DISC_OFF+_NCARD]
        exh  = x[:, _EXH_OFF:_EXH_OFF+_NCARD]
        ch = hand @ self.card_embed   # counts @ E = sum of embeddings
        cd = draw @ self.card_embed
        cc = disc @ self.card_embed
        ce = exh  @ self.card_embed

        # ── relics: sum-pool over present relics (binary mask) ──
        rel = x[:, _RELIC_OFF:_RELIC_OFF+_NREL]       # (B, 128)
        rel_mask = (rel > 0.5).float()
        cr = rel_mask @ self.relic_embed.weight        # (B, d_relic)

        # ── potions: count-weighted sum ──
        pot = x[:, _POT_OFF:_POT_OFF+_NPOT]            # (B, 44)
        cp = pot @ self.potion_embed.weight

        # ── encounter embedding ──
        enc = x[:, _ENC_IDX].long().clamp(0, self.encounter_embed.num_embeddings-1)
        ce_enc = self.encounter_embed(enc)

        # ── monsters: per-slot encode, mean-pool over alive ──
        mon = x[:, _MON_OFF:_MON_OFF+_NMON*_NMFEAT].reshape(B, _NMON, _NMFEAT)
        mon_alive = (mon[:, :, 1] > 0).float()          # m{i}Hp > 0
        # Per-slot MLP: (B, 5, d_mon)
        ms = mon @ self.mon_w1.t() + self.mon_b1        # (B, 5, d_mon)
        ms = torch.relu(ms)
        ms = ms @ self.mon_w2.t() + self.mon_b2
        ms = torch.relu(ms)
        # Mean-pool over alive monsters (avoid div-by-zero)
        ms = ms * mon_alive.unsqueeze(-1)
        cm = ms.sum(dim=1) / mon_alive.sum(dim=1, keepdim=True).clamp(min=1)

        # ── scalars: z-normalize → clamp → linear ──
        sc = x[:, _SCALAR_IDXS]
        sc = (sc - self.scalar_mean) * self.scalar_inv
        sc = torch.clamp(sc, -5.0, 5.0)
        cs = sc @ self.scalar_w.t() + self.scalar_b
        cs = torch.relu(cs)

        # ── concatenate and MLP ──
        pooled = torch.cat([ch, cd, cc, ce, cr, cp, cm, ce_enc, cs], dim=1)
        return self.mlp(pooled).squeeze(1)


# ── Training ──

def main():
    CSV   = sys.argv[1] if len(sys.argv) > 1 else "build/vcombat_honest.csv"
    OUT   = sys.argv[2] if len(sys.argv) > 2 else "build/v_combat_deepsets.txt"
    EPOCHS = int(os.environ.get("DS_EPOCHS",
                sys.argv[3] if len(sys.argv) > 3 else "30"))
    BATCH  = int(os.environ.get("DS_BATCH", "4096"))
    LR     = float(os.environ.get("DS_LR", "1e-3"))
    WD     = float(os.environ.get("DS_WD", "1e-4"))
    DCARD  = int(os.environ.get("DS_DCARD", "64"))
    DREL   = int(os.environ.get("DS_DRELIC", "32"))
    DPOT   = int(os.environ.get("DS_DPOT", "16"))
    DMON   = int(os.environ.get("DS_DMON", "32"))
    DENC   = int(os.environ.get("DS_DENC", "16"))
    DSCL   = int(os.environ.get("DS_DSCALAR", "32"))
    H1     = int(os.environ.get("DS_H1", "128"))
    H2     = int(os.environ.get("DS_H2", "64"))

    DEV = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(42); np.random.seed(42)
    print(f"device={DEV} epochs={EPOCHS} batch={BATCH}", flush=True)

    # ── load data ──
    print(f"loading {CSV} ...", flush=True)
    t0 = time.time()
    hdr = pd.read_csv(CSV, nrows=0).columns
    dtypes = {c: (np.int32 if c in ("seed","fightIdx") else np.int16) for c in hdr}
    df = pd.read_csv(CSV, dtype=dtypes)
    print(f"  {len(df)} rows in {time.time()-t0:.1f}s", flush=True)

    feat_cols = [c for c in df.columns
                 if c not in ("seed","fightIdx","won","endHp")
                 and df[c].std() > 1e-9]
    # Verify canonical feature count
    assert len(feat_cols) <= _TOTAL, f"Data has {len(feat_cols)} features, expected ≤ {_TOTAL}"

    X = df[feat_cols].to_numpy(np.float32)
    y = df["endHp"].to_numpy(np.float32)
    group = (df["seed"].to_numpy(np.int64)*1000 + df["fightIdx"].to_numpy(np.int64))

    # Critical-state weights (same as train_value_combat.py)
    won = df["won"].to_numpy(np.float32)
    hp_frac = np.clip(df["curHp"].to_numpy(np.float32) / np.maximum(df["maxHp"].to_numpy(np.float32), 1.0), 0, 1)
    fights = df[["seed","fightIdx","encounter","won"]].drop_duplicates(["seed","fightIdx"])
    enc_fail_map = (1.0 - fights.groupby("encounter")["won"].mean()).to_dict()
    enc_fail = df["encounter"].map(enc_fail_map).to_numpy(np.float32)
    weight = np.clip(1.0 + 2.0*(1.0-hp_frac)**2 + 2.0*(1.0-won) + 1.5*enc_fail, 1.0, 8.0).astype(np.float32)
    weight /= weight.mean()

    # Max encounter for embedding table
    n_enc = int(df["encounter"].max()) + 1

    # Feature name → canonical index mapping
    canon_names = None
    # We'll read the CSV header and map against our known structure
    feat_name_to_idx = {n: i for i, n in enumerate(feat_cols)}

    del df; import gc; gc.collect()

    # ── train/val split ──
    tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0).split(X, y, groups=group))
    print(f"  train {len(tr)} val {len(va)} n_enc {n_enc}", flush=True)

    # ── Pad X to _TOTAL columns (fill missing with 0) ──
    if X.shape[1] < _TOTAL:
        Xp = np.zeros((X.shape[0], _TOTAL), dtype=np.float32)
        for ci, cn in enumerate(feat_cols):
            Xp[:, ci] = X[:, ci]  # features match 1:1 since feat_cols are the first N canonical features
        X = Xp

    X_tr = torch.from_numpy(np.ascontiguousarray(X[tr]))
    y_tr = torch.from_numpy(np.ascontiguousarray(y[tr]))
    w_tr = torch.from_numpy(np.ascontiguousarray(weight[tr]))
    X_va = torch.from_numpy(np.ascontiguousarray(X[va]))
    y_va = torch.from_numpy(np.ascontiguousarray(y[va]))

    # ── compute scalar stats ──
    scalar_mean = X_tr[:, _SCALAR_IDXS].mean(dim=0)
    scalar_std  = X_tr[:, _SCALAR_IDXS].std(dim=0) + 1e-6
    scalar_inv  = 1.0 / scalar_std

    # ── compute y stats for output denormalization ──
    y_mean = y_tr.mean().item()
    y_std  = y_tr.std().item() + 1e-6
    y_norm = (y_tr - y_mean) / y_std

    # ── model ──
    model = CombatDeepSet(d_card=DCARD, d_relic=DREL, d_pot=DPOT, d_mon=DMON,
                          d_enc=DENC, d_scalar=DSCL, h1=H1, h2=H2, n_enc=n_enc)
    model.scalar_mean.copy_(scalar_mean)
    model.scalar_inv.copy_(scalar_inv)
    model.to(DEV)
    print(f"  params: {sum(p.numel() for p in model.parameters()):,}", flush=True)

    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WD)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=EPOCHS)
    lossf = nn.MSELoss(reduction='none')

    # ── training loop ──
    best_rmse = float('inf')
    best_state = None
    best_ep = 0

    for ep in range(EPOCHS):
        model.train()
        perm = torch.randperm(len(tr))
        tl = 0.0; nb = 0
        for i in range(0, len(tr), BATCH):
            idx = perm[i:i+BATCH]
            xb = X_tr[idx].to(DEV); yb = y_norm[idx].to(DEV); wb = w_tr[idx].to(DEV)
            opt.zero_grad()
            pred = model(xb)
            loss = (lossf(pred, yb) * wb).mean()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tl += loss.item(); nb += 1
        sched.step()

        # validation
        model.eval()
        with torch.no_grad():
            pv = model(X_va.to(DEV)).cpu()
            # Denormalize
            pv_raw = pv * y_std + y_mean
            rmse = float(np.sqrt(((y_va.numpy() - pv_raw.numpy())**2).mean()))

        flag = ""
        if rmse < best_rmse:
            best_rmse = rmse; best_ep = ep + 1
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            flag = " *"
        print(f"ep {ep+1:2d}/{EPOCHS}  loss={tl/nb:.4f}  val_rmse={rmse:.2f}  "
              f"r2={r2_score(y_va.numpy(), pv_raw.numpy()):.4f}{flag}", flush=True)

    if best_state is None:
        print("ERROR: no best state", flush=True); sys.exit(1)

    model.load_state_dict(best_state)

    # ── export ──
    export_deepsets(model, OUT, feat_cols, y_mean, y_std, n_enc)
    print(f"saved -> {OUT}  best RMSE {best_rmse:.2f} @ep{best_ep}", flush=True)

    # ── parity CSV ──
    val_csv = OUT.replace('.txt', '_val.csv')
    write_parity_csv(model, X_va, y_va, feat_cols, val_csv, y_mean, y_std, DEV)
    print(f"parity csv -> {val_csv}", flush=True)


# ── Export ──

def export_deepsets(model, path, feat_cols, y_mean, y_std, n_enc):
    sd = model.state_dict()

    # Build scalar selector indices (canonical positions)
    scalar_sel = _SCALAR_IDXS

    with open(path, 'w') as f:
        f.write("combat_deepsets_v1\n")
        f.write(f"d_card {model.card_embed.shape[1]}\n")
        f.write(f"d_relic {model.relic_embed.weight.shape[1]}\n")
        f.write(f"d_pot {model.potion_embed.weight.shape[1]}\n")
        f.write(f"d_mon {model.mon_w2.shape[0]}\n")
        f.write(f"d_enc {model.encounter_embed.weight.shape[1]}\n")
        f.write(f"d_scalar {model.scalar_w.shape[0]}\n")
        f.write(f"h1 {model.mlp[0].out_features}\n")
        f.write(f"h2 {model.mlp[2].out_features}\n")
        f.write(f"encounter_idx {_ENC_IDX}\n")
        f.write(f"n_encounter {n_enc}\n")
        f.write(f"nscalar {len(scalar_sel)}\n")

        # Scalar selector
        f.write("scalar_sel")
        for s in scalar_sel:
            f.write(f" {s}")
        f.write("\n")

        def wrv(name, vec):
            f.write(f"{name}")
            vn = vec.detach().cpu().numpy().flatten()
            for v in vn:
                f.write(f" {v:.8g}")
            f.write("\n")

        wrv("scalar_mean", model.scalar_mean)
        wrv("scalar_inv", model.scalar_inv)
        wrv("scalar_w", model.scalar_w)
        wrv("scalar_b", model.scalar_b)

        # Card embeddings: (371, d_card)
        wrv("card_embed", sd["card_embed"])

        # Relic embedding: (128, d_relic)
        wrv("relic_embed", sd["relic_embed.weight"])

        # Potion embedding: (44, d_pot)
        wrv("potion_embed", sd["potion_embed.weight"])

        # Encounter embedding: (n_enc, d_enc)
        wrv("encounter_embed", sd["encounter_embed.weight"])

        # Monster encoder
        wrv("mon_w1", sd["mon_w1"])
        wrv("mon_b1", sd["mon_b1"])
        wrv("mon_w2", sd["mon_w2"])
        wrv("mon_b2", sd["mon_b2"])

        # MLP head
        wrv("w1", sd["mlp.0.weight"])
        wrv("b1", sd["mlp.0.bias"])
        wrv("w2", sd["mlp.2.weight"])
        wrv("b2", sd["mlp.2.bias"])
        wrv("w3", sd["mlp.4.weight"])
        wrv("b3", sd["mlp.4.bias"])

        f.write(f"y_mean {y_mean:.8g}\n")
        f.write(f"y_scale {y_std:.8g}\n")


def write_parity_csv(model, X_va, y_va, feat_cols, path, y_mean, y_std, DEV):
    """Write canonical features + pyPred for vnettest parity."""
    model.eval()
    with torch.no_grad():
        pv = model(X_va.to(DEV)).cpu()
        pv_raw = pv * y_std + y_mean

    n = min(200, len(X_va))
    X_sample = X_va[:n].numpy()
    pred_sample = pv_raw[:n].numpy()

    # Use canonical 1766 feature names matching combatFeatureNames()
    canon_names = _build_canonical_names()

    with open(path, 'w') as f:
        f.write(','.join(canon_names) + ',pyPred\n')
        for i in range(n):
            row = ','.join(str(int(v)) if v == int(v) else f'{v:.6g}' for v in X_sample[i])
            f.write(f'{row},{pred_sample[i]:.6g}\n')


def _build_canonical_names():
    """Build the full 1766 canonical feature names matching combatFeatureNames()."""
    names = []
    base = ["ascension","encounter","turn","curHp","maxHp","block","energy",
            "strength","dexterity","focus","artifact","monAlive","monSumHp",
            "monMaxHp","monSumBlock","monSumStr","monSumArt",
            "hand","draw","discard","exhaust","nAtkAvail","nSklAvail",
            "nPowAvail","nOtherAvail","potions"]
    names.extend(base)
    powers = ["pDemonForm","pMetallicize","pFeelNoPain","pBarricade","pPlatedArmor",
              "pRupture","pCombust","pDarkEmbrace","pBrutality","pFireBreath",
              "pJuggernaut","pCorruption","pVigor","pMayhem","pPanache",
              "pNoxious","pFlameBarrier","pThorns","pRegen","pBuffer",
              "pIntangible","pVulnerable","pWeak","pFrail"]
    names.extend(powers)
    for i in range(128): names.append(f"r{i}")
    for i in range(371): names.append(f"hd{i}")
    for i in range(371): names.append(f"dr{i}")
    for i in range(371): names.append(f"ds{i}")
    for i in range(371): names.append(f"ex{i}")
    names.extend(["incomingDmg","nAttacking"])
    for i in range(5):
        names.extend([f"m{i}Id",f"m{i}Hp",f"m{i}Block",f"m{i}Str",
                      f"m{i}Intent",f"m{i}Atk",f"m{i}Vuln",f"m{i}Weak",f"m{i}Poison"])
    for i in range(44): names.append(f"pot{i}")
    names.extend(["gold","potionCap","cardsPlayed","attacksPlayed","skillsPlayed"])
    names.extend(["happyFlowerCtr","incenseBurnerCtr","inkBottleCtr","inserterCtr",
                  "nunchakuCtr","penNibCtr","sundialCtr","panacheCtr"])
    return names


if __name__ == "__main__":
    main()
