#!/usr/bin/env python3
"""Train the Phase-A token-state OOC strategic net (V4) from `strategicgen2` CSV rows.

Same row schema and losses as `train_strategic.py` (V3): group-CE on `chosen`,
per-screen value-MSE on chosen rows (target 10*won+endHp), Q-MSE on Tier-B
labeled rows (target 10*labelWon+labelHp). The state representation is replaced
by the V4 token state (contract docs/knowledge-base/architecture/ooc-strategic-v4.md):
42 globals (36 raw scalars + 6 derived thresholds), counted deck tokens
(id, upgraded, countF) through a 1-layer single-head attention, relic tokens
(id, dataF) and potion tokens (id, countF) through mean-pooled MLPs, plus a
candidate entity embedding in the action encoder (rung 4).

Rung mask (STRAT_TOK_RUNG, 1..4) zeroes inactive groups: rung<2 -> no deck
tokens; rung<3 -> no relic/potion tokens; rung<4 -> no entity embedding.
All rungs share the same topology and training contract.

Memory: like V3, the state block is read in pandas chunks and written ONCE to a
group-ordered float16 binary (OUT + "_tok_state.bin") with 474 raw columns per
row [glob 42, deck 96x3, rel 64x2, pot 8x2]; training gathers contiguous
slices from an mmap of that file (uploaded to GPU VRAM once and gathered
on-device when CUDA is available; CPU mmap fallback on OOM). Global mean/inv
(42 values) are computed from train rows; normalization happens per batch (the
file stores RAW values).
"""
import hashlib, json, math, os, re, sys, time

# Defragment the CUDA caching allocator before torch initializes; the
# GPU-resident state (2.9 GB) + attention intermediates fragment 8 GB VRAM
# otherwise (e.g. when another process holds memory). Respects a user setting.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import numpy as np
import pandas as pd
import torch
from torch import nn

from strategic_tok_net import Net, NCARD, NREL, NPOT, MAXD, MAXR, MAXP, NGLOB, NRAW
from strategic_split import SPLIT_VERSION, seed_disjoint_split
from strategic_tok_contract import build_globals, make_layout

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/strategic_tierb.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "selfplay/models/ooc_strategic_tok"
EPOCHS = int(os.environ.get("STRAT_EPOCHS", "40"))
PATIENCE = int(os.environ.get("STRAT_PATIENCE", "6"))  # stop after N epochs without >=MIN_DELTA val_pol_ce improvement
MIN_DELTA = float(os.environ.get("STRAT_MIN_DELTA", "1e-4"))
SELECT_METRIC = os.environ.get("STRAT_SELECT_METRIC", "val_pol_ce")  # best-checkpoint metric: val_pol_ce (min) or q_top1 (max)
Q_TARGET = os.environ.get("STRAT_Q_TARGET", "absolute")  # absolute or fallback_centered
if Q_TARGET not in ("absolute", "fallback_centered"):
    raise ValueError("STRAT_Q_TARGET must be absolute or fallback_centered")
INIT_CKPT = os.environ.get("STRAT_INIT_CKPT", "")  # warm-start from a checkpoint
INIT_REUSE_NORM = os.environ.get("STRAT_INIT_REUSE_NORM", "0") == "1"  # reuse ckpt mean/inv
Q_ONLY = os.environ.get("STRAT_Q_ONLY", "0") == "1"  # freeze all except q.* parameters
SPLIT_MANIFEST = os.environ.get("STRAT_SPLIT_MANIFEST", "")  # JSON file to save train/val seeds
SPLIT_LOAD = os.environ.get("STRAT_SPLIT_LOAD", "")  # JSON file to load train/val seeds from
MODEL_SEED = int(os.environ.get("STRAT_MODEL_SEED", "0"))  # model initialization seed
RANK_LAMBDA = float(os.environ.get("STRAT_RANK_LAMBDA", "0"))  # 0 = disabled; pairwise labelWon ranking term weight
RANK_MARGIN = float(os.environ.get("STRAT_RANK_MARGIN", "1.0"))  # hinge margin for the ranking term
RANK_MAX_PAIRS = int(os.environ.get("STRAT_RANK_MAX_PAIRS", "16"))  # max ranking pairs per group per batch
BATCH = int(os.environ.get("STRAT_BATCH", "4096"))   # target ROWS per batch (whole groups)
EVAL_CHUNK = int(os.environ.get("STRAT_EVAL_CHUNK", "8192"))  # eval forward chunk (no group constraint; keep small: VRAM holds the 2.9 GB resident state)
LR = float(os.environ.get("STRAT_LR", "2e-3"))
VLAMBDA = float(os.environ.get("STRAT_VLAMBDA", "0.5"))
QLAMBDA = float(os.environ.get("STRAT_QLAMBDA", "1.0"))
CLIP = float(os.environ.get("STRAT_CLIP", "1.0"))
CHUNK = int(os.environ.get("STRAT_CHUNK", "250000"))
RUNG = int(os.environ.get("STRAT_TOK_RUNG", "4"))
TRANSFORMER = os.environ.get("STRAT_TOK_TRANSFORMER", "0") == "1"
PROBES_FILE = os.environ.get("TOK_PROBES_FILE", "")   # npy (nrows, 54); unset = no probes
NPROBES = 9 if PROBES_FILE else 0
QUANTS = int(os.environ.get("STRAT_TOK_QUANTILES", "0"))  # C4: per-screen 11-quantile value heads
NQUANTS = 11 if QUANTS else 0
CROSS = int(os.environ.get("STRAT_TOK_CROSS", "0"))  # C2: candidate-deck cross-attention
COMPILE = os.environ.get("STRAT_TOK_COMPILE", "1") == "1"  # torch.compile (Triton fusion) the net; needs CPython dev headers
THREADS = int(os.environ.get("OMP_NUM_THREADS", "8"))
DEVICE = os.environ.get("STRAT_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
if not DEVICE.startswith("cuda"):
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
torch.set_num_threads(THREADS)
torch.manual_seed(MODEL_SEED)
print(f"device: {DEVICE}  rung: {RUNG}  epochs: {EPOCHS}"
      f"  transformer: {int(TRANSFORMER)}", flush=True)

nonfinite_batches = [0]   # non-finite loss counter (NaN-bug visibility, issue 44)

hdr = pd.read_csv(CSV, nrows=0).columns
need = {"seed", "decIdx", "screen", "action", "actionType", "c1", "c2", "c3",
        "cand1", "cand2", "cand3", "chosen", "won", "endHp",
        "labelWon", "labelHp"}
missing = need - set(hdr)
if missing:
    raise ValueError(f"missing columns: {sorted(missing)}")
if "labelWon" not in hdr or "labelHp" not in hdr:
    raise ValueError("Tier-B training requires labelWon,labelHp (strategicgen2 schema)")
opt_cols = ["labelFloor", "labelBootstrap"]
for c in opt_cols:
    if c not in hdr:
        print(f"[train-strategic-tok] optional column {c} absent; using NaN", flush=True)

# State block = all numeric columns strictly between `chosen` and `won` (found
# by column index, like V3). Group the 1017 columns by name prefix:
# scalars (44), d* (deck counts), u* (upgraded counts), r* (relics), pot*.
ci, wi = list(hdr).index("chosen"), list(hdr).index("won")
NSTATE = wi - ci - 1
if NSTATE != 1017:
    raise ValueError(f"expected the 1017-col rich state block, got {NSTATE} columns")
state_cols = list(hdr[ci + 1:wi])
contract_layout = make_layout(state_cols)
re_d = re.compile(r"^d(\d+)$")
re_u = re.compile(r"^u(\d+)$")
re_r = re.compile(r"^r(\d+)$")
re_pot = re.compile(r"^pot(\d+)$")
scalar_idx, d_idx, u_idx, r_idx, pot_idx = [], [], [], [], []
for i, name in enumerate(state_cols):
    if re_d.match(name): d_idx.append(i)
    elif re_u.match(name): u_idx.append(i)
    elif re_r.match(name): r_idx.append(i)
    elif re_pot.match(name): pot_idx.append(i)
    else: scalar_idx.append(i)
assert len(scalar_idx) == 44, len(scalar_idx)
# Verify column positions: the trainer relies on specific CSV column indices;
# if richHeader() changes order, fail with a clear message rather than silently
# producing a skewed model (see decision-log/2026-08-09-v4-glob-skew-fix.md).
_col_checks = [
    (23, 'pvShop'), (31, 'bottledPowId'),
    (1005, 'fmDElite'), (1015, 'curMapX'), (1016, 'curMapY'),
]
for _idx, _name in _col_checks:
    assert state_cols[_idx] == _name, f"state_cols[{_idx}] = {state_cols[_idx]!r}, expected {_name!r}"
assert len(d_idx) == NCARD and len(u_idx) == NCARD, (len(d_idx), len(u_idx))
assert len(r_idx) == NREL and len(pot_idx) == NPOT, (len(r_idx), len(pot_idx))

# Raw scalars needed for thresholds / affordability (all are CSV columns).
extra_cols = ["gold", "curHp", "maxHp", "potionCount", "potionCapacity",
              "blueKey", "greenKey", "redKey", "remElites", "fmDBoss"]
use_cols = sorted(need | set(opt_cols) | set(extra_cols))
chunks = pd.read_csv(CSV, usecols=use_cols, chunksize=CHUNK)
small = []
for ch in chunks:
    small.append(ch)
df = pd.concat(small, ignore_index=True)
del small
# Group offsets below require all rows for a (seed, decIdx) decision to be
# contiguous. CSV production order is not a contract, so canonicalize it here.
df = df.sort_values(["seed", "decIdx"], kind="stable").reset_index(drop=True)
nrows = len(df)
print(f"{nrows:,} rows, {df.seed.nunique()} seeds", flush=True)

groups = df.seed.to_numpy(np.int64) * 1000000 + df.decIdx.to_numpy(np.int64)
grp_vals, grp_ids = np.unique(groups, return_inverse=True)
NG = len(grp_vals)
sizes = np.bincount(grp_ids, minlength=NG).astype(np.int64)
block_start = np.concatenate(([0], np.cumsum(sizes[:-1])))

chosen = df.chosen.to_numpy(np.int64) == 1
one_chosen = np.bincount(grp_ids[chosen], minlength=NG) == 1
chosen_row_idx = np.full(NG, -1, np.int64)
cp = np.flatnonzero(chosen)
chosen_row_idx[grp_ids[cp]] = cp
act_col = df.action.to_numpy(np.int64)
chosen_act = np.where(chosen_row_idx >= 0, act_col[np.maximum(chosen_row_idx, 0)], -2)
valid_pol = one_chosen & (chosen_act != -1)
print(f"{NG} decisions, {int(one_chosen.sum())} groups with exactly one chosen row "
      f"({int(valid_pol.sum())} with a valid policy action)", flush=True)

# Seed-disjoint 80/20 split; decisions remain the batching unit.
tr_rows, train_seeds, val_seeds = seed_disjoint_split(df.seed.to_numpy(), random_seed=0)

# --- Load split from manifest if requested ---
if SPLIT_LOAD:
    with open(SPLIT_LOAD) as f:
        m = json.load(f)
    train_seeds = np.array(m["train_seeds"], dtype=np.int64)
    val_seeds = np.array(m["val_seeds"], dtype=np.int64)
    assert len(np.intersect1d(train_seeds, val_seeds)) == 0, "loaded split has seed intersection"
    tr_rows = np.isin(df.seed.to_numpy(), train_seeds)
    print(f"[train-strategic-tok] loaded split from {SPLIT_LOAD}: "
          f"{len(train_seeds)} train, {len(val_seeds)} val seeds", flush=True)

tr_mask = tr_rows[block_start].copy()
if not np.array_equal(tr_rows, tr_mask[grp_ids]):
    raise AssertionError("seed split crossed a decision group")
va_groups = np.flatnonzero(~tr_mask)
if len(va_groups) == 0:
    raise ValueError("need held-out decision groups")
print(f"train seeds ({len(train_seeds)}): {train_seeds.tolist()}", flush=True)
print(f"validation seeds ({len(val_seeds)}): {val_seeds.tolist()}", flush=True)
print(f"seed intersection: {np.intersect1d(train_seeds, val_seeds).tolist()}", flush=True)
print(f"train: {int(tr_rows.sum()):,} rows / {int(tr_mask.sum()):,} groups, "
      f"val: {int((~tr_rows).sum()):,} rows / {len(va_groups):,} groups", flush=True)
rng = np.random.default_rng(0)

# --- Split manifest: save if creating a new split ---
if SPLIT_MANIFEST and not SPLIT_LOAD:
    manifest = {"train_seeds": train_seeds.tolist(), "val_seeds": val_seeds.tolist(),
                "split_seed": 0, "model_seed": MODEL_SEED, "batch_seed": 0}
    with open(SPLIT_MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"[train-strategic-tok] wrote split manifest: {SPLIT_MANIFEST}", flush=True)

order = np.argsort(grp_ids, kind="stable")
inv_perm = np.empty(nrows, np.int64)
inv_perm[order] = np.arange(nrows)
pos_of_row = inv_perm.copy()
rank_in_group = pos_of_row - block_start[grp_ids]
cr = np.maximum(chosen_row_idx, 0)
chosen_in_block = np.where(chosen_row_idx >= 0,
                           block_start[grp_ids[cr]] + rank_in_group[cr], -1)
chosen_off = np.where(chosen_in_block >= 0, chosen_in_block - block_start, -1)


def parse_bits(x):
    if isinstance(x, str) and x.startswith("bits="):
        return int(x.split("=")[1])
    return int(x)


action_ints = np.array([parse_bits(x) for x in df.action], np.int64)
cat = np.stack([np.clip(df[c].to_numpy(np.int64) + 1, 0, 511).astype(np.int16)
                for c in ("c1", "c2", "c3", "cand1", "cand2", "cand3")], 1)
atype = np.clip(df.actionType.to_numpy(np.int64) + 1, 0, 15).astype(np.int16)
screen = np.clip(df.screen.to_numpy(np.int64), 0, 15).astype(np.int16)
value = (10 * df.won.to_numpy(np.float32) + df.endHp.to_numpy(np.float32)).astype(np.float32)
q_target = (10 * df.labelWon.to_numpy(np.float32) + df.labelHp.to_numpy(np.float32)).astype(np.float32)
q_valid = np.isfinite(q_target)

# --- Fallback-centering: subtract behavior fallback Q from all candidates ---
if Q_TARGET == "fallback_centered":
    q_target_abs = q_target.copy()
    # Build per-group fallback Q value: Q at the chosen row in each group
    _fb_group = np.full(NG, np.nan, np.float32)
    valid_fb = chosen_row_idx >= 0
    _fb_group[valid_fb] = q_target[chosen_row_idx[valid_fb]]
    has_fb = np.isfinite(_fb_group)
    n_missing = int((~has_fb).sum())
    if n_missing > 0:
        print(f"[train-strategic-tok] WARNING: {n_missing} groups lack a behavior fallback — "
              f"q_target set to NaN for these groups", flush=True)
        q_target[~has_fb[grp_ids]] = np.nan
    q_target[has_fb[grp_ids]] = (q_target[has_fb[grp_ids]] -
                                  _fb_group[has_fb][grp_ids[has_fb[grp_ids]]]).astype(np.float32)
    q_valid = np.isfinite(q_target)
    print(f"[train-strategic-tok] Q target: fallback_centered", flush=True)
    # Self-test on groups with valid fallback
    n_tested = 0
    for _g in range(min(100, NG)):
        if not has_fb[_g]:
            continue
        lo, sz = int(block_start[_g]), int(sizes[_g])
        if sz < 2:
            continue
        fb_off = int(rank_in_group[chosen_row_idx[_g]])
        orig = q_target_abs[lo:lo + sz]
        centered = q_target[lo:lo + sz]
        assert abs(centered[fb_off]) < 1e-4, f"centered[fallback]={centered[fb_off]}"
        for i in range(sz):
            for j in range(sz):
                diff = abs((orig[i] - orig[j]) - (centered[i] - centered[j]))
                assert diff < 1e-3, f"pairwise diff mismatch: {diff}"
        assert np.argmax(orig) == np.argmax(centered), "argmax changed"
        n_tested += 1
        if n_tested >= 10:
            break
    print(f"[train-strategic-tok] centering self-test PASS ({n_tested} groups)", flush=True)

lw_all = df.labelWon.to_numpy(np.float32)

# Candidate entity embedding (contract 2.5): entType 0=none 1=card 2=relic 3=potion.
scr = df.screen.to_numpy(np.int64)
at = df.actionType.to_numpy(np.int64)
c1 = df.cand1.to_numpy(np.int64)
c2 = df.cand2.to_numpy(np.int64)
gold = df.gold.to_numpy(np.float32)
ent_type = np.zeros(nrows, np.int64)
ent_id = np.full(nrows, -1, np.int64)
gold_ge = np.zeros(nrows, np.float32)
m = (scr == 2) & (at == 0)        # REWARDS CARD
ent_type[m] = 1; ent_id[m] = c1[m]
m = (scr == 2) & (at == 4)        # REWARDS RELIC
ent_type[m] = 2; ent_id[m] = c1[m]
m = (scr == 2) & (at == 3)        # REWARDS POTION
ent_type[m] = 3; ent_id[m] = c1[m]
m = (scr == 2) & (at == 1) & (c1 >= 0)   # REWARDS GOLD: cand1 = gold amount
gold_ge[m] = (gold[m] >= c1[m]).astype(np.float32)
m = (scr == 8) & (at == 0)        # SHOP CARD
ent_type[m] = 1; ent_id[m] = c1[m]
m = (scr == 8) & (at == 4)        # SHOP RELIC
ent_type[m] = 2; ent_id[m] = c1[m]
m = (scr == 8) & (at == 3)        # SHOP POTION
ent_type[m] = 3; ent_id[m] = c1[m]
m = (scr == 8) & (c2 >= 0)        # SHOP: cand2 = price
gold_ge[m] = (gold[m] >= c2[m]).astype(np.float32)
m = (scr == 4)                    # CARD_SELECT
ent_type[m] = 1; ent_id[m] = c1[m]
del c1, c2, gold, scr, at

# Reorder every small array by group id once: batches are contiguous slices.
action_ints, cat = action_ints[order], cat[order]
atype, screen, value = atype[order], screen[order], value[order]
q_target, q_valid = q_target[order], q_valid[order]
chosen = chosen[order]
ent_type, ent_id, gold_ge = ent_type[order], ent_id[order], gold_ge[order]

probes = None
if PROBES_FILE:
    probes = np.load(PROBES_FILE).astype(np.float32)
    if probes.shape[0] != nrows or probes.shape[1] != NPROBES * 6:
        raise ValueError(f"probe file {PROBES_FILE}: {probes.shape} != ({nrows}, {NPROBES*6})")
    probes = probes[order]
    print(f"[train-strategic-tok] probes: {probes.shape}", flush=True)

# --- Token-array builders (vectorized over a chunk of rows) ------------------
def deck_tokens(d, u):
    """d/u: (N, NCARD) float32 count arrays -> (N, MAXD) ids/ups/cfs, -1 pad."""
    N = d.shape[0]
    ids = np.full((N, MAXD), -1, np.float32)
    ups = np.zeros((N, MAXD), np.float32)
    cfs = np.zeros((N, MAXD), np.float32)
    w = np.zeros(N, np.int32)
    for i in range(NCARD):
        ui = u[:, i]
        m1 = ui > 0
        if m1.any():
            j = w[m1]
            ids[m1, j] = i
            ups[m1, j] = 1.0
            cfs[m1, j] = np.minimum(ui[m1], 9) / 9.0
            w[m1] += 1
        rem = d[:, i] - ui
        m0 = rem > 0
        if m0.any():
            j = w[m0]
            ids[m0, j] = i
            cfs[m0, j] = np.minimum(rem[m0], 9) / 9.0
            w[m0] += 1
    return ids, ups, cfs


def rel_tokens(r):
    """r: (N, NREL) float32 (presence+counter) -> (N, MAXR) ids/dfs, -1 pad."""
    N = r.shape[0]
    ids = np.full((N, MAXR), -1, np.float32)
    dfs = np.zeros((N, MAXR), np.float32)
    w = np.zeros(N, np.int32)
    for i in range(NREL):
        ri = r[:, i]
        m = ri > 0
        if m.any():
            j = w[m]
            ids[m, j] = i
            dfs[m, j] = np.minimum(ri[m] - 1.0, 9) / 9.0
            w[m] += 1
    return ids, dfs


def pot_tokens(p):
    """p: (N, NPOT) float32 counts -> (N, MAXP) ids/cfs, -1 pad."""
    N = p.shape[0]
    ids = np.full((N, MAXP), -1, np.float32)
    cfs = np.zeros((N, MAXP), np.float32)
    w = np.zeros(N, np.int32)
    for i in range(NPOT):
        pi = p[:, i]
        m = pi > 0
        if m.any():
            j = w[m]
            ids[m, j] = i
            cfs[m, j] = np.minimum(pi[m], 9) / 9.0
            w[m] += 1
    return ids, cfs


# --- State file: 482 raw float16 columns, group-ordered -----------------------
NFILE = NGLOB + MAXD * 3 + MAXR * 2 + MAXP * 2   # 42 + 288 + 128 + 16 = 474
STATE_FILE = OUT + "_tok_state.bin"
expected = nrows * NFILE * 2
reused = False
fp_file = STATE_FILE + ".fp"
fp = hashlib.sha256()
for f in (CSV, os.path.abspath(__file__)):
    try:
        st = os.stat(f)
        fp.update(f.encode()); fp.update(str(st.st_size).encode()); fp.update(str(st.st_mtime_ns).encode())
    except OSError:
        pass
fp.update(str(nrows).encode()); fp.update(str(NFILE).encode())
fp.update(SPLIT_VERSION.encode())
fp_hex = fp.hexdigest()
old_fp = None
if os.path.exists(fp_file):
    with open(fp_file) as f:
        old_fp = f.read().strip()
if (os.path.exists(STATE_FILE) and os.path.getsize(STATE_FILE) == expected
        and old_fp == fp_hex):
    reused = True
    print(f"[train-strategic-tok] reusing {STATE_FILE} ({expected:,} bytes)", flush=True)

# Column groups inside the file layout.
glob_cols = slice(0, NGLOB)
dk_id_cols = slice(NGLOB, NGLOB + MAXD * 3, 3)
dk_up_cols = slice(NGLOB + 1, NGLOB + MAXD * 3, 3)
dk_cf_cols = slice(NGLOB + 2, NGLOB + MAXD * 3, 3)
rl_id_cols = slice(NGLOB + MAXD * 3, NGLOB + MAXD * 3 + MAXR * 2, 2)
rl_df_cols = slice(NGLOB + MAXD * 3 + 1, NGLOB + MAXD * 3 + MAXR * 2, 2)
pt_id_cols = slice(NGLOB + MAXD * 3 + MAXR * 2, NFILE, 2)
pt_cf_cols = slice(NGLOB + MAXD * 3 + MAXR * 2 + 1, NFILE, 2)

mean = np.zeros(NGLOB, np.float64)
sumsq = np.zeros(NGLOB, np.float64)
cnt = 0
lo = 0
for chunk in pd.read_csv(CSV, usecols=state_cols, chunksize=CHUNK, dtype=np.float32):
    hi = lo + len(chunk)
    c = chunk.to_numpy(np.float64)
    m = tr_rows[lo:hi]
    # Build the NRAW=36 glob block: columns 0-14 (ascension..bossId) +
    # pv*/bottled* (cols 23-31) + fm*/mapPos (cols 1005-1016).
    # Skip columns 15-22 (nextEliteId/nextFight0-2/remElites/remFights/
    # monOffset/eliteOffset — the 8 hidden-information leaks) and the
    # interleaved d/u/r/pot block (cols 32-1004).
    c_m = c[m, :]
    g = np.zeros((c_m.shape[0], NGLOB), np.float64)
    g[:, :14] = c_m[:, :14]
    g[:, 14] = c_m[:, 14]          # bossId (legit, visible on act map)
    g[:, 15:24] = c_m[:, 23:32]    # pvShop..bottledPowId (9 scalars)
    g[:, 24:34] = c_m[:, 1005:1015] # fmDElite..fmCTreasure (10 values)
    g[:, 34:NRAW] = c_m[:, 1015:1017] # curMapX, curMapY (2 values)
    # Slots NRAW..NGLB-1 are DERIVED features.
    hp = c_m[:, 3]
    mx = np.maximum(c_m[:, 4], 1.0)
    g[:, NRAW + 0] = hp / mx                                          # hpFrac
    g[:, NRAW + 1] = c_m[:, 4] - hp                                   # missingHp
    g[:, NRAW + 2] = (c_m[:, 12] < c_m[:, 13]).astype(np.float64)     # freePotionSlot
    g[:, NRAW + 3] = (c_m[:, 5] >= 75.0).astype(np.float64)           # goldGeRemoval
    # canTakeEliteKey: fmCElite (c col 1009) replaces removed remElites (c col 19)
    g[:, NRAW + 4] = ((c_m[:, 1009] > 0) & ~((c_m[:, 9] > 0) & (c_m[:, 10] > 0) & (c_m[:, 11] > 0))).astype(np.float64)
    g[:, NRAW + 5] = (c_m[:, 1008] <= 3.0).astype(np.float64)         # bossNear (fmDBoss, c col 1008)
    if cnt == 0 and len(c_m):
        if not np.array_equal(g, build_globals(c_m, contract_layout)):
            raise AssertionError("V4 glob construction disagrees with the shared contract")
    mean += g.sum(0)
    sumsq += (g * g).sum(0)
    cnt += int(m.sum())
    lo = hi
mean /= max(1, cnt)
var = sumsq / max(1, cnt) - mean * mean
std = np.sqrt(np.maximum(var, 0.0))
inv = 1 / np.maximum(std, 1e-6)
mean = mean.astype(np.float32)
inv = inv.astype(np.float32)

if not reused:
    state_mem = np.memmap(STATE_FILE, dtype=np.float16, mode="w+", shape=(nrows, NFILE))
    lo = 0
    for chunk in pd.read_csv(CSV, usecols=state_cols, chunksize=CHUNK, dtype=np.float32):
        hi = lo + len(chunk)
        c = chunk.to_numpy(np.float64)
        out = np.zeros((len(chunk), NFILE), np.float32)
        out[:, :14] = c[:, :14]
        out[:, 14] = c[:, 14]          # bossId (legit, visible on act map)
        out[:, 15:24] = c[:, 23:32]    # pvShop..bottledPowId (9 scalars)
        out[:, 24:34] = c[:, 1005:1015] # fmDElite..fmCTreasure (10 values)
        out[:, 34:NRAW] = c[:, 1015:1017] # curMapX, curMapY (2 values)
        hp = c[:, 3]                                    # curHp
        mx = np.maximum(c[:, 4], 1.0)                   # maxHp
        out[:, NRAW + 0] = hp / mx                      # hpFrac
        out[:, NRAW + 1] = c[:, 4] - hp                 # missingHp
        out[:, NRAW + 2] = (c[:, 12] < c[:, 13]).astype(np.float32)             # freePotionSlot
        out[:, NRAW + 3] = (c[:, 5] >= 75.0).astype(np.float32)                 # goldGeRemoval
        # canTakeEliteKey: fmCElite (c col 1009) replaces removed remElites (c col 19)
        out[:, NRAW + 4] = ((c[:, 1009] > 0) & ~((c[:, 9] > 0) & (c[:, 10] > 0) & (c[:, 11] > 0))).astype(np.float32)
        out[:, NRAW + 5] = (c[:, 1008] <= 3.0).astype(np.float32)               # bossNear (fmDBoss, c col 1008)
        d = c[:, d_idx]
        u = c[:, u_idx]
        r = c[:, r_idx]
        p = c[:, pot_idx]
        ids, ups, cfs = deck_tokens(d, u)
        out[:, dk_id_cols] = ids
        out[:, dk_up_cols] = ups
        out[:, dk_cf_cols] = cfs
        ids, dfs = rel_tokens(r)
        out[:, rl_id_cols] = ids
        out[:, rl_df_cols] = dfs
        ids, cfs = pot_tokens(p)
        out[:, pt_id_cols] = ids
        out[:, pt_cf_cols] = cfs
        state_mem[inv_perm[lo:hi]] = out
        lo = hi
    state_mem.flush()
    with open(fp_file, "w") as f:
        f.write(fp_hex)
    print(f"[train-strategic-tok] wrote {STATE_FILE} ({expected:,} bytes)", flush=True)

state_mmap = np.memmap(STATE_FILE, dtype=np.float16, mode="r", shape=(nrows, NFILE))

# GPU-resident state: upload once, gather rows on-device (~0.15 ms vs ~6 ms
# per-batch CPU mmap gather). Falls back to the CPU mmap path on OOM.
state_gpu = None
if DEVICE.startswith("cuda"):
    try:
        state_gpu = torch.from_numpy(np.array(state_mmap)).to(DEVICE, torch.float16)
        print(f"[train-strategic-tok] state resident on GPU: {state_gpu.shape} "
              f"({state_gpu.numel() * 2:,} bytes)", flush=True)
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        print("[train-strategic-tok] GPU state upload OOM; using CPU mmap gather", flush=True)
AR_G = None
act_gpu = cat_gpu = atype_gpu = screen_gpu = ent_type_gpu = ent_id_gpu = gold_ge_gpu = None
probes_gpu = None
if state_gpu is not None:
    AR_G = torch.arange(32, dtype=torch.int64, device=DEVICE)
    act_gpu = torch.from_numpy(action_ints).to(DEVICE, torch.int64)
    cat_gpu = torch.from_numpy(cat).to(DEVICE, torch.long)
    atype_gpu = torch.from_numpy(atype).to(DEVICE, torch.long)
    screen_gpu = torch.from_numpy(screen).to(DEVICE, torch.long)
    ent_type_gpu = torch.from_numpy(ent_type).to(DEVICE, torch.long)
    ent_id_gpu = torch.from_numpy(ent_id).to(DEVICE, torch.long)
    gold_ge_gpu = torch.from_numpy(gold_ge).to(DEVICE)
    if probes is not None:
        probes_gpu = torch.from_numpy(probes).to(DEVICE)



net = Net(RUNG, nprobes=NPROBES, transformer=TRANSFORMER, nquants=NQUANTS, ncross=CROSS).to(DEVICE)
model = net
if COMPILE and DEVICE.startswith("cuda"):
    try:
        # mode="default" (Triton fusion, ~2x on this net). Not
        # "reduce-overhead": CUDA-graph capture rejects the masked index_put_
        # in the entity block. State dicts are handled via `net` (the compiled
        # wrapper would prefix keys with `_orig_mod.` and break the exporter).
        # suppress_errors: any compile failure (e.g. missing CPython dev
        # headers) falls back to eager for that graph instead of aborting.
        torch._dynamo.config.suppress_errors = True
        model = torch.compile(net, mode="default")
        print("[train-strategic-tok] torch.compile enabled (default mode)", flush=True)
    except Exception as e:
        model = net
        print(f"[train-strategic-tok] torch.compile failed ({e!r}); running eager", flush=True)
opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=2e-4)

# ── Warm-start from checkpoint ──
if INIT_CKPT:
    print(f"[train-strategic-tok] warm-start from {INIT_CKPT}", flush=True)
    init_ckpt = torch.load(INIT_CKPT, map_location=DEVICE, weights_only=False)
    # Validate architecture compatibility
    for key in ["rung", "transformer", "nquants", "ncross", "nprobes"]:
        ckpt_val = init_ckpt.get(key, 0)
        local_val = {"rung": RUNG, "transformer": TRANSFORMER, "nquants": NQUANTS,
                     "ncross": CROSS, "nprobes": NPROBES}[key]
        if bool(ckpt_val) != bool(local_val) and not (key == "rung" and ckpt_val == local_val):
            if ckpt_val != local_val:
                print(f"[train-strategic-tok] WARNING: ckpt {key}={ckpt_val} != local {local_val}", flush=True)
    net.load_state_dict(init_ckpt["state_dict"], strict=False)
    if INIT_REUSE_NORM:
        print(f"[train-strategic-tok] reusing checkpoint normalization", flush=True)
        mean = init_ckpt["mean"].copy()
        inv = init_ckpt["inv"].copy()
        MEAN = torch.from_numpy(mean).to(DEVICE)
        INV = torch.from_numpy(inv).to(DEVICE)
    print(f"[train-strategic-tok] warm-start loaded", flush=True)

# ── Q-only mode: freeze all except q.* parameters ──
if Q_ONLY:
    print(f"[train-strategic-tok] Q-only mode: freezing all except q.*", flush=True)
    for name, param in net.named_parameters():
        if not name.startswith("q."):
            param.requires_grad = False
    # Rebuild optimizer with only trainable params
    opt = torch.optim.AdamW(
        (p for p in net.parameters() if p.requires_grad), lr=LR, weight_decay=2e-4)
    frozen = sum(1 for p in net.parameters() if not p.requires_grad)
    trainable = sum(1 for p in net.parameters() if p.requires_grad)
    print(f"[train-strategic-tok] frozen={frozen} trainable={trainable}", flush=True)

AR = np.arange(32, dtype=np.int64)
MEAN = torch.from_numpy(mean).to(DEVICE)
INV = torch.from_numpy(inv).to(DEVICE)


def fwd_rows(rows):
    """Forward over an arbitrary row set: gather the 482-col slices once."""
    if state_gpu is not None:
        rg = torch.from_numpy(rows).to(DEVICE)
        x = state_gpu[rg].float()
        bits = ((act_gpu[rg, None] >> AR_G) & 1).float()
        c = cat_gpu[rg]
        a = atype_gpu[rg]
        s = screen_gpu[rg]
        et = ent_type_gpu[rg]
        ei = ent_id_gpu[rg]
        gg = gold_ge_gpu[rg]
        pr = probes_gpu[rg] if probes_gpu is not None else None
    else:
        x = torch.from_numpy(state_mmap[rows].copy()).to(DEVICE, torch.float32)
        bits = torch.from_numpy(((action_ints[rows, None] >> AR[None, :]) & 1)
                                .astype(np.float32)).to(DEVICE)
        c = torch.from_numpy(cat[rows]).to(DEVICE, torch.long)
        a = torch.from_numpy(atype[rows]).to(DEVICE, torch.long)
        s = torch.from_numpy(screen[rows]).to(DEVICE, torch.long)
        et = torch.from_numpy(ent_type[rows]).to(DEVICE, torch.long)
        ei = torch.from_numpy(ent_id[rows]).to(DEVICE, torch.long)
        gg = torch.from_numpy(gold_ge[rows]).to(DEVICE)
        pr = torch.from_numpy(probes[rows]).to(DEVICE) if probes is not None else None
    g = torch.clamp((x[:, glob_cols] - MEAN) * INV, -8, 8)
    dk_id = x[:, dk_id_cols].to(torch.int64)
    dk_up = x[:, dk_up_cols].to(torch.int64)
    dk_cf = x[:, dk_cf_cols]
    rl_id = x[:, rl_id_cols].to(torch.int64)
    rl_df = x[:, rl_df_cols]
    pt_id = x[:, pt_id_cols].to(torch.int64)
    pt_cf = x[:, pt_cf_cols]
    return model(g, dk_id, dk_up, dk_cf, rl_id, rl_df, pt_id, pt_cf,
                 bits, c, a, s, et, ei, gg, pr)


def train_batch_loss(gs):
    sizes_b = sizes[gs]
    rows = np.repeat(block_start[gs], sizes_b) + np.arange(sizes_b.sum()) - np.repeat(np.cumsum(sizes_b) - sizes_b, sizes_b)
    logit, val, q, qq = fwd_rows(rows)
    gstart = np.concatenate(([0], np.cumsum(sizes_b[:-1])))
    ok = valid_pol[gs]
    if ok.any():
        loc = torch.from_numpy(np.repeat(np.arange(len(gs)), sizes_b)).to(DEVICE)
        gm = torch.full((len(gs),), float("-inf"), device=DEVICE)
        gm.scatter_reduce_(0, loc, logit, reduce="amax", include_self=True)
        lse = gm + torch.zeros(len(gs), device=DEVICE).scatter_add_(
            0, loc, (logit - gm[loc]).exp()).log()
        cpos = torch.from_numpy(gstart[ok] + chosen_off[gs][ok]).to(DEVICE)
        pc = logit[cpos] - lse[loc[cpos]]
        pol_loss = -pc.mean()
    else:
        pol_loss = torch.zeros((), device=DEVICE)
    m = chosen[rows]
    if m.any():
        scr = screen[rows][m]
        tl = torch.from_numpy(value[rows]).to(DEVICE)[m]
        vv = val[m]
        vlosses = []
        for h in range(8):
            mm = (scr == h + 1)
            if mm.any():
                vlosses.append(nn.functional.mse_loss(vv[mm], tl[mm]))
        val_loss = torch.stack(vlosses).mean() if vlosses else torch.zeros((), device=DEVICE)
    else:
        val_loss = torch.zeros((), device=DEVICE)
    qm = q_valid[rows]
    rank_loss = torch.zeros((), device=DEVICE)
    if qm.any():
        ql = torch.from_numpy(q_target[rows]).to(DEVICE)[qm]
        q_loss = nn.functional.mse_loss(q[qm], ql)
        if RANK_LAMBDA > 0:
            lr = np.flatnonzero(q_valid[rows])
            if len(lr) >= 2:
                grp_ids_batch = np.repeat(np.arange(len(gs)), sizes_b)
                gl = grp_ids_batch[lr]
                lw = lw_all[rows[lr]]
                ii: list[int] = []
                jj: list[int] = []
                for gpos in np.unique(gl):
                    sel = np.flatnonzero(gl == gpos)
                    if len(sel) < 2:
                        continue
                    lwg = lw[sel]
                    order = np.argsort(-lwg)
                    cnt = 0
                    for a in range(len(sel)):
                        for b in range(a + 1, len(sel)):
                            if lwg[order[a]] > lwg[order[b]]:
                                ii.append(sel[order[a]])
                                jj.append(sel[order[b]])
                                cnt += 1
                                if cnt >= RANK_MAX_PAIRS:
                                    break
                        if cnt >= RANK_MAX_PAIRS:
                            break
                if ii:
                    qi = q[qm][torch.from_numpy(np.asarray(ii)).to(DEVICE)]
                    qj = q[qm][torch.from_numpy(np.asarray(jj)).to(DEVICE)]
                    rank_loss = nn.functional.relu(RANK_MARGIN - (qi - qj)).mean()
    else:
        q_loss = torch.zeros((), device=DEVICE)
    loss = pol_loss + VLAMBDA * val_loss + QLAMBDA * q_loss + RANK_LAMBDA * rank_loss
    if NQUANTS > 0 and qq is not None and m.any():
        tau = model.qtau.view(1, -1)
        y = tl.unsqueeze(1)
        qp = qq[m]
        diff = y - qp
        pin = torch.maximum(tau * diff, (tau - 1.0) * diff).mean()
        loss = loss + 0.5 * pin
    if not torch.isfinite(loss):
        nonfinite_batches[0] += 1
        if nonfinite_batches[0] <= 10:
            print(f"[train-strategic-tok] WARNING: non-finite loss zeroed "
                  f"({nonfinite_batches[0]}x so far) — masks a NaN bug in the "
                  f"distillation machinery", flush=True)
        loss = torch.zeros((), device=DEVICE)
    return loss, float(pol_loss.detach()), float(val_loss.detach()), float(q_loss.detach())


va_perm = np.concatenate([np.arange(block_start[g], block_start[g] + sizes[g])
                          for g in va_groups])
va_start = np.full(NG, -1, np.int64)
pos = 0
for g in va_groups:
    va_start[g] = pos
    pos += sizes[g]
va_chosen = chosen[va_perm]
va_target = value[va_perm]
va_screen = screen[va_perm]
va_qtarget = q_target[va_perm]
va_qvalid = q_valid[va_perm]


@torch.no_grad()
def evaluate():
    full_logit = np.empty(len(va_perm), np.float32)
    full_val = np.empty(len(va_perm), np.float32)
    full_q = np.empty(len(va_perm), np.float32)
    for lo in range(0, len(va_perm), EVAL_CHUNK):
        hi = min(lo + EVAL_CHUNK, len(va_perm))
        l, v, q, _ = fwd_rows(va_perm[lo:hi])
        full_logit[lo:hi] = l.cpu().numpy()
        full_val[lo:hi] = v.cpu().numpy()
        full_q[lo:hi] = q.cpu().numpy()
    vtarget = va_target
    ch = va_chosen
    vmse = float(np.mean((full_val[ch] - vtarget[ch]) ** 2))
    vmae = float(np.mean(np.abs(full_val[ch] - vtarget[ch])))
    per_screen = {}
    scr_all = va_screen
    for h in range(8):
        sm = (scr_all == h + 1) & ch
        if sm.sum() >= 10:
            per_screen[h + 1] = {
                "mae": float(np.mean(np.abs(full_val[sm] - vtarget[sm]))),
                "rmse": float(np.sqrt(np.mean((full_val[sm] - vtarget[sm]) ** 2))),
                "n": int(sm.sum()),
            }
    qv = va_qvalid
    qmae = float(np.mean(np.abs(full_q[qv] - va_qtarget[qv]))) if qv.any() else 0.0
    qrmse = float(np.sqrt(np.mean((full_q[qv] - va_qtarget[qv]) ** 2))) if qv.any() else 0.0
    q_screen = {}
    for h in range(8):
        sm = (scr_all == h + 1) & qv
        if sm.sum() >= 10:
            q_screen[h + 1] = {
                "mae": float(np.mean(np.abs(full_q[sm] - va_qtarget[sm]))),
                "n": int(sm.sum()),
            }
    top1 = 0
    qtop1 = 0
    margin = 0.0
    ce = 0.0
    ntop = 0
    nqtop = 0
    for g in va_groups:
        sz = sizes[g]
        if sz < 2:
            continue
        lo = va_start[g]
        p = full_logit[lo:lo + sz]
        c = int(chosen_off[g])
        if valid_pol[g]:
            srt = np.sort(p)[::-1]
            top1 += int(np.argmax(p) == c)
            margin += srt[0] - srt[1]
            lse = p.max() + np.log(np.exp(p - p.max()).sum())
            ce += lse - p[c]
            ntop += 1
        qg = qv[lo:lo + sz]
        if qg.sum() >= 2:
            qoracle = np.argmax(va_qtarget[lo:lo + sz])
            qpred = np.argmax(full_q[lo:lo + sz])
            qtop1 += int(qoracle == qpred)
            nqtop += 1
    return {"groups": ntop,
            "policy_top1": top1 / max(1, ntop),
            "margin": margin / max(1, ntop),
            "value_mae": vmae,
            "value_rmse": float(np.sqrt(vmse)),
            "value_n": int(ch.sum()),
            "value_mae_screen": per_screen,
            "q_top1": qtop1 / max(1, nqtop),
            "q_top1_n": nqtop,
            "q_mae": qmae,
            "q_rmse": qrmse,
            "q_n": int(qv.sum()),
            "q_mae_screen": q_screen,
            "val_pol_ce": ce / max(1, ntop)}


def to_py(obj):
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {k: to_py(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_py(x) for x in obj]
    return obj


if __name__ == "__main__":
    # --- Predict-only mode (STRAT_PREDICT_ONLY=1) ---
    if os.environ.get("STRAT_PREDICT_ONLY") == "1":
        import json
        from strategic_gate_contract import classify_group
        ckpt_path = os.environ.get("STRAT_PREDICT_CKPT", "")
        out_csv = os.environ.get("STRAT_PREDICT_OUT", OUT + "_preds.csv")
        threshold = float(os.environ.get("STRAT_PREDICT_THRESHOLD", "1.0"))
        max_groups = int(os.environ.get("STRAT_PREDICT_MAX_GROUPS", "0"))
        if not ckpt_path:
            raise SystemExit("STRAT_PREDICT_ONLY=1 requires STRAT_PREDICT_CKPT=<path>")
        ckpt = torch.load(ckpt_path, map_location=DEVICE, weights_only=False)
        net.load_state_dict(ckpt["state_dict"])
        model.eval()
        print(f"[predict-only] loaded {ckpt_path}", flush=True)
        labelWon = df.labelWon.to_numpy(np.float32) if "labelWon" in df else None
        labelHp  = df.labelHp.to_numpy(np.float32)  if "labelHp"  in df else None
        labelQ_all = (10.0 * labelWon + labelHp) if (labelWon is not None and labelHp is not None) else None
        actionType_all = df.actionType.to_numpy(np.int64) if "actionType" in df else None
        screen_all = df.screen.to_numpy(np.int64)
        c1_all = df.c1.to_numpy(np.int64) if "c1" in df else None
        N_pred = min(NG, max_groups) if max_groups > 0 else NG
        print(f"[predict-only] {N_pred} groups, threshold={threshold}", flush=True)
        # Batch Q prediction over all rows (not per-group)
        chunk = 4096
        q_all = np.empty(nrows, np.float32)
        print(f"[predict-only] running batched forward over {nrows} rows (chunk={chunk})...", flush=True)
        all_rows = np.arange(nrows, dtype=np.int64)
        for lo in range(0, nrows, chunk):
            hi = min(lo + chunk, nrows)
            rows = all_rows[lo:hi]
            with torch.no_grad():
                _, _, q_chunk, _ = fwd_rows(rows)
            q_all[lo:hi] = q_chunk.cpu().numpy()
            if lo % (chunk * 50) == 0 and lo > 0:
                print(f"  {lo}/{nrows} rows", flush=True)
        print(f"[predict-only] forward done, writing groups...", flush=True)
        out = open(out_csv, "w")
        out.write("seed,decIdx,screen,gateKind,owned,ownershipExact,nCand,modelIdx,bestIdx,"
                  "behaviorFallbackIdx,fallbackIdx,fallbackSource,margin,threshold,fired,predQ,labelQ\n")
        for g in range(N_pred):
            sz = int(sizes[g])
            if sz < 2:
                continue
            lo = int(block_start[g])
            rows = all_rows[lo:lo + sz]
            scr = int(screen_all[lo])
            group_atypes = actionType_all[rows] if actionType_all is not None else [-1]
            kind, owned_flag, exact = classify_group(scr, group_atypes)
            owned = 1 if owned_flag else 0
            q_pred = q_all[rows]
            model_idx = int(np.argmax(q_pred))
            best_idx = -1
            if labelQ_all is not None:
                best_idx = int(np.argmax(labelQ_all[rows]))
            behavior_fb = int(rank_in_group[chosen_row_idx[g]]) if chosen_row_idx[g] >= 0 else -1
            second = np.partition(q_pred, -2)[-2] if sz >= 2 else q_pred[0]
            margin = float(q_pred[model_idx] - second)
            fired = 1 if (owned and margin >= threshold) else 0
            seed_val = int(df.seed.iloc[lo])
            dec_val = int(df.decIdx.iloc[lo])
            pred_str = "|".join(f"{v:.6f}" for v in q_pred)
            label_str = ""
            if labelQ_all is not None:
                label_str = "|".join(f"{v:.6f}" for v in labelQ_all[rows])
            out.write(f"{seed_val},{dec_val},{scr},{int(kind)},{owned},{exact},"
                      f"{sz},{model_idx},{best_idx},{behavior_fb},{behavior_fb},"
                      f"tierb_chosen,{margin:.6f},{threshold:.6f},{fired},"
                      f"{pred_str},{label_str}\n")
        out.close()
        print(f"[predict-only] wrote {out_csv}", flush=True)
        raise SystemExit(0)

    # Dual checkpoint tracking: independently track best CE and best q_top1
    best_ce = float("inf")
    best_qtop1 = float("-inf")
    best_ce_state = None
    best_qtop1_state = None
    best_ce_epoch = 0
    best_qtop1_epoch = 0
    epochs_no_improve = 0
    early_stopped = False
    tr_gs = np.flatnonzero(tr_mask)
    # Seed initial checkpoints from epoch 0 evaluation
    model.eval()
    em0 = evaluate()
    best_ce = em0.get("val_pol_ce", float("inf"))
    best_qtop1 = em0.get("q_top1", float("-inf"))
    best_ce_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
    best_qtop1_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
    print(f"epoch=000 (init) val_pol_ce={best_ce:.4f} q_top1={best_qtop1:.4f}", flush=True)
    for epoch in range(1, EPOCHS + 1):
        t_ep = time.time()
        model.train()
        order = rng.permutation(tr_gs)
        batches = []
        cur, nrows_b = [], 0
        for g in order:
            cur.append(g)
            nrows_b += sizes[g]
            if nrows_b >= BATCH:
                batches.append(np.asarray(cur))
                cur, nrows_b = [], 0
        if cur:
            batches.append(np.asarray(cur))
        p_losses, v_losses, q_losses = [], [], []
        for gs in batches:
            loss, pl, vl, ql = train_batch_loss(gs)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), CLIP)
            opt.step()
            p_losses.append(pl)
            v_losses.append(vl)
            q_losses.append(ql)
        model.eval()
        em = evaluate()
        ce = em.get("val_pol_ce", float("inf"))
        qtop = em.get("q_top1", float("-inf"))
        # Track best CE (minimize)
        if ce < best_ce - MIN_DELTA:
            best_ce = ce
            best_ce_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
            best_ce_epoch = epoch
        # Track best q_top1 (maximize)
        if qtop > best_qtop1 + MIN_DELTA:
            best_qtop1 = qtop
            best_qtop1_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
            best_qtop1_epoch = epoch
        # Early-stop: use SELECT_METRIC for the stopping decision
        primary_val = em[SELECT_METRIC]
        if SELECT_METRIC == "q_top1":
            primary_best = best_qtop1
            primary_improved = primary_val > primary_best + MIN_DELTA
        else:
            primary_best = best_ce if best_ce_epoch > 0 else float("inf")
            primary_improved = primary_val < primary_best - MIN_DELTA
        if primary_improved:
            epochs_no_improve = 0
        else:
            epochs_no_improve += 1
            if PATIENCE and epochs_no_improve >= PATIENCE:
                print(f"early stop after epoch {epoch}: no improvement for {PATIENCE} epochs", flush=True)
                early_stopped = True
                break
        if epoch == 1 or epoch % 10 == 0 or epoch == EPOCHS:
            print(f"epoch={epoch:03d} ({time.time() - t_ep:5.1f}s) train_pol={np.mean(p_losses):.4f} "
                  f"train_val={np.mean(v_losses):.4f} train_q={np.mean(q_losses):.4f} "
                  f"val_pol_ce={em['val_pol_ce']:.4f} q_top1={em.get('q_top1',0):.4f} "
                  f"metrics={to_py(em)}", flush=True)

    if not early_stopped and EPOCHS > 1:
        print(f"reached max epochs ({EPOCHS}) without early stop", flush=True)

    # Save both best checkpoints
    for name, state, val, epoch_num in [("ce", best_ce_state, best_ce, best_ce_epoch),
                                         ("qtop1", best_qtop1_state, best_qtop1, best_qtop1_epoch)]:
        if state is None:
            print(f"warning: no best_{name} checkpoint saved", flush=True)
            continue
        net.load_state_dict(state)
        model.eval()
        eval_metrics = to_py(evaluate())
        # Serialize CPU state dict as a COPY. net.cpu() would move the live model
        # off DEVICE, so the next checkpoint's compiled evaluate() would feed CPU
        # parameters into Triton kernels ("Pointer argument ... cpu tensor?").
        ckpt = {"state_dict": {k: v.detach().cpu() for k, v in net.state_dict().items()},
                "mean": mean, "inv": inv,
                "metrics": eval_metrics, "rung": RUNG, "nrows": int(nrows),
                "features": NFILE, "transformer": TRANSFORMER,
                "nquants": NQUANTS, "ncross": CROSS, "nprobes": NPROBES}
        ckpt_path = f"{OUT}_best_{name}.pt"
        metrics_path = f"{OUT}_best_{name}_metrics.json"
        os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
        torch.save(ckpt, ckpt_path)
        with open(metrics_path, "w") as f:
            json.dump(eval_metrics, f, indent=2)
        print(f"best {name} (epoch {epoch_num}, value={val:.4f}): {eval_metrics}", flush=True)
        print(f"wrote {ckpt_path}, {metrics_path}", flush=True)

    # Also save the default (SELECT_METRIC) checkpoint at the usual OUT path for compatibility
    default_state = best_ce_state if SELECT_METRIC == "val_pol_ce" else best_qtop1_state
    if default_state is not None:
        net.load_state_dict(default_state)
        model.eval()
        eval_metrics = to_py(evaluate())
        torch.save({"state_dict": {k: v.detach().cpu() for k, v in net.state_dict().items()},
                    "mean": mean, "inv": inv,
                    "metrics": eval_metrics, "rung": RUNG, "nrows": int(nrows),
                    "features": NFILE, "transformer": TRANSFORMER,
                    "nquants": NQUANTS, "ncross": CROSS, "nprobes": NPROBES},
                   OUT + ".pt")
        with open(OUT + "_metrics.json", "w") as f:
            json.dump(eval_metrics, f, indent=2)
        print(f"wrote {OUT}.pt, {OUT}_metrics.json", flush=True)
