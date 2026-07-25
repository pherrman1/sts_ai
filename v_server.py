#!/usr/bin/env python3
"""Deck-aware value-function server: holds the GBM V(state,deck) and answers
card-pick queries from the C++ agent over a TCP socket.

Wire protocol (one line each way, newline-terminated):
  request : "cand0,cand1,...;v0,v1,...\n"
            candidates = candidate card ids; v* = the rich raw features in
            featureRow()+deckCountsCsv() order (ascension..nRelics, d0..d371).
  response: "<idx>\n"   idx in 0..n-1 = take that candidate; 5 = skip.

Card value = V(deck+card) - V(deck), evaluated with the exact trained GBM.
Take the best; skip if best marginal <= SKIP_THRESHOLD (default 0).

Rest-site endpoints (same rich-feature suffix, tagged first field):
  "H;<healAmt>;<v0..v391>\n"  -> "<healGain>\n"  where
       healGain = V(deck, curHp+healAmt capped at maxHp) - V(deck, curHp).
       Value (in expected-final-floor units) of resting vs. not.
  "U;<cid0,cid1,...>;<v0,...>\n" -> "<idx>\n"  index into the candidate
       list of the card the deck values most: argmax V(deck) - V(deck-card).
       (Crude upgrade-target proxy; the model can't see per-card upgrade.)
  "RC;<v0,...>\n" -> "<delta>\n" where positive means the paired
       counterfactual model prefers rest over smith; "NA" means use HW/UW.
  "CA;<cid:up,...>;<rooms>;<edges>;<special>;<raw>\n" -> "<idx> <score>\n"
       Direct paired card/skip action model with the full 15x7 map graph.
  "PG;<child_x>;<rooms>;<edges>;<special>;<raw>\n" -> "<pwin>\n"
       Graph-aware path value for one legal immediate child subtree.
  "PA;<child_x,...>;<heuristic_x>;<rooms>;<edges>;<special>;<raw>\n"
       -> "<chosen_x> <predicted_score_advantage_vs_heuristic>\n"
       Direct paired counterfactual path-action model.
"""
import os, sys, socket, socketserver, threading

# Serving is CPU-only.  Merely exposing CUDA to PyTorch/XGBoost can create a GPU
# context even when every model is mapped to CPU, which competes with games for
# VRAM and can destabilize the NVIDIA driver under memory pressure.  Hide CUDA
# before importing either library; opt in only for an explicitly GPU-bound
# server experiment.
if os.environ.get("VSERVER_ALLOW_CUDA", "0") != "1":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

import numpy as np
import xgboost as xgb

MODEL      = os.environ.get("VMODEL", "build/v_rich_xgb.json")  # trained by train_value_rich.py
PORT       = int(os.environ.get("VPORT", "5555"))
SKIP_THR   = float(os.environ.get("VSKIP", "0.0"))    # take iff best marginal > this
NEVER_SKIP = os.environ.get("VNEVERSKIP", "0") == "1"

# ---- raw feature layout emitted by C++ vFeatCsv() == richRow() schema/order ----
# Must exactly match apps/one_combat.cpp richHeader() (minus seed prefix & labels).
SCALARS = ["ascension","act","floor","curHp","maxHp","gold","deckSize","potionChance",
           "cardRarityFactor","blueKey","greenKey","redKey","potionCount","potionCapacity",
           "bossId","nextEliteId","nextFight0","nextFight1","nextFight2","remElites",
           "remFights","monOffset","eliteOffset","pvShop","pvRest","pvEvent","pvElite",
           "pvMonster","pvTreasure","bottledAtkId","bottledSkillId","bottledPowId"]
NCARD, NRELIC, NPOT = 372, 181, 48
FWDMAP = ["fmDElite","fmDRest","fmDShop","fmDBoss","fmCElite","fmCRest","fmCShop",
          "fmCEvent","fmCMonster","fmCTreasure"]   # forward-map feats (appended last)
MAPPOS = ["curMapX","curMapY"]                     # position -> full map graph recoverable from seed+act
RAW = (SCALARS + [f"d{i}" for i in range(NCARD)] + [f"u{i}" for i in range(NCARD)]
       + [f"r{i}" for i in range(NRELIC)] + [f"pot{i}" for i in range(NPOT)] + FWDMAP + MAPPOS)  # 1017
rawpos = {n: i for i, n in enumerate(RAW)}

# Load the GPU-trained XGBoost booster. Its feature_names ARE the trained feature
# set (aggregates already dropped in train_value_xgb.py) — use them directly so
# serving matches training exactly. Predict on CPU (tiny per-pick batches).
BOOSTER = xgb.Booster()
BOOSTER.load_model(MODEL)
BOOSTER.set_param({"device": "cpu"})
FEATS = list(BOOSTER.feature_names)
missing = [c for c in FEATS if c not in rawpos]
if missing:
    sys.stderr.write(f"[v_server] FATAL: model features not in raw layout: {missing[:8]}\n")
    sys.exit(1)
fsel = [rawpos[c] for c in FEATS]           # pick model features out of the 392 raw
fmpos = {c: k for k, c in enumerate(FEATS)} # position within the model vector

# ---- optional WIN-RATE model V_win(state)->P(win), for survival/heal decisions ----
# HP has a sharp, nonlinear effect on P(win) but only a weak one on expected floor,
# so heal-vs-upgrade is decided in win-probability units (HW/UW endpoints).
WIN_MODEL = os.environ.get("VWIN", "build/v_win_xgb.json")
WIN_REQUIRED = os.environ.get("VWIN_REQUIRED", "0") == "1"
WIN_BOOSTER = None
try:
    WIN_BOOSTER = xgb.Booster(); WIN_BOOSTER.load_model(WIN_MODEL); WIN_BOOSTER.set_param({"device": "cpu"})
    WIN_FEATS = list(WIN_BOOSTER.feature_names)
    missing_win = [c for c in WIN_FEATS if c not in rawpos]
    if missing_win:
        if WIN_REQUIRED:
            raise RuntimeError(f"win-model features not in raw layout: {missing_win[:8]}")
        sys.stderr.write("[v_server] WARN: win-model features not in raw layout; disabling win model\n")
        WIN_BOOSTER = None
    else:
        win_fsel = [rawpos[c] for c in WIN_FEATS]
        win_fmpos = {c: k for k, c in enumerate(WIN_FEATS)}
except Exception as e:
    sys.stderr.write(f"[v_server] WARN: no win model ({e}); HW/UW disabled\n")
    if WIN_REQUIRED:
        sys.exit(1)

# ---- paired counterfactual rest-vs-smith model ----
# Trained directly on common-state branch outcomes. Positive output means resting
# beat smithing on the gate-aligned score; absent model cleanly falls back to the
# established V_win marginal comparison in the C++ caller.
REST_MODEL = os.environ.get("VREST", "")
REST_REQUIRED = os.environ.get("VREST_REQUIRED", "0") == "1"
REST_BOOSTER = None
if REST_MODEL:
    try:
        REST_BOOSTER = xgb.Booster(); REST_BOOSTER.load_model(REST_MODEL); REST_BOOSTER.set_param({"device": "cpu"})
        REST_FEATS = list(REST_BOOSTER.feature_names)
        missing_rest = [c for c in REST_FEATS if c not in rawpos]
        if missing_rest:
            raise RuntimeError(f"rest-model features not in raw layout: {missing_rest[:8]}")
        rest_fsel = [rawpos[c] for c in REST_FEATS]
        print(f"[v_server] loaded paired rest model {REST_MODEL}: {len(REST_FEATS)} features", flush=True)
    except Exception as e:
        sys.stderr.write(f"[v_server] WARN: no paired rest model ({e}); using V_win rest fallback\n")
        REST_BOOSTER = None
        if REST_REQUIRED:
            sys.exit(1)
# ---- optional BOSS-SURVIVAL model P(pass next act boss), for boss-aware drafting ----
# finalFloor-trained v_rich near-ignores WHICH boss is coming; v_boss is trained on
# the same rows with a boss-survival target so its card marginal is boss-conditioned.
BOSS_MODEL = os.environ.get("VBOSS", "build/v_boss_xgb.json")
BOSS_BOOSTER = None
try:
    BOSS_BOOSTER = xgb.Booster(); BOSS_BOOSTER.load_model(BOSS_MODEL); BOSS_BOOSTER.set_param({"device": "cpu"})
    BOSS_FEATS = list(BOSS_BOOSTER.feature_names)
    if [c for c in BOSS_FEATS if c not in rawpos]:
        sys.stderr.write("[v_server] WARN: boss-model features not in raw layout; disabling boss model\n")
        BOSS_BOOSTER = None
    else:
        boss_fsel = [rawpos[c] for c in BOSS_FEATS]
        boss_fmpos = {c: k for k, c in enumerate(BOSS_FEATS)}
        BOSS_HAS_DSZ = "deckSize" in boss_fmpos
        print(f"[v_server] loaded boss model {BOSS_MODEL}: {len(BOSS_FEATS)} features", flush=True)
except Exception as e:
    sys.stderr.write(f"[v_server] WARN: no boss model ({e}); CB blend disabled\n")

# ---- optional DECK-SET NN win model V_win_nn(state)->P(win), for synergy-aware drafting ----
# DeepSets card embeddings model deck synergies the trees can't; ties GBM on absolute AUC
# (0.75) but its card MARGINAL can depend on deck composition. Served for the CN op (pure NN
# or blended with the v_win GBM marginal). train_deckset is import-safe (defines DeckSet only).
NN_MODEL = os.environ.get("VNN", "build/v_deckset.pt")
NN = None
try:
    import torch
    from train_deckset import DeckSet, SCALARS as NN_SCALARS, NCARDS as NN_NCARD, NRELICS as NN_NREL, NPOT as NN_NPOT
    _ck = torch.load(NN_MODEL, map_location="cpu", weights_only=False)
    NN = DeckSet(nboss=_ck["nboss"]); NN.load_state_dict(_ck["state"]); NN.eval()
    torch.set_num_threads(2)
    NN_SMU = np.asarray(_ck["smu"], np.float32); NN_SSD = np.asarray(_ck["ssd"], np.float32)
    nn_d   = [rawpos[f"d{i}"]   for i in range(NN_NCARD)]
    nn_u   = [rawpos[f"u{i}"]   for i in range(NN_NCARD)]
    nn_r   = [rawpos[f"r{i}"]   for i in range(NN_NREL)]
    nn_pot = [rawpos[f"pot{i}"] for i in range(NN_NPOT)]
    nn_scl = [rawpos[c] for c in NN_SCALARS]
    nn_boss = rawpos["bossId"]; nn_hp = rawpos["curHp"]; nn_mhp = rawpos["maxHp"]
    print(f"[v_server] loaded deck-set NN {NN_MODEL}: nboss={_ck['nboss']}", flush=True)
except Exception as e:
    sys.stderr.write(f"[v_server] WARN: no deck-set NN ({e}); CN op disabled\n")
    NN = None

def _nn_predict(raws):
    """raws: (B, RAWLEN) float64 -> P(win) per row via the deck-set NN."""
    d = raws[:, nn_d].astype(np.float32); u = raws[:, nn_u].astype(np.float32)
    nonup = np.clip(d - u, 0, None)
    rel = (raws[:, nn_r] > 0).astype(np.float32); pot = raws[:, nn_pot].astype(np.float32)
    boss = raws[:, nn_boss].astype(np.int64)
    scl = raws[:, nn_scl].astype(np.float32)
    hpf = (raws[:, nn_hp] / np.maximum(raws[:, nn_mhp], 1)).astype(np.float32)[:, None]
    scl = (np.concatenate([scl, hpf], 1) - NN_SMU) / NN_SSD
    with LOCK, torch.no_grad():
        o = NN(torch.from_numpy(nonup), torch.from_numpy(u), torch.from_numpy(rel),
               torch.from_numpy(pot), torch.from_numpy(boss), torch.from_numpy(scl))
        return torch.sigmoid(o).numpy()

def decide_nn(cands, raw, w):
    """Card pick by deck-set NN P(win) marginal, optionally blended with the v_win GBM
    marginal: marg = w*NN + (1-w)*GBM (both P(win) scale). Returns '<idx> <marginal>'."""
    if NN is None:
        return decide_win(cands, raw) if WIN_BOOSTER is not None else "5 -999.0"
    rows = [raw.copy()]
    for c in cands:
        r = raw.copy(); r[rawpos[f"d{c}"]] += 1.0; r[rawpos["deckSize"]] += 1.0
        rows.append(r)
    pnn = _nn_predict(np.stack(rows))
    marg = pnn[1:] - pnn[0]
    if w < 1.0 and WIN_BOOSTER is not None:
        base = raw[win_fsel].astype(np.float32)
        pw = WIN_BOOSTER.predict(xgb.DMatrix(np.stack([base] + [add_card_win(base, c) for c in cands]),
                                             feature_names=WIN_FEATS))
        marg = w * marg + (1.0 - w) * (pw[1:] - pw[0])
    best = int(np.argmax(marg))
    return f"{best} {float(marg[best]):.6f}"

HAS_DECKSIZE = "deckSize" in fmpos
LOCK = threading.Lock()
print(f"[v_server] loaded {MODEL}: {len(FEATS)} features "
      f"({sum(1 for c in FEATS if c[0]=='d' and c[1:].isdigit())} card-id counts)", flush=True)

# ---- optional joint entity-aware meta model (floor + win heads) -----------
# Opt-in only: VMETA_NN=/path/prefix loads prefix.torchscript + prefix.npz.
# It can replace the floor and win predictors independently through the existing
# protocol; the XGBoost models remain loaded for unsupported auxiliary endpoints.
META_PREFIX = os.environ.get("VMETA_NN", "")
META_ENTITY = None
META_USE_FLOOR = os.environ.get("VMETA_FLOOR", "1") != "0"
META_USE_WIN = os.environ.get("VMETA_WIN", "1") != "0"
if META_PREFIX:
    try:
        import torch
        META_ENTITY = torch.jit.load(META_PREFIX + ".torchscript", map_location="cpu")
        META_ENTITY.eval(); torch.set_num_threads(2)
        _mn = np.load(META_PREFIX + ".npz")
        META_SCALAR_COLS = [str(x) for x in _mn["scalar_cols"]]
        META_SCALAR_MEAN = _mn["scalar_mean"].astype(np.float32)
        META_SCALAR_INV = _mn["scalar_inv"].astype(np.float32)
        meta_scalar_idx = [rawpos[c] for c in META_SCALAR_COLS]
        meta_deck_idx = [rawpos[f"d{i}"] for i in range(372)]
        meta_upgrade_idx = [rawpos[f"u{i}"] for i in range(372)]
        meta_relic_idx = [rawpos[f"r{i}"] for i in range(181)]
        meta_potion_idx = [rawpos[f"pot{i}"] for i in range(48)]
        meta_encounter_idx = [rawpos[c] for c in
                              ("bossId", "nextEliteId", "nextFight0", "nextFight1", "nextFight2")]
        meta_bottle_idx = [rawpos[c] for c in
                           ("bottledAtkId", "bottledSkillId", "bottledPowId")]
        print(f"[v_server] loaded joint entity meta NN {META_PREFIX}: "
              f"{len(META_SCALAR_COLS)} scalars + entity pools "
              f"(floor={META_USE_FLOOR}, win={META_USE_WIN})", flush=True)
    except Exception as e:
        sys.stderr.write(f"[v_server] WARN: no joint entity meta NN ({e}); using trees\n")
        META_ENTITY = None

# Optional action-conditioned next-combat model.  It consumes the complete
# 1017-feature rich OOC state plus one-hot GameAction bits and predicts the
# expected next-combat win probability and surviving HP fraction.
OOC_ACTION_PREFIX = os.environ.get("VOOC_ACTION", "")
OOC_ACTION = None
OOC_ACTION_MEAN = None
OOC_ACTION_INV = None
if OOC_ACTION_PREFIX:
    try:
        import torch
        OOC_ACTION = torch.jit.load(OOC_ACTION_PREFIX + ".torchscript", map_location="cpu")
        OOC_ACTION.eval()
        _oa = torch.load(OOC_ACTION_PREFIX + ".pt", map_location="cpu", weights_only=False)
        OOC_ACTION_MEAN = _oa["mean"].astype(np.float32)
        OOC_ACTION_INV = _oa["inv"].astype(np.float32)
        print(f"[v_server] loaded OOC next-combat action NN {OOC_ACTION_PREFIX}", flush=True)
    except Exception as e:
        sys.stderr.write(f"[v_server] WARN: no OOC action NN ({e})\n")
        OOC_ACTION = None

# Checkpoint-oracle distilled utility model (single-score output, no win/hp split)
OOC_CHECKPOINT_PREFIX = os.environ.get("VOOC_CHECKPOINT", "")
OOC_CHECKPOINT = None
OOC_CHECKPOINT_MEAN = None
OOC_CHECKPOINT_INV = None
if OOC_CHECKPOINT_PREFIX:
    try:
        import torch
        OOC_CHECKPOINT = torch.jit.load(OOC_CHECKPOINT_PREFIX + ".torchscript", map_location="cpu")
        OOC_CHECKPOINT.eval()
        _oc = torch.load(OOC_CHECKPOINT_PREFIX + ".pt", map_location="cpu", weights_only=False)
        OOC_CHECKPOINT_MEAN = _oc["mean"].astype(np.float32)
        OOC_CHECKPOINT_INV = _oc["inv"].astype(np.float32)
        print(f"[v_server] loaded OOC checkpoint utility NN {OOC_CHECKPOINT_PREFIX}", flush=True)
    except Exception as e:
        sys.stderr.write(f"[v_server] WARN: no OOC checkpoint NN ({e})\n")
        OOC_CHECKPOINT = None

def decide_ooc_action(action_bits, screen, act, raw):
    if OOC_CHECKPOINT is not None:
        bits = np.asarray([[(int(x) >> i) & 1 for i in range(32)] for x in action_bits], dtype=np.float32)
        x = np.clip((np.asarray(raw, dtype=np.float32)[None, :] - OOC_CHECKPOINT_MEAN) * OOC_CHECKPOINT_INV, -8, 8)
        x = np.repeat(x, len(action_bits), axis=0)
        screens = np.full(len(action_bits), np.clip(int(screen), 0, 15), dtype=np.int64)
        acts = np.full(len(action_bits), np.clip(int(act), 0, 3), dtype=np.int64)
        import torch
        with torch.no_grad():
            scores = OOC_CHECKPOINT(torch.from_numpy(x), torch.from_numpy(bits),
                                    torch.from_numpy(screens), torch.from_numpy(acts))
        s = scores.numpy().ravel()
        return " ".join(f"{float(v):.8f},0.0" for v in s)
    if OOC_ACTION is None:
        return ""
    bits = np.asarray([[(int(x) >> i) & 1 for i in range(32)] for x in action_bits], dtype=np.float32)
    x = np.clip((np.asarray(raw, dtype=np.float32)[None, :] - OOC_ACTION_MEAN) * OOC_ACTION_INV, -8, 8)
    x = np.repeat(x, len(action_bits), axis=0)
    screens = np.full(len(action_bits), np.clip(int(screen), 0, 15), dtype=np.int64)
    acts = np.full(len(action_bits), np.clip(int(act), 0, 3), dtype=np.int64)
    import torch
    with torch.no_grad():
        wl, hp = OOC_ACTION(torch.from_numpy(x), torch.from_numpy(bits),
                            torch.from_numpy(screens), torch.from_numpy(acts))
    pwin = torch.sigmoid(wl).numpy()
    hpfrac = hp.numpy()
    return " ".join(f"{float(w):.8f},{float(h):.8f}" for w, h in zip(pwin, hpfrac))

# Encounter-conditioned version used by the multi-checkpoint evaluator.  It
# preserves the candidate OOC action but scores a specified possible encounter
# rather than collapsing the encounter distribution first.
OOC_ENCOUNTER_PREFIX = os.environ.get("VOOC_ENCOUNTER", "")
OOC_ENCOUNTER = None
OOC_ENCOUNTER_MEAN = None
OOC_ENCOUNTER_INV = None
if OOC_ENCOUNTER_PREFIX:
    try:
        import torch
        OOC_ENCOUNTER = torch.jit.load(OOC_ENCOUNTER_PREFIX + ".torchscript", map_location="cpu")
        OOC_ENCOUNTER.eval()
        _oe = torch.load(OOC_ENCOUNTER_PREFIX + ".pt", map_location="cpu", weights_only=False)
        OOC_ENCOUNTER_MEAN = _oe["mean"].astype(np.float32)
        OOC_ENCOUNTER_INV = _oe["inv"].astype(np.float32)
        print(f"[v_server] loaded OOC encounter-conditioned NN {OOC_ENCOUNTER_PREFIX}", flush=True)
    except Exception as e:
        sys.stderr.write(f"[v_server] WARN: no OOC encounter NN ({e})\n")
        OOC_ENCOUNTER = None

def decide_ooc_encounter(action_bits, encounters, screen, act, raw):
    if OOC_ENCOUNTER is None:
        return ""
    n = len(encounters)
    bits = np.asarray([[(int(x) >> i) & 1 for i in range(32)] for x in action_bits], dtype=np.float32)
    x = np.clip((np.asarray(raw, dtype=np.float32)[None, :] - OOC_ENCOUNTER_MEAN) * OOC_ENCOUNTER_INV, -8, 8)
    x = np.repeat(x, n, axis=0)
    screens = np.full(n, np.clip(int(screen), 0, 15), dtype=np.int64)
    acts = np.full(n, np.clip(int(act), 0, 3), dtype=np.int64)
    enc = np.clip(np.asarray(encounters, dtype=np.int64), 0, 127)
    import torch
    with torch.no_grad():
        wl, hp = OOC_ENCOUNTER(torch.from_numpy(x), torch.from_numpy(bits),
                               torch.from_numpy(screens), torch.from_numpy(acts),
                               torch.from_numpy(enc))
    return " ".join(f"{float(w):.8f},{float(h):.8f}" for w, h in zip(torch.sigmoid(wl).numpy(), hp.numpy()))

def _meta_predict(raws):
    """Return (P(win), expected final floor) for canonical RAW rows."""
    a = np.asarray(raws, dtype=np.float32)
    scalar = (a[:, meta_scalar_idx] - META_SCALAR_MEAN) * META_SCALAR_INV
    deck = a[:, meta_deck_idx].astype(np.uint8)
    upgrades = a[:, meta_upgrade_idx].astype(np.uint8)
    relics = np.maximum(a[:, meta_relic_idx], 0).astype(np.float32)
    potions = np.maximum(a[:, meta_potion_idx], 0).astype(np.float32)
    encounters = np.clip(a[:, meta_encounter_idx].astype(np.int64)+1, 0, 127).astype(np.uint8)
    bottles = np.clip(a[:, meta_bottle_idx].astype(np.int64)+1, 0, 372).astype(np.int16)
    with LOCK, torch.no_grad():
        wl, pl = META_ENTITY(torch.from_numpy(scalar), torch.from_numpy(deck),
                             torch.from_numpy(upgrades), torch.from_numpy(relics),
                             torch.from_numpy(potions), torch.from_numpy(encounters),
                             torch.from_numpy(bottles))
        pwin = torch.sigmoid(wl).numpy()
        progress = torch.sigmoid(pl).numpy()
    floor = a[:, rawpos["floor"]]
    return pwin, floor + (51.0-floor)*progress

def _meta_floor_predict(rows):
    return _meta_predict(np.stack(rows))[1]

def _meta_win_predict(rows):
    return _meta_predict(np.stack(rows))[0]

def _raw_add_card(raw, cid):
    out = raw.copy(); out[rawpos[f"d{cid}"]] += 1.0; out[rawpos["deckSize"]] += 1.0
    return out

def _raw_remove_card(raw, cid):
    out = raw.copy(); out[rawpos[f"d{cid}"]] -= 1.0; out[rawpos["deckSize"]] -= 1.0
    return out

def _raw_upgrade_card(raw, cid):
    out = raw.copy(); out[rawpos[f"u{cid}"]] += 1.0
    return out

# ---- optional direct paired card-action model, including full map graph -----
# CA;<cid:up,...>;<105 rooms>;<105 edge masks>;<105 burning flags>;<RAW>
CARD_ACTION_PREFIX = os.environ.get("VCARD_ACTION", "")
CARD_ACTION_REQUIRED = os.environ.get("VCARD_ACTION_REQUIRED", "0") == "1"
# Kept opt-in: the card-action value remains the default selector while the
# simulator-derived future-fight head is validated in gameplay.  A positive
# value adds W * min(P(next combat), P(next boss)) to each action score.
CARD_ACTION_SURVIVAL_W = float(os.environ.get("VCARD_ACTION_SURVIVAL_W", "0"))
CARD_ACTION = None
if CARD_ACTION_PREFIX:
    try:
        import torch
        CARD_ACTION = torch.jit.load(CARD_ACTION_PREFIX + ".torchscript", map_location="cpu")
        CARD_ACTION.eval(); torch.set_num_threads(2)
        _ca = np.load(CARD_ACTION_PREFIX + ".npz")
        CARD_ACTION_SCALARS = [str(x) for x in _ca["scalar_cols"]]
        CARD_ACTION_MEAN = _ca["scalar_mean"].astype(np.float32)
        CARD_ACTION_INV = _ca["scalar_inv"].astype(np.float32)
        ca_scalar_idx = [rawpos[c] for c in CARD_ACTION_SCALARS]
        ca_deck_idx = [rawpos[f"d{i}"] for i in range(372)]
        ca_upgrade_idx = [rawpos[f"u{i}"] for i in range(372)]
        ca_relic_idx = [rawpos[f"r{i}"] for i in range(181)]
        ca_potion_idx = [rawpos[f"pot{i}"] for i in range(48)]
        ca_encounter_idx = [rawpos[c] for c in
                            ("bossId", "nextEliteId", "nextFight0", "nextFight1", "nextFight2")]
        ca_bottle_idx = [rawpos[c] for c in
                         ("bottledAtkId", "bottledSkillId", "bottledPowId")]
        print(f"[v_server] loaded paired card-action NN {CARD_ACTION_PREFIX}: "
              f"{len(CARD_ACTION_SCALARS)} scalars + full map graph", flush=True)
    except Exception as e:
        sys.stderr.write(f"[v_server] WARN: no paired card-action NN ({e}); CA disabled\n")
        CARD_ACTION = None
        if CARD_ACTION_REQUIRED:
            sys.exit(1)

def decide_card_action(candidates, raw, rooms, edges, special):
    """Choose among offered (card id, upgraded) actions and the learned skip."""
    if CARD_ACTION is None:
        return "5 -999.0"
    if len(rooms) != 105 or len(edges) != 105 or len(special) != 105:
        raise ValueError("CA map tensors must each contain exactly 105 nodes")
    a = raw[None].astype(np.float32)
    scalar = (a[:, ca_scalar_idx] - CARD_ACTION_MEAN) * CARD_ACTION_INV
    deck = a[:, ca_deck_idx].astype(np.uint8)
    upgrades = a[:, ca_upgrade_idx].astype(np.uint8)
    relics = np.maximum(a[:, ca_relic_idx], 0).astype(np.float32)
    potions = np.maximum(a[:, ca_potion_idx], 0).astype(np.float32)
    encounters = np.clip(a[:, ca_encounter_idx].astype(np.int64)+1, 0, 127).astype(np.uint8)
    bottles = np.clip(a[:, ca_bottle_idx].astype(np.int64)+1, 0, 372).astype(np.int16)
    # Candidate id 0 is reserved for skip; real card ids are shifted by one.
    candidate = np.asarray([[cid+1 for cid, _ in candidates] + [0]], dtype=np.int64)
    candidate_up = np.asarray([[up for _, up in candidates] + [0]], dtype=np.int64)
    action_mask = np.ones_like(candidate, dtype=bool)
    map_position = a[:, [rawpos["curMapX"], rawpos["curMapY"]]].astype(np.int16)
    with LOCK, torch.no_grad():
        output = CARD_ACTION(
            torch.from_numpy(scalar), torch.from_numpy(deck), torch.from_numpy(upgrades),
            torch.from_numpy(relics), torch.from_numpy(potions), torch.from_numpy(encounters),
            torch.from_numpy(bottles), torch.from_numpy(candidate), torch.from_numpy(candidate_up),
            torch.from_numpy(action_mask), torch.from_numpy(np.asarray(rooms, dtype=np.uint8)[None]),
            torch.from_numpy(np.asarray(edges, dtype=np.uint8)[None]),
            torch.from_numpy(np.asarray(special, dtype=np.uint8)[None]), torch.from_numpy(map_position))
    if isinstance(output, tuple):
        q = output[0][0].numpy()
        if CARD_ACTION_SURVIVAL_W:
            survival = torch.sigmoid(output[1][0]).numpy()
            # Elite routing is optional, so it remains diagnostic rather than
            # a hard constraint. Every run must clear its next battle and boss.
            q = q + CARD_ACTION_SURVIVAL_W * np.minimum(survival[:, 0], survival[:, 2])
    else:
        q = output[0].numpy()
    best = int(np.argmax(q))
    return f"{5 if best == len(candidates) else best} {float(q[best]*10.0):.6f}"

# ---- optional graph-aware path state value -------------------------------
# PG;<chosen child x>;<rooms>;<edges>;<special>;<RAW> -> P(run win)
PATH_GRAPH_PREFIX = os.environ.get("VPATH_GRAPH", "")
PATH_GRAPH_REQUIRED = os.environ.get("VPATH_GRAPH_REQUIRED", "0") == "1"
PATH_GRAPH = None
if PATH_GRAPH_PREFIX:
    try:
        import torch
        PATH_GRAPH = torch.jit.load(PATH_GRAPH_PREFIX + ".torchscript", map_location="cpu")
        PATH_GRAPH.eval(); torch.set_num_threads(2)
        _pg = np.load(PATH_GRAPH_PREFIX + ".npz")
        PATH_GRAPH_SCALARS = [str(x) for x in _pg["scalar_cols"]]
        PATH_GRAPH_MEAN = _pg["scalar_mean"].astype(np.float32)
        PATH_GRAPH_INV = _pg["scalar_inv"].astype(np.float32)
        pg_scalar_idx = [rawpos[c] for c in PATH_GRAPH_SCALARS]
        pg_deck_idx = [rawpos[f"d{i}"] for i in range(372)]
        pg_upgrade_idx = [rawpos[f"u{i}"] for i in range(372)]
        pg_relic_idx = [rawpos[f"r{i}"] for i in range(181)]
        pg_potion_idx = [rawpos[f"pot{i}"] for i in range(48)]
        pg_encounter_idx = [rawpos[c] for c in
                            ("bossId", "nextEliteId", "nextFight0", "nextFight1", "nextFight2")]
        pg_bottle_idx = [rawpos[c] for c in
                         ("bottledAtkId", "bottledSkillId", "bottledPowId")]
        print(f"[v_server] loaded graph path NN {PATH_GRAPH_PREFIX}: "
              f"{len(PATH_GRAPH_SCALARS)} scalars + full map graph", flush=True)
    except Exception as e:
        sys.stderr.write(f"[v_server] WARN: no graph path NN ({e}); PG disabled\n")
        PATH_GRAPH = None
        if PATH_GRAPH_REQUIRED:
            sys.exit(1)

def path_graph_value(chosen_x, raw, rooms, edges, special):
    if PATH_GRAPH is None:
        return 0.5
    if len(rooms) != 105 or len(edges) != 105 or len(special) != 105:
        raise ValueError("PG map tensors must each contain exactly 105 nodes")
    a = raw[None].astype(np.float32)
    scalar = (a[:, pg_scalar_idx] - PATH_GRAPH_MEAN) * PATH_GRAPH_INV
    position = np.asarray([[int(raw[rawpos["curMapX"]]), int(raw[rawpos["curMapY"]]),
                            chosen_x]], dtype=np.int16)
    with LOCK, torch.no_grad():
        wl, _ = PATH_GRAPH(
            torch.from_numpy(scalar),
            torch.from_numpy(a[:, pg_deck_idx].astype(np.uint8)),
            torch.from_numpy(a[:, pg_upgrade_idx].astype(np.uint8)),
            torch.from_numpy(np.maximum(a[:, pg_relic_idx], 0).astype(np.float32)),
            torch.from_numpy(np.maximum(a[:, pg_potion_idx], 0).astype(np.float32)),
            torch.from_numpy(np.clip(a[:, pg_encounter_idx].astype(np.int64)+1, 0, 127).astype(np.uint8)),
            torch.from_numpy(np.clip(a[:, pg_bottle_idx].astype(np.int64)+1, 0, 372).astype(np.int16)),
            torch.from_numpy(np.asarray(rooms, dtype=np.uint8)[None]),
            torch.from_numpy(np.asarray(edges, dtype=np.uint8)[None]),
            torch.from_numpy(np.asarray(special, dtype=np.uint8)[None]), torch.from_numpy(position))
    return float(torch.sigmoid(wl)[0])

# ---- direct paired path-action model --------------------------------------
# PA;<candidate x,...>;<rooms>;<edges>;<special>;<RAW> -> chosen child x
PATH_ACTION_PREFIX = os.environ.get("VPATH_ACTION", "")
PATH_ACTION_REQUIRED = os.environ.get("VPATH_ACTION_REQUIRED", "0") == "1"
PATH_ACTION = None
if PATH_ACTION_PREFIX:
    try:
        import torch
        PATH_ACTION = torch.jit.load(PATH_ACTION_PREFIX + ".torchscript", map_location="cpu")
        PATH_ACTION.eval(); torch.set_num_threads(2)
        _pa = np.load(PATH_ACTION_PREFIX + ".npz")
        PATH_ACTION_SCALARS = [str(x) for x in _pa["scalar_cols"]]
        PATH_ACTION_MEAN = _pa["scalar_mean"].astype(np.float32)
        PATH_ACTION_INV = _pa["scalar_inv"].astype(np.float32)
        pa_scalar_idx = [rawpos[c] for c in PATH_ACTION_SCALARS]
        pa_deck_idx = [rawpos[f"d{i}"] for i in range(372)]
        pa_upgrade_idx = [rawpos[f"u{i}"] for i in range(372)]
        pa_relic_idx = [rawpos[f"r{i}"] for i in range(181)]
        pa_potion_idx = [rawpos[f"pot{i}"] for i in range(48)]
        pa_encounter_idx = [rawpos[c] for c in
                            ("bossId", "nextEliteId", "nextFight0", "nextFight1", "nextFight2")]
        pa_bottle_idx = [rawpos[c] for c in
                         ("bottledAtkId", "bottledSkillId", "bottledPowId")]
        print(f"[v_server] loaded direct path-action NN {PATH_ACTION_PREFIX}: "
              f"{len(PATH_ACTION_SCALARS)} scalars + candidate subtrees", flush=True)
    except Exception as e:
        sys.stderr.write(f"[v_server] WARN: no direct path-action NN ({e}); PA disabled\n")
        PATH_ACTION = None
        if PATH_ACTION_REQUIRED:
            sys.exit(1)

def decide_path_action(candidates, raw, rooms, edges, special):
    if PATH_ACTION is None or not candidates:
        return -1, np.full(len(candidates), -1e9, dtype=np.float32)
    if len(rooms) != 105 or len(edges) != 105 or len(special) != 105:
        raise ValueError("PA map tensors must each contain exactly 105 nodes")
    a = raw[None].astype(np.float32)
    scalar = (a[:, pa_scalar_idx] - PATH_ACTION_MEAN) * PATH_ACTION_INV
    candidate = np.asarray(candidates, dtype=np.int64)[None]
    action_mask = np.ones_like(candidate, dtype=bool)
    position = np.asarray([[int(raw[rawpos["curMapX"]]), int(raw[rawpos["curMapY"]])]],
                          dtype=np.int16)
    with LOCK, torch.no_grad():
        q = PATH_ACTION(
            torch.from_numpy(scalar),
            torch.from_numpy(a[:, pa_deck_idx].astype(np.uint8)),
            torch.from_numpy(a[:, pa_upgrade_idx].astype(np.uint8)),
            torch.from_numpy(np.maximum(a[:, pa_relic_idx], 0).astype(np.float32)),
            torch.from_numpy(np.maximum(a[:, pa_potion_idx], 0).astype(np.float32)),
            torch.from_numpy(np.clip(a[:, pa_encounter_idx].astype(np.int64)+1, 0, 127).astype(np.uint8)),
            torch.from_numpy(np.clip(a[:, pa_bottle_idx].astype(np.int64)+1, 0, 372).astype(np.int16)),
            torch.from_numpy(np.asarray(rooms, dtype=np.uint8)[None]),
            torch.from_numpy(np.asarray(edges, dtype=np.uint8)[None]),
            torch.from_numpy(np.asarray(special, dtype=np.uint8)[None]), torch.from_numpy(position),
            torch.from_numpy(candidate), torch.from_numpy(action_mask))[0].numpy()
    best = int(np.argmax(q))
    # Report predicted paired-score advantage over the deployed heuristic
    # separately; C++ may use it as a conservative intervention threshold.
    return int(candidates[best]), q

def add_card(vec, cid):
    """vec: (F,) model-ordered features -> copy with one card cid added.
    Aggregates were dropped in training, so this bumps only the card's own
    per-id count d{cid} (+ deckSize if the model kept it)."""
    out = vec.copy()
    if HAS_DECKSIZE: out[fmpos["deckSize"]] += 1.0
    dn = f"d{cid}"
    if dn in fmpos: out[fmpos[dn]] += 1.0
    return out

def decide(cands, raw):
    """Return "<best_idx> <best_marginal>": the argmax-marginal card and its
    V(deck+card)-V(deck) in final-floor units. The CALLER applies the skip
    threshold (so it can be swept without restarting the server)."""
    if META_ENTITY is not None and META_USE_FLOOR:
        rows = [raw.astype(np.float32)] + [_raw_add_card(raw, c).astype(np.float32) for c in cands]
        pred = _meta_floor_predict(rows)
        marg = pred[1:] - pred[0]
        best = int(np.argmax(marg))
        return f"{best} {float(marg[best]):.5f}"
    base = raw[fsel].astype(np.float32)          # model-ordered base state
    rows = np.stack([base] + [add_card(base, c) for c in cands])
    with LOCK:
        pred = BOOSTER.predict(xgb.DMatrix(rows, feature_names=FEATS))
    marg = pred[1:] - pred[0]                     # V(deck+card) - V(deck)
    best = int(np.argmax(marg))
    return f"{best} {float(marg[best]):.5f}"

def _boss_add_card(vec, cid):
    out = vec.copy()
    if BOSS_HAS_DSZ: out[boss_fmpos["deckSize"]] += 1.0
    dn = f"d{cid}"
    if dn in boss_fmpos: out[boss_fmpos[dn]] += 1.0
    return out

def _zscore(a):
    a = np.asarray(a, dtype=np.float64); s = a.std()
    return (a - a.mean()) / s if s > 1e-9 else a - a.mean()

def decide_boss_blend(cands, raw, w):
    """Near-boss card pick blending v_rich and v_boss marginals. The two are on
    DIFFERENT scales (floors vs probability), so each marginal vector is
    z-normalized across the candidate set, then blended (1-w)*zr + w*zb and
    argmax'd. Returns '<best_idx> <v_rich_marginal[best]>' -- the floor-scale
    marginal -- so the caller's existing skip threshold still applies. Falls back
    to plain v_rich when the boss model is missing or there's <2 candidates."""
    base = raw[fsel].astype(np.float32)
    rows = np.stack([base] + [add_card(base, c) for c in cands])
    with LOCK:
        pred = BOOSTER.predict(xgb.DMatrix(rows, feature_names=FEATS))
    mr = pred[1:] - pred[0]                        # v_rich marginals (floor units)
    if BOSS_BOOSTER is None or len(cands) < 2:
        best = int(np.argmax(mr)); return f"{best} {float(mr[best]):.5f}"
    bbase = raw[boss_fsel].astype(np.float32)
    brows = np.stack([bbase] + [_boss_add_card(bbase, c) for c in cands])
    with LOCK:
        bpred = BOSS_BOOSTER.predict(xgb.DMatrix(brows, feature_names=BOSS_FEATS))
    mb = bpred[1:] - bpred[0]                       # v_boss marginals (P(pass boss))
    blended = (1.0 - w) * _zscore(mr) + w * _zscore(mb)
    best = int(np.argmax(blended))
    return f"{best} {float(mr[best]):.5f}"          # floor-scale marginal for skip logic

def marginals(cands, raw):
    """Return all candidates' marginal V(deck+card)-V(deck) as space-separated
    floats (final-floor units). Lets the caller softmax-sample for datagen spread."""
    if META_ENTITY is not None and META_USE_FLOOR:
        rows = [raw.astype(np.float32)] + [_raw_add_card(raw, c).astype(np.float32) for c in cands]
        pred = _meta_floor_predict(rows); marg = pred[1:] - pred[0]
        return " ".join(f"{float(m):.5f}" for m in marg)
    base = raw[fsel].astype(np.float32)
    rows = np.stack([base] + [add_card(base, c) for c in cands])
    with LOCK:
        pred = BOOSTER.predict(xgb.DMatrix(rows, feature_names=FEATS))
    marg = pred[1:] - pred[0]
    return " ".join(f"{float(m):.5f}" for m in marg)

def remove_card(raw, cid):
    """raw: (392,) -> model-ordered features with one card cid removed.
    Mirror of add_card: drop the per-id count (+ deckSize if kept)."""
    base = raw[fsel].astype(np.float32)
    out = base.copy()
    if HAS_DECKSIZE: out[fmpos["deckSize"]] -= 1.0
    dn = f"d{cid}"
    if dn in fmpos: out[fmpos[dn]] -= 1.0
    return out

def heal_gain(heal_amt, raw):
    """V(deck, curHp+heal capped) - V(deck, curHp), in final-floor units."""
    if META_ENTITY is not None and META_USE_FLOOR:
        hi = raw.astype(np.float32).copy()
        hi[rawpos["curHp"]] = min(hi[rawpos["maxHp"]], hi[rawpos["curHp"]] + heal_amt)
        pred = _meta_floor_predict([raw.astype(np.float32), hi])
        return float(pred[1]-pred[0])
    base = raw[fsel].astype(np.float32)
    if "curHp" not in fmpos:                       # model can't see HP -> no signal
        return 0.0
    hi = base.copy()
    cur = base[fmpos["curHp"]]
    mx  = base[fmpos["maxHp"]] if "maxHp" in fmpos else cur + heal_amt
    hi[fmpos["curHp"]] = min(mx, cur + heal_amt)
    with LOCK:
        pred = BOOSTER.predict(xgb.DMatrix(np.stack([base, hi]), feature_names=FEATS))
    return float(pred[1] - pred[0])

def upgrade_pick(cands, raw):
    """Index of the card whose UPGRADE most raises V: argmax V(deck,u{cid}+1)-V(deck).
    Uses the rich model's per-card upgrade features u* = the TRUE upgrade marginal
    (upgrading a card != how much the deck values its presence). Cards whose u*
    feature was dropped (never upgraded in training) show 0 gain; if every candidate
    is like that we fall back to the old 'most-valued card' proxy so we still act."""
    if META_ENTITY is not None and META_USE_FLOOR:
        rows = [raw.astype(np.float32)] + [_raw_upgrade_card(raw, c).astype(np.float32) for c in cands]
        pred = _meta_floor_predict(rows); gain = pred[1:]-pred[0]
        if np.max(np.abs(gain)) < 1e-6:
            rows = [raw.astype(np.float32)] + [_raw_remove_card(raw, c).astype(np.float32) for c in cands]
            pred = _meta_floor_predict(rows); gain = pred[0]-pred[1:]
        return int(np.argmax(gain))
    base = raw[fsel].astype(np.float32)
    rows = [base]
    for c in cands:
        r = base.copy()
        un = f"u{c}"
        if un in fmpos: r[fmpos[un]] += 1.0
        rows.append(r)
    with LOCK:
        pred = BOOSTER.predict(xgb.DMatrix(np.stack(rows), feature_names=FEATS))
    gain = pred[1:] - pred[0]                       # V(deck, card upgraded) - V(deck)
    if np.max(np.abs(gain)) < 1e-6:                 # no upgrade signal -> proxy fallback
        rows = np.stack([base] + [remove_card(raw, c) for c in cands])
        with LOCK:
            pred = BOOSTER.predict(xgb.DMatrix(rows, feature_names=FEATS))
        gain = pred[0] - pred[1:]                   # V(deck) - V(deck-card)
    return int(np.argmax(gain))

def worst_pick(cands, raw):
    """Index of the card whose REMOVAL helps most: argmax V(deck-card) - V(deck).
    Used to choose the target of a shop/rest card-removal."""
    if META_ENTITY is not None and META_USE_FLOOR:
        rows = [raw.astype(np.float32)] + [_raw_remove_card(raw, c).astype(np.float32) for c in cands]
        pred = _meta_floor_predict(rows); return int(np.argmax(pred[1:]-pred[0]))
    base = raw[fsel].astype(np.float32)
    rows = np.stack([base] + [remove_card(raw, c) for c in cands])
    with LOCK:
        pred = BOOSTER.predict(xgb.DMatrix(rows, feature_names=FEATS))
    gain = pred[1:] - pred[0]                        # V(deck-card) - V(deck)
    return int(np.argmax(gain))

# ---- win-rate (survival) endpoints: heal / upgrade decided in P(win) units ----
def _win_predict(rows):
    if META_ENTITY is not None and META_USE_WIN:
        return _meta_win_predict(rows)
    with LOCK:
        return WIN_BOOSTER.predict(xgb.DMatrix(np.stack(rows), feature_names=WIN_FEATS))

def heal_win_gain(heal_amt, raw):
    """P(win, curHp+heal capped) - P(win, curHp), using the win model."""
    if META_ENTITY is not None and META_USE_WIN:
        hi = raw.astype(np.float32).copy()
        hi[rawpos["curHp"]] = min(hi[rawpos["maxHp"]], hi[rawpos["curHp"]] + heal_amt)
        pred = _meta_win_predict([raw.astype(np.float32), hi])
        return float(pred[1]-pred[0])
    if WIN_BOOSTER is None or "curHp" not in win_fmpos:
        return 0.0
    base = raw[win_fsel].astype(np.float32)
    hi = base.copy()
    cur = base[win_fmpos["curHp"]]
    mx  = base[win_fmpos["maxHp"]] if "maxHp" in win_fmpos else cur + heal_amt
    hi[win_fmpos["curHp"]] = min(mx, cur + heal_amt)
    pred = _win_predict([base, hi])
    return float(pred[1] - pred[0])

def add_card_win(vec, cid):
    """Win-model version of add_card: bump d{cid} (+deckSize) in the win feature vec."""
    out = vec.copy()
    if "deckSize" in win_fmpos: out[win_fmpos["deckSize"]] += 1.0
    dn = f"d{cid}"
    if dn in win_fmpos: out[win_fmpos[dn]] += 1.0
    return out

def decide_win(cands, raw):
    """Card pick by WIN model: '<best_idx> <best_marginal>' where marginal =
    P(win, deck+card) - P(win, deck). Caller applies its own (win-scale) skip."""
    if META_ENTITY is not None and META_USE_WIN:
        rows = [raw.astype(np.float32)] + [_raw_add_card(raw, c).astype(np.float32) for c in cands]
        pred = _meta_win_predict(rows); marg = pred[1:]-pred[0]
        best = int(np.argmax(marg))
        return f"{best} {float(marg[best]):.6f}"
    if WIN_BOOSTER is None:
        return "5 -999.0"
    base = raw[win_fsel].astype(np.float32)
    rows = np.stack([base] + [add_card_win(base, c) for c in cands])
    with LOCK:
        pred = WIN_BOOSTER.predict(xgb.DMatrix(rows, feature_names=WIN_FEATS))
    marg = pred[1:] - pred[0]
    best = int(np.argmax(marg))
    return f"{best} {float(marg[best]):.6f}"

def upgrade_win_pick(cands, raw):
    """Best upgrade by win: '<idx> <gain>' = argmax P(win, u{cid}+1) - P(win) and its
    gain, so the caller can compare directly against heal_win_gain (same units)."""
    if META_ENTITY is not None and META_USE_WIN:
        rows = [raw.astype(np.float32)] + [_raw_upgrade_card(raw, c).astype(np.float32) for c in cands]
        pred = _meta_win_predict(rows); gain = pred[1:]-pred[0]
        k = int(np.argmax(gain)); return f"{k} {float(gain[k]):.6f}"
    if WIN_BOOSTER is None:
        return "0 0.0"
    base = raw[win_fsel].astype(np.float32)
    rows = [base]
    for c in cands:
        r = base.copy()
        un = f"u{c}"
        if un in win_fmpos: r[win_fmpos[un]] += 1.0
        rows.append(r)
    pred = _win_predict(rows)
    gain = pred[1:] - pred[0]
    k = int(np.argmax(gain))
    return f"{k} {float(gain[k]):.6f}"

def rest_counterfactual_delta(raw):
    """Predicted paired score(rest)-score(smith), or None when no model is loaded."""
    if REST_BOOSTER is None:
        return None
    row = raw[rest_fsel].astype(np.float32)[None, :]
    with LOCK:
        return float(REST_BOOSTER.predict(xgb.DMatrix(row, feature_names=REST_FEATS))[0])

# ---- shop: knapsack over card-buys + removal + relics, maximizing V(final) ----
_GOLD = fmpos.get("gold"); _NREL = fmpos.get("nRelics"); _DSZ = fmpos.get("deckSize")

def _predict_rows(rows):
    with LOCK:
        return BOOSTER.predict(xgb.DMatrix(np.stack(rows), feature_names=FEATS))

def _model_ctx(use_win):
    """(sel, mp, feats, booster, gold_i, dsz_i, predict) for V_floor or V_win."""
    if META_ENTITY is not None and ((use_win and META_USE_WIN) or (not use_win and META_USE_FLOOR)):
        full = np.arange(len(RAW))
        predict = _meta_win_predict if use_win else _meta_floor_predict
        return full, rawpos, RAW, META_ENTITY, rawpos.get("gold"), rawpos.get("deckSize"), predict
    if use_win and WIN_BOOSTER is not None:
        mp = win_fmpos
        return win_fsel, mp, WIN_FEATS, WIN_BOOSTER, mp.get("gold"), mp.get("deckSize"), _win_predict
    return fsel, fmpos, FEATS, BOOSTER, _GOLD, _DSZ, _predict_rows

def best_removal(base, mp, dsz_i, predict):
    """(cid, gain) of the current-deck card whose removal most raises the model score."""
    cids = [i for i in range(NCARD) if f"d{i}" in mp and base[mp[f"d{i}"]] > 0]
    if not cids:
        return None, 0.0
    rows = [base]
    for c in cids:
        r = base.copy(); r[mp[f"d{c}"]] -= 1.0
        if dsz_i is not None: r[dsz_i] -= 1.0
        rows.append(r)
    pred = predict(rows)
    gains = pred[1:] - pred[0]
    k = int(np.argmax(gains))
    return cids[k], float(gains[k])

def shop_plan(remove_cost, cards, relics, raw, use_win=False):
    """cards: list of (cid, price); relics: list of (relic_id, price) per shop slot.
    Enumerate every affordable subset of {card buys, relic buys} x {remove, keep},
    score the resulting state, return the best as tokens like 'c0 c2 r1 x' (buy
    shop-card 0 & 2, buy shop-relic 1, buy a removal). ''=skip. use_win=True scores
    bundles by P(win) (win model) instead of expected floor -- shops are a spend-vs-
    save / relic-vs-cards threshold decision where P(win) may rank better."""
    sel, mp, feats, booster, gold_i, dsz_i, predict = _model_ctx(use_win)
    base = raw[sel].astype(np.float32)
    gold = float(base[gold_i]) if gold_i is not None else 0.0
    rem_cid, _ = best_removal(base, mp, dsz_i, predict) if remove_cost >= 0 else (None, 0.0)
    items = []                                       # (kind, shop_idx, price, id)
    for i, (cid, pr) in enumerate(cards):
        if pr >= 0: items.append(("c", i, pr, cid))
    for j, (rid, pr) in enumerate(relics):
        if pr >= 0: items.append(("r", j, pr, rid))
    n = len(items)
    if n > 16:                                       # safety; real shops have <=10
        items = items[:16]; n = 16
    rem_opts = [False, True] if (remove_cost >= 0 and rem_cid is not None) else [False]
    combos, rows = [], []
    for mask in range(1 << n):
        chosen = [items[k] for k in range(n) if (mask >> k) & 1]
        spend = sum(c[2] for c in chosen)
        for rem in rem_opts:
            s = spend + (remove_cost if rem else 0)
            if s > gold: continue
            r = base.copy()
            if gold_i is not None: r[gold_i] -= s
            add = 0
            for c in chosen:
                if c[0] == "c":
                    dn = f"d{c[3]}"
                    if dn in mp: r[mp[dn]] += 1.0
                    add += 1
                else:                                # relic buy: mark its own r{id} present
                    rn = f"r{c[3]}"
                    if rn in mp: r[mp[rn]] = max(r[mp[rn]], 1.0)
            if rem and rem_cid is not None:
                dn = f"d{rem_cid}"
                if dn in mp: r[mp[dn]] -= 1.0
                if dsz_i is not None: r[dsz_i] -= 1.0
            if dsz_i is not None: r[dsz_i] += add
            combos.append((chosen, rem)); rows.append(r)
    if not rows:
        return ""
    pred = predict(rows)
    chosen, rem = combos[int(np.argmax(pred))]
    toks = [f"{c[0]}{c[1]}" for c in chosen]
    if rem: toks.append("x")
    return " ".join(toks)

class H(socketserver.StreamRequestHandler):
    def handle(self):
        for line in self.rfile:
            line = line.decode().strip()
            if not line: continue
            parts = line.split(";")
            tag = parts[0]
            try:
                if tag == "H":                     # heal-gain query (floor units)
                    heal_amt = float(parts[1])
                    raw = np.array([float(x) for x in parts[2].split(",")], dtype=np.float64)
                    resp = f"{heal_gain(heal_amt, raw):.6f}"
                elif tag == "HW":                  # heal-gain query (P(win) units)
                    heal_amt = float(parts[1])
                    raw = np.array([float(x) for x in parts[2].split(",")], dtype=np.float64)
                    resp = f"{heal_win_gain(heal_amt, raw):.6f}"
                elif tag == "UW":                  # best upgrade by P(win): "<idx> <gain>"
                    cands = [int(x) for x in parts[1].split(",") if x != ""]
                    raw = np.array([float(x) for x in parts[2].split(",")], dtype=np.float64)
                    resp = upgrade_win_pick(cands, raw)
                elif tag == "RC":                  # paired rest-vs-smith score delta
                    raw = np.array([float(x) for x in parts[1].split(",")], dtype=np.float64)
                    delta = rest_counterfactual_delta(raw)
                    resp = "NA" if delta is None else f"{delta:.6f}"
                elif tag == "CW":                  # card pick by P(win): "<idx> <marginal>"
                    cands = [int(x) for x in parts[1].split(",") if x != ""]
                    raw = np.array([float(x) for x in parts[2].split(",")], dtype=np.float64)
                    resp = decide_win(cands, raw)
                elif tag == "CB":                  # boss-aware blend: CB;<w>;<cands>;<feats>
                    w = float(parts[1])
                    cands = [int(x) for x in parts[2].split(",") if x != ""]
                    raw = np.array([float(x) for x in parts[3].split(",")], dtype=np.float64)
                    resp = decide_boss_blend(cands, raw, w)
                elif tag == "CN":                  # deck-set NN card pick: CN;<w>;<cands>;<feats>
                    w = float(parts[1])            # w=1 pure NN, w<1 blend w*NN+(1-w)*v_win GBM
                    cands = [int(x) for x in parts[2].split(",") if x != ""]
                    raw = np.array([float(x) for x in parts[3].split(",")], dtype=np.float64)
                    resp = decide_nn(cands, raw, w)
                elif tag == "CA":                  # paired card action NN + full map graph
                    cands = []
                    for tok in parts[1].split(","):
                        if tok:
                            cid, upgraded = tok.split(":")
                            cands.append((int(cid), int(upgraded)))
                    rooms = [int(x) for x in parts[2].split(",")]
                    edges = [int(x) for x in parts[3].split(",")]
                    special = [int(x) for x in parts[4].split(",")]
                    raw = np.array([float(x) for x in parts[5].split(",")], dtype=np.float64)
                    resp = decide_card_action(cands, raw, rooms, edges, special)
                elif tag == "PG":                  # graph-aware value of one legal map child
                    chosen_x = int(parts[1])
                    rooms = [int(x) for x in parts[2].split(",")]
                    edges = [int(x) for x in parts[3].split(",")]
                    special = [int(x) for x in parts[4].split(",")]
                    raw = np.array([float(x) for x in parts[5].split(",")], dtype=np.float64)
                    resp = f"{path_graph_value(chosen_x, raw, rooms, edges, special):.8f}"
                elif tag == "PA":                  # direct paired path-action model
                    cands = [int(x) for x in parts[1].split(",") if x]
                    heuristic_x = int(parts[2])
                    rooms = [int(x) for x in parts[3].split(",")]
                    edges = [int(x) for x in parts[4].split(",")]
                    special = [int(x) for x in parts[5].split(",")]
                    raw = np.array([float(x) for x in parts[6].split(",")], dtype=np.float64)
                    chosen, q = decide_path_action(cands, raw, rooms, edges, special)
                    hi = cands.index(heuristic_x)
                    bi = cands.index(chosen)
                    resp = f"{chosen} {float((q[bi]-q[hi])*10.0):.6f}"
                elif tag == "OA":                  # batched OOC action -> next-combat prediction
                    bits = [int(x) for x in parts[1].split(",") if x]
                    screen = int(parts[2]); act = int(parts[3])
                    raw = np.array([float(x) for x in parts[4].split(",")], dtype=np.float32)
                    resp = decide_ooc_action(bits, screen, act, raw)
                elif tag == "OE":                  # OOC action + specified encounter prediction
                    bits = [int(x) for x in parts[1].split(",") if x]
                    encounters = [int(x) for x in parts[2].split(",") if x]
                    screen = int(parts[3]); act = int(parts[4])
                    raw = np.array([float(x) for x in parts[5].split(",")], dtype=np.float32)
                    resp = decide_ooc_encounter(bits, encounters, screen, act, raw)
                elif tag == "U":                   # upgrade-target query
                    cands = [int(x) for x in parts[1].split(",") if x != ""]
                    raw = np.array([float(x) for x in parts[2].split(",")], dtype=np.float64)
                    resp = str(upgrade_pick(cands, raw))
                elif tag == "VS":                  # raw V(state) = predicted final floor (deck-strength scalar)
                    raw = np.array([float(x) for x in parts[1].split(",")], dtype=np.float64)
                    if META_ENTITY is not None and META_USE_FLOOR:
                        v = float(_meta_floor_predict([raw.astype(np.float32)])[0])
                    else:
                        base = raw[fsel].astype(np.float32)
                        with LOCK:
                            v = float(BOOSTER.predict(xgb.DMatrix(base[None, :], feature_names=FEATS))[0])
                    resp = f"{v:.6f}"
                elif tag == "VW":                  # raw V_win(state) = P(win); for boss-relic / Neow choice
                    if META_ENTITY is not None and META_USE_WIN:
                        raw = np.array([float(x) for x in parts[1].split(",")], dtype=np.float64)
                        v = float(_meta_win_predict([raw.astype(np.float32)])[0])
                        resp = f"{v:.6f}"
                    elif WIN_BOOSTER is None: resp = "0.5"
                    else:
                        raw = np.array([float(x) for x in parts[1].split(",")], dtype=np.float64)
                        base = raw[win_fsel].astype(np.float32)
                        with LOCK:
                            v = float(WIN_BOOSTER.predict(xgb.DMatrix(base[None, :], feature_names=WIN_FEATS))[0])
                        resp = f"{v:.6f}"
                elif tag == "M":                   # all card marginals (for softmax datagen sampling)
                    cands = [int(x) for x in parts[1].split(",") if x != ""]
                    raw = np.array([float(x) for x in parts[2].split(",")], dtype=np.float64)
                    resp = marginals(cands, raw)
                elif tag == "X":                   # removal-target query (worst card)
                    cands = [int(x) for x in parts[1].split(",") if x != ""]
                    raw = np.array([float(x) for x in parts[2].split(",")], dtype=np.float64)
                    resp = str(worst_pick(cands, raw))
                elif tag == "S" or tag == "SW":    # shop knapsack (SW = score by P(win))
                    # S;<removeCost>;<cid:price,...>;<relicprice,...>;<feats>
                    remove_cost = int(parts[1])
                    cards = []
                    for tok in parts[2].split(","):
                        if tok == "": continue
                        cid, pr = tok.split(":"); cards.append((int(cid), int(pr)))
                    relics = []
                    for tok in parts[3].split(","):
                        if tok == "": continue
                        rid, pr = tok.split(":"); relics.append((int(rid), int(pr)))
                    raw = np.array([float(x) for x in parts[4].split(",")], dtype=np.float64)
                    resp = shop_plan(remove_cost, cards, relics, raw, use_win=(tag == "SW"))
                else:                              # card-pick query (original)
                    cands = [int(x) for x in tag.split(",") if x != ""]
                    raw = np.array([float(x) for x in parts[1].split(",")], dtype=np.float64)
                    resp = str(decide(cands, raw))
            except Exception as e:
                sys.stderr.write(f"[v_server] error: {e}\n")
                resp = {"H": "0.0", "HW": "0.0", "RC": "NA", "U": "0", "UW": "0 0.0",
                        "X": "0", "S": "", "SW": "", "M": "", "VS": "20.0", "VW": "0.5",
                        "CN": "5 -999.0", "CA": "5 -999.0", "PG": "0.5", "PA": "-1", "OA": "", "OE": ""}.get(tag, "5 -999.0")
            self.wfile.write(f"{resp}\n".encode()); self.wfile.flush()

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == "__main__":
    srv = Server(("127.0.0.1", PORT), H)
    print(f"[v_server] ready on 127.0.0.1:{PORT}  skipThr={SKIP_THR} neverSkip={NEVER_SKIP}", flush=True)
    srv.serve_forever()
