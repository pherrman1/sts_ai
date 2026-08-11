#!/usr/bin/env python3
"""Preprocess fairgen CSVs to memory-mapped numpy arrays for streaming training.

Value:  (N, 1766) float32 state + (N, 2) float32 labels
Policy: (M, 1766) float32 state + (M, 14) float32 action + (M,) int32 visit/total
        + group boundaries (start, end) for each (seed, fightIdx, decIdx).

All files are memmap-backed; training reads slices without loading the whole file.
"""
import numpy as np, pandas as pd, os, sys, gc

VAL_CSV = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fair_final_v.csv"
POL_CSV = sys.argv[2] if len(sys.argv) > 2 else "/tmp/fair_final_p.csv"
OUT_DIR = sys.argv[3] if len(sys.argv) > 3 else "/tmp/pvnet_data"
CHUNK = int(os.environ.get("PREP_CHUNK", "100000"))

os.makedirs(OUT_DIR, exist_ok=True)

# ── Schema ───────────────────────────────────────────────────────────────────
val_header = list(pd.read_csv(VAL_CSV, nrows=0).columns)
VAL_LABELS = ("seed", "fightIdx", "won", "endHp")
canonical = [c for c in val_header if c not in VAL_LABELS]
assert len(canonical) == 1766, f"Expected 1766, got {len(canonical)}"

pol_header = list(pd.read_csv(POL_CSV, nrows=0).columns)
POL_META = ("seed", "fightIdx", "decIdx", "visit", "total")
pol_canonical = [c for c in pol_header if c not in POL_META]
assert len(pol_canonical) == 1780

# Column types for mixed precision
card_cols = [c for c in canonical if c.startswith(("hd", "dr", "ds", "ex"))]
relic_cols = [c for c in canonical if c.startswith("r") and c[1:].isdigit()]
potion_cols = [c for c in canonical if c.startswith("pot") and c[1:].isdigit()]
monster_id_cols = [c for c in canonical if c.startswith("m") and c.endswith("Id")]
monster_stat_cols = [c for c in canonical if (c.startswith("m") and
    any(c.endswith(s) for s in ("Hp", "Block", "Str", "Intent", "Atk", "Vuln", "Weak", "Poison")))]
scalar_cols = [c for c in canonical if c not in set(card_cols + relic_cols + potion_cols +
               monster_id_cols + monster_stat_cols)]

print(f"[schema] {len(scalar_cols)} float32 scalars, {len(card_cols)} card cols, "
      f"{len(relic_cols)} relic cols", flush=True)

# ── Value data → memmap ──────────────────────────────────────────────────────
print("[prep] value CSV → memmap...", flush=True)
reader = pd.read_csv(VAL_CSV, chunksize=CHUNK)
val_labels = []
n_val = 0
# First pass: count rows
for df in reader:
    n_val += len(df)
print(f"  {n_val} rows", flush=True)

# Create memmaps
val_feats = np.memmap(f"{OUT_DIR}/val_feats.npy", dtype=np.float32,
                      mode='w+', shape=(n_val, 1766))
val_labels_mm = np.memmap(f"{OUT_DIR}/val_labels.npy", dtype=np.float32,
                          mode='w+', shape=(n_val, 2))

# Second pass: write
reader = pd.read_csv(VAL_CSV, chunksize=CHUNK)
offset = 0
for df in reader:
    n = len(df)
    val_feats[offset:offset+n] = df[canonical].to_numpy(np.float32)
    val_labels_mm[offset:offset+n, 0] = df["won"].to_numpy(np.float32)
    val_labels_mm[offset:offset+n, 1] = df["endHp"].to_numpy(np.float32)
    offset += n
    if offset % (CHUNK * 5) == 0:
        print(f"  value {offset}/{n_val}", flush=True)
val_feats.flush(); val_labels_mm.flush()
del val_feats, val_labels_mm; gc.collect()
print(f"  value done ({n_val} rows)", flush=True)

# ── Policy data → memmap ─────────────────────────────────────────────────────
print("[prep] policy CSV → memmap...", flush=True)
reader = pd.read_csv(POL_CSV, chunksize=CHUNK)
n_pol = 0
for df in reader:
    n_pol += len(df)
print(f"  {n_pol} rows", flush=True)

pol_state = np.memmap(f"{OUT_DIR}/pol_state.npy", dtype=np.float32,
                      mode='w+', shape=(n_pol, 1766))
pol_action = np.memmap(f"{OUT_DIR}/pol_action.npy", dtype=np.float32,
                       mode='w+', shape=(n_pol, 14))
pol_visit = np.memmap(f"{OUT_DIR}/pol_visit.npy", dtype=np.int32,
                      mode='w+', shape=(n_pol,))
pol_total = np.memmap(f"{OUT_DIR}/pol_total.npy", dtype=np.int32,
                      mode='w+', shape=(n_pol,))
pol_meta = np.memmap(f"{OUT_DIR}/pol_meta.npy", dtype=np.int64,
                     mode='w+', shape=(n_pol, 3))

# Action columns
action_names = [c for c in pol_header if c not in canonical and c not in POL_META]
assert len(action_names) == 14, f"Expected 14 action cols, got {len(action_names)}: {action_names}"

reader = pd.read_csv(POL_CSV, chunksize=CHUNK)
offset = 0
for df in reader:
    n = len(df)
    pol_state[offset:offset+n] = df[canonical].to_numpy(np.float32)
    pol_action[offset:offset+n] = df[action_names].to_numpy(np.float32)
    pol_visit[offset:offset+n] = df["visit"].to_numpy(np.int32)
    pol_total[offset:offset+n] = df["total"].to_numpy(np.int32)
    pol_meta[offset:offset+n, 0] = df["seed"].to_numpy(np.int64)
    pol_meta[offset:offset+n, 1] = df["fightIdx"].to_numpy(np.int32)
    pol_meta[offset:offset+n, 2] = df["decIdx"].to_numpy(np.int32)
    offset += n
    if offset % (CHUNK * 5) == 0:
        print(f"  policy {offset}/{n_pol}", flush=True)
pol_state.flush(); pol_action.flush(); pol_visit.flush(); pol_total.flush(); pol_meta.flush()
del pol_state, pol_action, pol_visit, pol_total; gc.collect()
print(f"  policy state done ({n_pol} rows)", flush=True)

# ── Group boundaries ─────────────────────────────────────────────────────────
print("[prep] computing decision group boundaries...", flush=True)
# Sort by (seed, fightIdx, decIdx) -- they should already be sorted in CSV order
# but let's verify by computing a composite key and finding changes
keys = np.zeros(n_pol, dtype=np.int64)
BATCH_SIZE = 5000000  # process in batches to save RAM
for b_start in range(0, n_pol, BATCH_SIZE):
    b_end = min(b_start + BATCH_SIZE, n_pol)
    bk = pol_meta[b_start:b_end]
    keys[b_start:b_end] = (bk[:, 0].astype(np.int64) * 100_000_000 +
                           bk[:, 1].astype(np.int64) * 10_000 +
                           bk[:, 2].astype(np.int64))
    if b_start % (BATCH_SIZE * 2) == 0:
        print(f"  keys {b_start}/{n_pol}", flush=True)

# Find where the key changes
diffs = np.zeros(n_pol, dtype=np.bool_)
for b_start in range(0, n_pol - 1, BATCH_SIZE):
    b_end = min(b_start + BATCH_SIZE, n_pol - 1)
    diffs[b_start:b_end] = keys[b_start:b_end] != keys[b_start+1:b_end+1]
boundaries = np.where(diffs)[0] + 1
del diffs, keys; gc.collect()

starts = np.concatenate([[0], boundaries])
ends = np.concatenate([boundaries, [n_pol]])
group_sizes = ends - starts

print(f"  {len(starts)} decision groups, avg size={group_sizes.mean():.1f}, "
      f"max={group_sizes.max()}, min={group_sizes.min()}", flush=True)

# Save groups as int32 start/end
np.save(f"{OUT_DIR}/pol_groups.npy",
        np.column_stack([starts.astype(np.int32), ends.astype(np.int32)]))
np.save(f"{OUT_DIR}/canonical_cols.npy", np.array(canonical))
np.save(f"{OUT_DIR}/action_cols.npy", np.array(action_names))

# Metadata
with open(f"{OUT_DIR}/info.txt", "w") as f:
    f.write(f"value_rows={n_val}\npolicy_rows={n_pol}\n")
    f.write(f"policy_groups={len(starts)}\n")
    f.write(f"nfeat={len(canonical)}\nnaction={len(action_names)}\n")

print(f"\n[done] data in {OUT_DIR}/", flush=True)
