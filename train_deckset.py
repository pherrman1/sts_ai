#!/usr/bin/env python3
"""Deck-set NN win-value model: V_win_nn(state) -> P(win) on vrich.csv.

Motivation (see EXPERIMENTS / boss-aware-drafting): the GBM value models split one
feature at a time and are architecturally weak at CARD SYNERGIES (Corruption+Dead
Branch, Barricade+Body Slam, etc. are AND-interactions over sparse per-card-count
columns). A DeepSets NN treats the deck as a SET of cards via learned embeddings,
pools them, then an MLP models nonlinear interactions in the pooled latent -- the
natural model for "a deck is a bag of cards that interact".

Key trick: sum-pool over card embeddings == counts @ E (a matmul), so no explicit
per-card token expansion is needed. Deck vector =
    (d-u) @ E_base + u @ E_up           # unupgraded vs upgraded embedding tables
Relics: presence @ E_relic. Potions: counts @ E_pot. bossId: embedding. Remaining
meaningful numeric scalars are z-normalized and concatenated. Head -> sigmoid P(win).

Target = won (BCE). Group-split by seed so no run leaks across train/val. Baseline
to beat: v_win GBM val AUC 0.748. Saves build/v_deckset.pt (+ meta in the checkpoint).

NOTE: importing this module is SIDE-EFFECT-FREE (only defines DeckSet + constants);
all data loading / training runs under __main__ so eval scripts can import DeckSet
without kicking off a second 2.9GB CSV load.
"""
import sys, time, numpy as np, torch
import torch.nn as nn

NCARDS, NRELICS, NPOT = 372, 181, 48
# meaningful numeric scalars (drop raw categorical ids except bossId which we embed;
# raw ids like nextFight0 are meaningless magnitudes to an MLP -> excluded).
SCALARS = ["ascension","act","floor","curHp","maxHp","gold","deckSize","potionChance",
           "cardRarityFactor","blueKey","greenKey","redKey","potionCount","potionCapacity",
           "remElites","remFights","monOffset","eliteOffset",
           "pvShop","pvRest","pvEvent","pvElite","pvMonster","pvTreasure"]
NSCL = len(SCALARS) + 1   # + hp_frac appended at build time


class DeckSet(nn.Module):
    def __init__(self, nboss, nscl=NSCL, dcard=32, drelic=16, dpot=8, dboss=8, hidden=256):
        super().__init__()
        self.E_base = nn.Embedding(NCARDS, dcard)     # unupgraded card embeddings
        self.E_up   = nn.Embedding(NCARDS, dcard)     # upgraded card embeddings
        self.E_rel  = nn.Embedding(NRELICS, drelic)
        self.E_pot  = nn.Embedding(NPOT, dpot)
        self.E_boss = nn.Embedding(nboss, dboss)
        cin = 2*dcard + drelic + dpot + dboss + nscl  # [sum, mean] card pools stacked below
        self.emb_drop = nn.Dropout(0.3)               # regularize the pooled deck vector
        self.mlp = nn.Sequential(
            nn.Linear(cin, hidden), nn.ReLU(), nn.LayerNorm(hidden), nn.Dropout(0.3),
            nn.Linear(hidden, hidden), nn.ReLU(), nn.LayerNorm(hidden), nn.Dropout(0.3),
            nn.Linear(hidden, 1))

    def forward(self, nonup, up, rel, pot, boss, scl):
        # counts @ E  == sum over card tokens of their embeddings (DeepSets sum-pool)
        deck_sum = nonup @ self.E_base.weight + up @ self.E_up.weight      # (B, dcard)
        dsz = (nonup.sum(1, keepdim=True) + up.sum(1, keepdim=True)).clamp(min=1)
        deck_mean = deck_sum / dsz                                          # size-normalized pool
        rel_v = rel @ self.E_rel.weight
        pot_v = pot @ self.E_pot.weight
        boss_v = self.E_boss(boss)
        deck_sum = self.emb_drop(deck_sum); deck_mean = self.emb_drop(deck_mean)
        x = torch.cat([deck_sum, deck_mean, rel_v, pot_v, boss_v, scl], dim=1)
        return self.mlp(x).squeeze(1)


def main():
    import pandas as pd
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.metrics import roc_auc_score, log_loss

    CSV   = sys.argv[1] if len(sys.argv) > 1 else "build/vrich.csv"
    OUT   = sys.argv[2] if len(sys.argv) > 2 else "build/v_deckset.pt"
    EPOCHS = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    DEV = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(0); np.random.seed(0)

    print(f"loading {CSV} (float32) ... dev={DEV}", flush=True)
    df = pd.read_csv(CSV, dtype=np.float32)
    col = {n: i for i, n in enumerate(df.columns)}
    data = df.to_numpy(); del df
    N = len(data)
    block = lambda p, n: data[:, [col[f"{p}{i}"] for i in range(n)]]

    d   = block("d", NCARDS); u = block("u", NCARDS)
    nonup = np.clip(d - u, 0, None)
    rel = (block("r", NRELICS) > 0).astype(np.float32)
    pot = block("pot", NPOT)
    boss = data[:, col["bossId"]].astype(np.int64)
    nboss = int(boss.max()) + 1
    scl = np.stack([data[:, col[c]] for c in SCALARS], axis=1).astype(np.float32)
    scl = np.concatenate([scl, (data[:, col["curHp"]] / np.maximum(data[:, col["maxHp"]],1))[:,None]], axis=1)
    smu, ssd = scl.mean(0), scl.std(0) + 1e-6
    scl = (scl - smu) / ssd
    y = data[:, col["won"]].astype(np.float32)
    _, run = np.unique(data[:, col["seed"]], return_inverse=True)
    del data
    print(f"rows {N}  runs {run.max()+1}  win base-rate {y.mean():.3f}  nboss {nboss}  scalars {scl.shape[1]}", flush=True)

    tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0).split(nonup, y, groups=run))
    print(f"train {len(tr)}  val {len(va)}", flush=True)

    T = lambda a: torch.from_numpy(np.ascontiguousarray(a))
    nonup_t, up_t, rel_t, pot_t = T(nonup), T(u), T(rel), T(pot)
    boss_t, scl_t, y_t = torch.from_numpy(boss), T(scl), T(y)

    model = DeckSet(nboss=nboss, nscl=scl.shape[1]).to(DEV)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=2e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=1e-3,
                epochs=EPOCHS, steps_per_epoch=(len(tr)+8191)//8192)
    lossf = nn.BCEWithLogitsLoss()
    print(f"params {sum(p.numel() for p in model.parameters()):,}", flush=True)

    def batches(idx, bs, shuffle):
        if shuffle: idx = idx[torch.randperm(len(idx))]
        for i in range(0, len(idx), bs):
            b = idx[i:i+bs]
            yield (nonup_t[b].to(DEV), up_t[b].to(DEV), rel_t[b].to(DEV),
                   pot_t[b].to(DEV), boss_t[b].to(DEV), scl_t[b].to(DEV), y_t[b].to(DEV))

    tr_t, va_t = torch.from_numpy(tr), torch.from_numpy(va)
    BS = 8192
    best_auc = 0.0; best_state = None; best_ep = 0
    for ep in range(EPOCHS):
        model.train(); t0 = time.time(); tl = 0.0; nb = 0
        for *xb, yb in batches(tr_t, BS, True):
            opt.zero_grad()
            loss = lossf(model(*xb), yb)
            loss.backward(); opt.step(); sched.step()
            tl += loss.item(); nb += 1
        model.eval(); preds = []; ys = []
        with torch.no_grad():
            for *xb, yb in batches(va_t, 16384, False):
                preds.append(torch.sigmoid(model(*xb)).cpu().numpy()); ys.append(yb.cpu().numpy())
        pv = np.concatenate(preds); yv = np.concatenate(ys)
        auc = roc_auc_score(yv, pv); ll = log_loss(yv, pv)
        flag = ""
        if auc > best_auc:
            best_auc = auc; best_ep = ep+1
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            flag = "  *best*"
        print(f"ep {ep+1:2d}/{EPOCHS}  train_loss {tl/nb:.4f}  val AUC {auc:.4f}  logloss {ll:.4f}  ({time.time()-t0:.0f}s){flag}", flush=True)

    torch.save({"state": best_state, "smu": smu, "ssd": ssd, "scalars": SCALARS,
                "nboss": nboss, "cfg": dict(NCARDS=NCARDS, NRELICS=NRELICS, NPOT=NPOT)}, OUT)
    print(f"saved -> {OUT}   BEST val AUC {best_auc:.4f} @ep{best_ep}  (GBM v_win baseline 0.748)", flush=True)


if __name__ == "__main__":
    main()
