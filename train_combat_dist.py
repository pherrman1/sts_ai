#!/usr/bin/env python3
"""Train a distributional combat value model with cross-entity attention.

Predicts:
  - death probability P(dead)
  - win probability P(win)
  - ending HP quantiles (conditional on win)
  - potion use probability per potion type
  - expected turns remaining

Architecture:
  - Per-entity embedding layers (cards, relics, potions, monsters, encounter)
  - Shared card embedding with zone positional encoding
  - Transformer encoder with self-attention across entity tokens
  - Attention pooling to single state vector
  - Multi-head output for all prediction targets

Usage:
  train_combat_dist.py CSV [OUT]
"""

import os, sys, gc, math
import numpy as np
import pandas as pd
import torch
from torch import nn

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/vdist.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "build/v_combat_dist.txt"
VAL = sys.argv[3] if len(sys.argv) > 3 else "build/v_combat_dist_val.csv"

EPOCHS = int(os.environ.get("DIST_EPOCHS", "15"))
BATCH = int(os.environ.get("DIST_BATCH", "2048"))
THREADS = int(os.environ.get("OMP_NUM_THREADS", "16"))
DEVICE = os.environ.get("DIST_DEVICE", "cuda")
WIN_BONUS = float(os.environ.get("DIST_WIN_BONUS", "50"))
CHUNK = int(os.environ.get("DIST_CHUNK_ROWS", "5000"))
SAMPLE_MOD = max(1, int(os.environ.get("DIST_SAMPLE_MOD", "2")))
ENTITY_DIM = int(os.environ.get("DIST_ENTITY_DIM", "128"))
HIDDEN_DIM = int(os.environ.get("DIST_HIDDEN_DIM", "256"))
NUM_HEADS = int(os.environ.get("DIST_NUM_HEADS", "4"))
NUM_LAYERS = int(os.environ.get("DIST_NUM_LAYERS", "2"))
LR = float(os.environ.get("DIST_LR", "1e-4"))
WEIGHT_DECAY = float(os.environ.get("DIST_WD", "1e-5"))
NQUANTILE = int(os.environ.get("DIST_NQUANTILE", "11"))

if DEVICE == "cuda" and torch.cuda.is_available():
    print(f"[GPU] {torch.cuda.get_device_name(0)}", flush=True)
else:
    DEVICE = "cpu"

torch.manual_seed(0)
torch.set_num_threads(THREADS)


def mix64(x):
    x = np.asarray(x, dtype=np.uint64)
    x = x ^ (x >> np.uint64(30))
    x = x * np.uint64(0xbf58476d1ce4e5b9)
    x = x ^ (x >> np.uint64(27))
    x = x * np.uint64(0x94d049bb133111eb)
    return x ^ (x >> np.uint64(31))


header = list(pd.read_csv(CSV, nrows=0).columns)
LABEL_COLS = ("seed", "fightIdx", "won", "endHp", "endTurn", "potionsConsumed")
POTION_USED_COLS = [f"pUsed{i}" for i in range(44)]
canonical = [c for c in header
             if c not in LABEL_COLS and c not in POTION_USED_COLS]
zones = [[f"{p}{i}" for i in range(371)] for p in ("hd", "dr", "ds", "ex")]
relic_cols = [f"r{i}" for i in range(128)]
potion_cols = [f"pot{i}" for i in range(44)]
monster_cols = [[f"m{i}{s}" for s in
                 ("Id", "Hp", "Block", "Str", "Intent", "Atk", "Vuln", "Weak", "Poison")]
                for i in range(5)]
monster_flat = [c for row in monster_cols for c in row]
entity_cols = set(relic_cols + potion_cols + monster_flat + ["encounter"] + [c for z in zones for c in z])
scalar_cols = [c for c in canonical if c not in entity_cols]
assert len(canonical) == 1766 and len(scalar_cols) == 64, \
    f"Expected 1766 feats, got {len(canonical)} canonical, {len(scalar_cols)} scalars"

HAS_DIST_LABELS = all(c in header for c in ["endTurn"] + POTION_USED_COLS)

dtypes = {c: (np.int32 if c in ("seed", "fightIdx") else np.int16) for c in header}


def extract_entities(df):
    """Extract entity tensors from a DataFrame chunk."""
    n = len(df)
    scalar = df[scalar_cols].to_numpy(np.float32)
    cards = np.stack([df[z].to_numpy(np.uint8) for z in zones], axis=1)  # (N, 4, 371)
    relics = df[relic_cols].to_numpy(np.uint8)  # (N, 128)
    potions = df[potion_cols].to_numpy(np.uint8)  # (N, 44)
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
    y_won = df["won"].to_numpy(np.float32)
    y_hp = df["endHp"].to_numpy(np.float32)
    max_hp = df["maxHp"].to_numpy(np.float32)
    y_turn = df["turn"].to_numpy(np.float32)
    if HAS_DIST_LABELS:
        end_turn = df["endTurn"].to_numpy(np.float32)
        turns_remaining = np.maximum(0.0, end_turn - y_turn).astype(np.float32)
        potion_used = df[POTION_USED_COLS].to_numpy(np.float32) if all(c in df.columns for c in POTION_USED_COLS) \
                      else np.zeros((len(df), 44), dtype=np.float32)
    else:
        turns_remaining = np.zeros(len(df), dtype=np.float32)
        potion_used = np.zeros((len(df), 44), dtype=np.float32)
    return (scalar, cards, relics, potions, encounter, mids, intents, mcont, mmask,
            y_won, y_hp, max_hp, turns_remaining, potion_used)


class TransformerLayer(nn.Module):
    def __init__(self, dim, hidden_dim, num_heads):
        super().__init__()
        self.attn = nn.MultiheadAttention(dim, num_heads, batch_first=True)
        self.ln1 = nn.LayerNorm(dim)
        self.ffn = nn.Sequential(
            nn.Linear(dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, dim),
        )
        self.ln2 = nn.LayerNorm(dim)

    def forward(self, x):
        attn_out, _ = self.attn(x, x, x)
        x = self.ln1(x + attn_out)
        ffn_out = self.ffn(x)
        x = self.ln2(x + ffn_out)
        return x


class EntityEncoder(nn.Module):
    def __init__(self, dim, hidden_dim, num_heads, num_layers):
        super().__init__()
        self.dim = dim

        # Card embeddings (shared 371 x dim) + zone positional encoding (4 x dim)
        self.card_embed = nn.Parameter(torch.randn(371, dim) * 0.02)
        self.zone_pos = nn.Parameter(torch.randn(4, dim) * 0.02)

        # Relic embeddings
        self.relic_embed = nn.Parameter(torch.randn(128, 64) * 0.02)
        self.relic_proj = nn.Linear(64, dim) if 64 != dim else nn.Identity()

        # Potion embeddings
        self.potion_embed = nn.Parameter(torch.randn(44, 32) * 0.02)
        self.potion_proj = nn.Linear(32, dim) if 32 != dim else nn.Identity()

        # Encounter embedding
        self.enc_embed = nn.Embedding(128, 32)
        self.enc_proj = nn.Linear(32, dim) if 32 != dim else nn.Identity()

        # Monster ID embedding
        self.mon_id = nn.Embedding(256, 64)

        # Monster intent embedding
        self.mon_intent = nn.Embedding(32, 16)

        # Monster continuous encoder (7 stats + 64 id + 16 intent = 87 -> dim)
        input_dim = 7 + 64 + 16
        self.mon_encoder = nn.Sequential(
            nn.Linear(input_dim, dim),
            nn.ReLU(),
        )

        # Scalar feature encoder (64 -> dim)
        self.scalar_encoder = nn.Sequential(
            nn.Linear(64, dim),
            nn.ReLU(),
        )

        # Transformer layers
        self.layers = nn.ModuleList([
            TransformerLayer(dim, hidden_dim, num_heads)
            for _ in range(num_layers)
        ])

        # Attention pooling
        self.pool_attn = nn.Linear(dim, 1)

        # Normalization stats
        self.register_buffer("scalar_mean", torch.zeros(64))
        self.register_buffer("scalar_inv", torch.ones(64))
        self.register_buffer("mon_cont_mean", torch.zeros(7))
        self.register_buffer("mon_cont_inv", torch.ones(7))

    def build_tokens(self, scalar, cards, relics, potions, encounter,
                     mids, intents, mcont, mmask):
        B = scalar.shape[0]
        tokens = []

        # Scalar token
        s_norm = (scalar - self.scalar_mean) * self.scalar_inv
        tok_scalar = self.scalar_encoder(s_norm).unsqueeze(1)  # (B, 1, dim)
        tokens.append(tok_scalar)

        # Card tokens (one per zone with cards)
        for z in range(4):
            zone_counts = cards[:, z, :]  # (B, 371)
            has_cards = zone_counts.sum(dim=1) > 0
            tok_card = torch.einsum("bc,ce->be", zone_counts.float(), self.card_embed)
            tok_card = tok_card + self.zone_pos[z]
            tok_card = tok_card.unsqueeze(1)  # (B, 1, dim)
            tokens.append(tok_card)

        # Relic token
        relic_tok = torch.einsum("br,re->be", relics.float(), self.relic_embed)
        if 64 != self.dim:
            relic_tok = self.relic_proj(relic_tok)
        tokens.append(relic_tok.unsqueeze(1))

        # Potion token
        potion_tok = torch.einsum("bp,pe->be", potions.float(), self.potion_embed)
        if 32 != self.dim:
            potion_tok = self.potion_proj(potion_tok)
        tokens.append(potion_tok.unsqueeze(1))

        # Encounter token
        enc_tok = self.enc_embed(encounter.long())
        if 32 != self.dim:
            enc_tok = self.enc_proj(enc_tok)
        tokens.append(enc_tok.unsqueeze(1))

        # Monster tokens (one per alive monster)
        for s in range(5):
            alive = mmask[:, s]
            if not alive.any():
                continue
            mid = mids[:, s].long()
            intent = intents[:, s].long()
            mid_emb = self.mon_id(mid.clamp(0, 255))
            intent_emb = self.mon_intent(intent.clamp(0, 31))
            mc = (mcont[:, s, :] - self.mon_cont_mean) * self.mon_cont_inv
            minput = torch.cat([mid_emb, intent_emb, mc], dim=-1)
            mon_tok = self.mon_encoder(minput)
            mon_tok = mon_tok * alive.float().unsqueeze(-1)
            tokens.append(mon_tok.unsqueeze(1))

        # Concatenate all tokens: (B, Ntokens, dim)
        x = torch.cat(tokens, dim=1)
        return x

    def forward(self, scalar, cards, relics, potions, encounter,
                mids, intents, mcont, mmask):
        x = self.build_tokens(scalar, cards, relics, potions, encounter,
                              mids, intents, mcont, mmask)

        # Transformer layers
        for layer in self.layers:
            x = layer(x)

        # Attention pooling
        attn_scores = self.pool_attn(x).squeeze(-1)  # (B, Ntokens)
        attn_w = torch.softmax(attn_scores, dim=-1)  # (B, Ntokens)
        pooled = (attn_w.unsqueeze(-1) * x).sum(dim=1)  # (B, dim)
        return pooled


class CombatDistNet(nn.Module):
    def __init__(self, dim=128, hidden_dim=256, num_heads=4, num_layers=2):
        super().__init__()
        self.encoder = EntityEncoder(dim, hidden_dim, num_heads, num_layers)

        # Heads
        self.death_head = nn.Linear(dim, 1)      # P(death)
        self.win_head = nn.Linear(dim, 1)        # P(win)
        self.quantile_head = nn.Linear(dim, NQUANTILE)  # HP quantiles
        self.potion_head = nn.Linear(dim, 44)     # potion use prob
        self.turns_head = nn.Linear(dim, 1)       # expected turns

    def forward(self, scalar, cards, relics, potions, encounter,
                mids, intents, mcont, mmask):
        pooled = self.encoder(scalar, cards, relics, potions, encounter,
                              mids, intents, mcont, mmask)

        death = self.death_head(pooled).squeeze(-1)   # logit
        win = self.win_head(pooled).squeeze(-1)        # logit
        quantiles = self.quantile_head(pooled)          # (B, NQUANTILE)
        potion_prob = self.potion_head(pooled)           # (B, 44) logits
        turns = self.turns_head(pooled).squeeze(-1)     # raw

        return {
            "death": death,
            "win": win,
            "quantiles": quantiles,
            "potion_prob": potion_prob,
            "turns": turns,
        }


def compute_losses(preds, y_won, y_hp, max_hp, turns_remaining, potion_used):
    """Compute multi-objective losses."""
    losses = {}

    # Death probability: 1 - P(win) for losing fights
    y_death = (y_won <= 0).float()
    losses["death"] = nn.functional.binary_cross_entropy_with_logits(
        preds["death"], y_death)

    # Win probability
    losses["win"] = nn.functional.binary_cross_entropy_with_logits(
        preds["win"], y_won)

    # HP quantiles (only for won fights, pinball loss for quantile regression)
    won_mask = y_won > 0.5
    if won_mask.any():
        hp_frac = y_hp[won_mask] / (max_hp[won_mask] + 1e-6)
        # Pinball (quantile) loss
        quantiles_pred = preds["quantiles"][won_mask]  # (B, NQ)
        target = hp_frac.unsqueeze(-1)  # (B, 1)
        tau = torch.linspace(0.05, 0.95, NQUANTILE, device=target.device).view(1, -1)
        diff = target - quantiles_pred
        losses["quantile"] = (tau * diff.clamp(min=0) + (1 - tau) * (-diff).clamp(min=0)).mean()
    else:
        losses["quantile"] = torch.tensor(0.0, device=DEVICE)

    # Potion use probability: BCE per potion type
    potion_mask = potion_used.sum(dim=-1) > 0
    if potion_mask.any():
        losses["potion"] = nn.functional.binary_cross_entropy_with_logits(
            preds["potion_prob"][potion_mask], potion_used[potion_mask])
    else:
        losses["potion"] = 0.01 * preds["potion_prob"].abs().mean()

    # Expected turns remaining: MSE on log1p scale
    target_turns = torch.log1p(turns_remaining)
    losses["turns"] = nn.functional.smooth_l1_loss(
        preds["turns"], target_turns)

    total = (losses["death"] + losses["win"]
             + 2.0 * losses["quantile"]
             + 0.5 * losses["potion"]
             + 0.3 * losses["turns"])
    return total, losses


def export_model(model, path, scalar_cols_in, mon_cont_cols):
    """Export to native C++ format (combat_dist_v1)."""
    enc = model.encoder
    state = model.state_dict()
    with open(path, "w") as f:
        f.write("combat_dist_v1\n")
        f.write(f"entity_dim {enc.dim}\n")
        f.write(f"hidden_dim {HIDDEN_DIM}\n")
        f.write(f"num_heads {NUM_HEADS}\n")
        f.write(f"num_layers {NUM_LAYERS}\n")
        f.write(f"win_bonus {WIN_BONUS}\n")

        # Scalar selector (indices into canonical 1766 feature vector)
        canonical = list(pd.read_csv(CSV, nrows=0).columns)
        scalar_idx = [canonical.index(c) for c in scalar_cols_in]
        f.write(f"nscalar {len(scalar_idx)}\n")
        for idx in scalar_idx:
            f.write(f" {idx}")
        f.write("\n")

        def write_vec(name, arr):
            arr = arr.detach().cpu().numpy().ravel()
            f.write(f"{name}")
            for v in arr:
                f.write(f" {v:.6g}")
            f.write("\n")

        write_vec("scalar_mean", enc.scalar_mean)
        write_vec("scalar_inv", enc.scalar_inv)
        write_vec("scalar_weight", state["encoder.scalar_encoder.0.weight"])
        write_vec("scalar_bias", state["encoder.scalar_encoder.0.bias"])
        write_vec("card_embed", enc.card_embed)
        write_vec("relic_embed", enc.relic_embed)
        write_vec("potion_embed", enc.potion_embed)
        write_vec("encounter_embed", enc.enc_embed.weight)
        write_vec("zone_pos", enc.zone_pos)
        write_vec("mon_id_embed", enc.mon_id.weight)
        write_vec("mon_intent_embed", enc.mon_intent.weight)
        write_vec("mon_cont_mean", enc.mon_cont_mean)
        write_vec("mon_cont_inv", enc.mon_cont_inv)
        write_vec("mon_enc_weight", state["encoder.mon_encoder.0.weight"])
        write_vec("mon_enc_bias", state["encoder.mon_encoder.0.bias"])

        for l, layer in enumerate(enc.layers):
            prefix = f"encoder.layers.{l}."
            write_vec(f"layer_{l}_qkv_weight", state[prefix + "attn.in_proj_weight"])
            write_vec(f"layer_{l}_qkv_bias", state[prefix + "attn.in_proj_bias"])
            write_vec(f"layer_{l}_proj_weight", state[prefix + "attn.out_proj.weight"])
            write_vec(f"layer_{l}_proj_bias", state[prefix + "attn.out_proj.bias"])
            for i, ln in enumerate(["ln1", "ln2"]):
                write_vec(f"layer_{l}_{ln}_weight", state[prefix + f"{ln}.weight"])
                write_vec(f"layer_{l}_{ln}_bias", state[prefix + f"{ln}.bias"])
            for i, part in enumerate(["0", "2"]):
                write_vec(f"layer_{l}_ffn{i+1}_weight", state[prefix + f"ffn.{part}.weight"])
                write_vec(f"layer_{l}_ffn{i+1}_bias", state[prefix + f"ffn.{part}.bias"])

        write_vec("pool_weight", state["encoder.pool_attn.weight"])
        for name in ["death_head", "win_head", "quantile_head", "potion_head", "turns_head"]:
            write_vec(f"{name}_weight", state[f"{name}.weight"])
            write_vec(f"{name}_bias", state[f"{name}.bias"])
    print(f"[export] wrote {path}", flush=True)


def validation_loss(model, val_fights, dtypes):
    """Mean loss over held-out fight rows (same chunk/sample gates as
    training). Used for best-model selection; training loss alone is not."""
    model.eval()
    vloss = 0.0
    vn = 0
    reader = pd.read_csv(CSV, chunksize=CHUNK, dtype=dtypes)
    for df in reader:
        fight_mask = np.array([(int(s), int(f)) in val_fights
                               for s, f in zip(df["seed"], df["fightIdx"])])
        df_val = df[fight_mask]
        if len(df_val) == 0:
            continue
        if mix64(df_val["seed"].values[0]) % SAMPLE_MOD != 0:
            continue
        (scalar, cards, relics, potions, enc, mids, intents, mcont, mmask,
         y_won, y_hp, max_hp, turns_rem, pot_used) = extract_entities(df_val)
        with torch.no_grad():
            for start in range(0, len(df_val), BATCH):
                end = min(start + BATCH, len(df_val))
                bs = lambda x: torch.from_numpy(x[start:end]).to(DEVICE)
                preds = model(bs(scalar), bs(cards), bs(relics), bs(potions),
                              bs(enc), bs(mids), bs(intents), bs(mcont), bs(mmask))
                loss, _ = compute_losses(preds, bs(y_won), bs(y_hp), bs(max_hp),
                                         bs(turns_rem), bs(pot_used))
                vloss += loss.item() * (end - start)
                vn += (end - start)
    model.train()
    return vloss / max(vn, 1)


def main():
    print(f"[data] loading {CSV}", flush=True)
    reader = pd.read_csv(CSV, chunksize=CHUNK, dtype=dtypes)

    # First pass: compute normalization stats
    scalar_acc = []
    mon_acc = []
    print("[norm] computing statistics...", flush=True)
    for df in reader:
        if mix64(df["seed"].values[0]) % SAMPLE_MOD != 0:
            continue
        scalar, cards, relics, potions, enc, mids, intents, mcont, mmask, yw, yh, mh, *_ = extract_entities(df)
        scalar_acc.append(scalar)
        for s in range(5):
            mask = mmask[:, s]
            if mask.any():
                mon_acc.append(mcont[mask, s, :])
    scalar_all = np.concatenate(scalar_acc)
    scalar_mean = scalar_all.mean(axis=0).astype(np.float32)
    scalar_std = scalar_all.std(axis=0).astype(np.float32) + 1e-6
    mon_cont_mean = np.concatenate(mon_acc).mean(axis=0).astype(np.float32) if mon_acc else np.zeros(7, dtype=np.float32)
    mon_cont_std = np.concatenate(mon_acc).std(axis=0).astype(np.float32) + 1e-6 if mon_acc else np.ones(7, dtype=np.float32)

    # Model
    model = CombatDistNet(ENTITY_DIM, HIDDEN_DIM, NUM_HEADS, NUM_LAYERS).to(DEVICE)
    model.encoder.scalar_mean.data = torch.from_numpy(scalar_mean).to(DEVICE)
    model.encoder.scalar_inv.data = torch.from_numpy(1.0 / scalar_std).to(DEVICE)
    model.encoder.mon_cont_mean.data = torch.from_numpy(mon_cont_mean).to(DEVICE)
    model.encoder.mon_cont_inv.data = torch.from_numpy(1.0 / mon_cont_std).to(DEVICE)

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)

    print(f"[model] {sum(p.numel() for p in model.parameters()):,} params")
    print(f"[train] {EPOCHS} epochs, batch {BATCH}", flush=True)

    # Split fights for validation
    all_fight_ids = set()
    for df in pd.read_csv(CSV, chunksize=CHUNK, usecols=["seed", "fightIdx"]):
        for s, f in zip(df["seed"], df["fightIdx"]):
            all_fight_ids.add((int(s), int(f)))
    fight_ids = sorted(all_fight_ids)
    np.random.RandomState(0).shuffle(fight_ids)
    split = int(0.9 * len(fight_ids))
    train_fights = set(fight_ids[:split])
    val_fights = set(fight_ids[split:])
    print(f"[split] train={len(train_fights)} val={len(val_fights)} fights")

    best_loss = float("inf")
    for epoch in range(EPOCHS):
        model.train()
        epoch_loss = 0.0
        epoch_n = 0
        reader = pd.read_csv(CSV, chunksize=CHUNK, dtype=dtypes)
        for df in reader:
            fight_mask = np.array([(int(s), int(f)) in train_fights
                                   for s, f in zip(df["seed"], df["fightIdx"])])
            df_train = df[fight_mask]
            if len(df_train) == 0:
                continue
            if mix64(df_train["seed"].values[0]) % SAMPLE_MOD != 0:
                continue

            (scalar, cards, relics, potions, enc, mids, intents, mcont, mmask,
             y_won, y_hp, max_hp, turns_rem, pot_used) = extract_entities(df_train)

            for start in range(0, len(df_train), BATCH):
                end = min(start + BATCH, len(df_train))
                bs = lambda x: torch.from_numpy(x[start:end]).to(DEVICE)

                preds = model(bs(scalar), bs(cards), bs(relics), bs(potions),
                              bs(enc), bs(mids), bs(intents), bs(mcont), bs(mmask))
                loss, _ = compute_losses(
                    preds, bs(y_won), bs(y_hp), bs(max_hp),
                    bs(turns_rem), bs(pot_used))

                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()

                epoch_loss += loss.item() * (end - start)
                epoch_n += (end - start)

        avg_loss = epoch_loss / max(epoch_n, 1)
        val_avg = validation_loss(model, val_fights, dtypes)
        print(f"[epoch {epoch+1}/{EPOCHS}] loss={avg_loss:.4f} "
              f"val_loss={val_avg:.4f}", flush=True)

        if val_avg < best_loss:
            best_loss = val_avg
            export_model(model, OUT, scalar_cols, mon_cont_mean)

    print(f"[done] best_val_loss={best_loss:.4f} -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
