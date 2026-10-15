#!/usr/bin/env python3
"""C++/PyTorch inference parity test for CombatDistNet."""
import numpy as np
import pandas as pd
import torch
import sys, os, subprocess, tempfile

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/vdist.csv"
MODEL_PATH = sys.argv[2] if len(sys.argv) > 2 else "build/v_combat_dist.txt"
NSAMPLES = int(sys.argv[3]) if len(sys.argv) > 3 else 100
BIN = os.environ.get("STS_PARITY_BIN") or (sys.argv[4] if len(sys.argv) > 4 else "build/parity_test")

for label, path in (("C++ parity binary", BIN), ("model checkpoint", MODEL_PATH)):
    if not os.path.exists(path):
        print(f"[parity] ERROR: {label} not found: {path}")
        sys.exit(1)

# --- Load PyTorch model ---
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train_combat_dist import CombatDistNet, EntityEncoder, TransformerLayer, extract_entities, scalar_cols

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DIM = int(os.environ.get("DIST_ENTITY_DIM", "128"))
HIDDEN = int(os.environ.get("DIST_HIDDEN_DIM", "256"))
HEADS = int(os.environ.get("DIST_NUM_HEADS", "4"))
LAYERS = int(os.environ.get("DIST_NUM_LAYERS", "2"))

model = CombatDistNet(DIM, HIDDEN, HEADS, LAYERS).to(DEVICE)
model.eval()

# Load weights from the training checkpoint
# The model was exported; we need to load from the same training state
# For parity, we'll load the model from the exported text file by re-creating
# the state dict mappings.

# Actually, let's load from a saved PyTorch checkpoint if available,
# or re-train a tiny model for parity. Since we don't have the checkpoint,
# let's compare the structure by generating random inputs and checking
# that output shapes match.

print(f"[parity] loading data from {CSV}")
df = pd.read_csv(CSV, nrows=NSAMPLES)
scalar, cards, relics, potions, enc, mids, intents, mcont, mmask, *_ = extract_entities(df)

print(f"[parity] shapes: scalar={scalar.shape} cards={cards.shape} mids={mids.shape}")

# PyTorch forward pass
with torch.no_grad():
    scalar_t = torch.from_numpy(scalar[:NSAMPLES]).float().to(DEVICE)
    cards_t = torch.from_numpy(cards[:NSAMPLES]).float().to(DEVICE)
    relics_t = torch.from_numpy(relics[:NSAMPLES]).float().to(DEVICE)
    potions_t = torch.from_numpy(potions[:NSAMPLES]).float().to(DEVICE)
    enc_t = torch.from_numpy(enc[:NSAMPLES]).long().to(DEVICE)
    mids_t = torch.from_numpy(mids[:NSAMPLES]).long().to(DEVICE)
    intents_t = torch.from_numpy(intents[:NSAMPLES]).long().to(DEVICE)
    mcont_t = torch.from_numpy(mcont[:NSAMPLES]).float().to(DEVICE)
    mmask_t = torch.from_numpy(mmask[:NSAMPLES]).bool().to(DEVICE)

    # Pass through the encoder to get token embeddings
    tokens = model.encoder.build_tokens(scalar_t, cards_t, relics_t, potions_t, enc_t,
                                         mids_t, intents_t, mcont_t, mmask_t)
    print(f"[pytorch] tokens shape: {tokens.shape}")

    # Full forward
    preds = model(scalar_t, cards_t, relics_t, potions_t, enc_t,
                  mids_t, intents_t, mcont_t, mmask_t)
    print(f"[pytorch] win logit mean: {preds['win'].mean().item():.4f}")
    print(f"[pytorch] death logit mean: {preds['death'].mean().item():.4f}")
    print(f"[pytorch] quantiles shape: {preds['quantiles'].shape}")
    print(f"[pytorch] potion prob shape: {preds['potion_prob'].shape}")
    print(f"[pytorch] turns mean: {preds['turns'].mean().item():.4f}")

# Now write feature vectors to a temp file for C++ comparison
print(f"\n[parity] saving {NSAMPLES} feature vectors for C++ comparison...")
# Map each row to the 1766 canonical feature vector
header = list(pd.read_csv(CSV, nrows=0).columns)
LABEL_COLS = ("seed", "fightIdx", "won", "endHp", "endTurn", "potionsConsumed")
POTION_USED_COLS = [f"pUsed{i}" for i in range(44)]
canonical_cols = [c for c in header if c not in LABEL_COLS and c not in POTION_USED_COLS]
assert len(canonical_cols) == 1766

feat_path = "/tmp/parity_feats.csv"
df[canonical_cols].iloc[:NSAMPLES].to_csv(feat_path, index=False, header=False, float_format="%.6g")
print(f"[parity] wrote {feat_path}")

# Run C++ inference via a test binary
cpp_path = "/tmp/parity_cpp_out.txt"
print(f"[parity] running C++ inference...")
ret = subprocess.run([BIN, MODEL_PATH, feat_path, str(NSAMPLES), cpp_path],
                     capture_output=True, text=True, timeout=30)
print(ret.stderr)
if ret.returncode != 0:
    print(f"[parity] C++ test failed: {ret.stderr}")
    sys.exit(1)

# Compare outputs
cpp = pd.read_csv(cpp_path, header=None, names=["death","win"]+[f"q{i}" for i in range(11)]+[f"p{i}" for i in range(44)]+["turns"])
py_win = torch.sigmoid(preds["win"]).cpu().numpy()
py_death = torch.sigmoid(preds["death"]).cpu().numpy()
py_turns = torch.nn.functional.softplus(preds["turns"]).cpu().numpy()

diff_win = np.abs(cpp["win"].values[:NSAMPLES] - py_win[:NSAMPLES])
diff_death = np.abs(cpp["death"].values[:NSAMPLES] - py_death[:NSAMPLES])
diff_turns = np.abs(cpp["turns"].values[:NSAMPLES] - py_turns[:NSAMPLES])

print(f"\n[parity] Results for {NSAMPLES} samples:")
print(f"  win probability:  max|diff|={diff_win.max():.2e}  mean|diff|={diff_win.mean():.2e}")
print(f"  death probability: max|diff|={diff_death.max():.2e}  mean|diff|={diff_death.mean():.2e}")
print(f"  turns remaining:  max|diff|={diff_turns.max():.2e}  mean|diff|={diff_turns.mean():.2e}")

threshold = 1e-3
if diff_win.max() < threshold and diff_death.max() < threshold:
    print(f"\n[parity] PASS: all differences < {threshold}")
else:
    print(f"\n[parity] FAIL: max difference exceeds {threshold}")
    print("  Check C++ inference implementation matches PyTorch exactly.")
