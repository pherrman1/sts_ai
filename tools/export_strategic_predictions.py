#!/usr/bin/env python3
"""Export strategic model predictions in deployment-aligned schema.

Usage:
  python3 tools/export_strategic_predictions.py \
      <tierb_csv> <checkpoint.pt> <tok_state.bin> <out.csv> \
      [--threshold 1.0]

Produces a CSV with columns: seed,decIdx,screen,nCand,modelIdx,bestIdx,
chosenIdx,margin,fired,predQ,labelQ
where predQ and labelQ are pipe-delimited lists of per-candidate Q values.

The CSV is consumed by tools/analyze_strategic_metrics.py.
"""
import os, sys, json, argparse
import numpy as np
import pandas as pd
import torch
from torch import nn

# Import the token network
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from strategic_tok_net import Net, NCARD, NREL, NPOT, MAXD, MAXR, MAXP, NGLOB, NRAW
from strategic_tok_contract import build_globals, make_layout

CHUNK = 4096


def load_token_state(path, device):
    """Load the precomputed token state from bin file."""
    state = np.fromfile(path, dtype=np.float16)
    nrows = len(state) // (NGLOB + MAXD * 3 + MAXR * 2 + MAXP * 2)
    state = state[:nrows * (NGLOB + MAXD * 3 + MAXR * 2 + MAXP * 2)]
    state = state.reshape(nrows, NGLOB + MAXD * 3 + MAXR * 2 + MAXP * 2)
    state = state.astype(np.float32)
    return torch.from_numpy(state).to(device)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", help="Tier-B CSV")
    parser.add_argument("checkpoint", help=".pt checkpoint")
    parser.add_argument("tok_state", help="tok_state.bin")
    parser.add_argument("out", help="output CSV")
    parser.add_argument("--threshold", type=float, default=1.0)
    parser.add_argument("--max-groups", type=int, default=0,
                        help="limit groups for smoke testing")
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device: {device}", flush=True)

    # Load checkpoint
    ckpt = torch.load(args.checkpoint, map_location=device, weights_only=False)
    rung = ckpt.get("rung", 4)
    transformer = ckpt.get("transformer", 0)
    ncross = ckpt.get("ncross", 0)
    nprobes = ckpt.get("nprobes", 0)
    ckpt_mean = ckpt["mean"]
    ckpt_inv = ckpt["inv"]
    print(f"checkpoint: rung={rung} transformer={transformer} ncross={ncross} nprobes={nprobes}", flush=True)

    # Build model
    net = Net(rung=rung, transformer=transformer, ncross=ncross, nprobes=nprobes)
    net.load_state_dict(ckpt["state_dict"])
    net.to(device)
    net.eval()

    # Load CSV and token state
    df = pd.read_csv(args.csv)
    df = df.sort_values(["seed", "decIdx"], kind="stable").reset_index(drop=True)
    print(f"csv: {len(df)} rows, {df.seed.nunique()} seeds", flush=True)

    tok = load_token_state(args.tok_state, device)
    if len(tok) != len(df):
        raise ValueError(f"token state {len(tok)} rows != CSV {len(df)} rows")

    # Extract state columns between 'chosen' and 'won' (same contract as trainer)
    hdr = list(df.columns)
    ci, wi = hdr.index("chosen"), hdr.index("won")
    state_cols = hdr[ci + 1:wi]
    need_labels = "labelWon" in df.columns
    layout = make_layout(state_cols)
    glob_raw = build_globals(df[state_cols], layout)
    glob_norm = (glob_raw - ckpt_mean[:NGLOB]) * ckpt_inv[:NGLOB]
    glob_t = torch.from_numpy(glob_norm.astype(np.float32)).to(device)

    # Group by (seed, decIdx)
    groups_raw = df.seed.to_numpy(np.int64) * 1000000 + df.decIdx.to_numpy(np.int64)
    grp_vals, grp_ids = np.unique(groups_raw, return_inverse=True)
    NG = len(grp_vals)
    sizes = np.bincount(grp_ids, minlength=NG).astype(np.int64)
    block_start = np.concatenate(([0], np.cumsum(sizes[:-1])))

    order = np.argsort(grp_ids, kind="stable")
    inv_perm = np.empty(len(df), np.int64)
    inv_perm[order] = np.arange(len(df))
    rank_in_group = inv_perm - block_start[grp_ids]

    chosen = df.chosen.to_numpy(np.int64) == 1
    chosen_row_idx = np.full(NG, -1, np.int64)
    cp = np.flatnonzero(chosen)
    chosen_row_idx[grp_ids[cp]] = cp
    cr = np.maximum(chosen_row_idx, 0)
    chosen_off = np.where(chosen_row_idx >= 0,
                          block_start[grp_ids[cr]] + rank_in_group[cr], -1)

    screen = df.screen.to_numpy(np.int64)
    label_q = df.labelWon.to_numpy(np.float32) if need_labels else None

    max_groups = args.max_groups if args.max_groups > 0 else NG
    print(f"predicting {max_groups} of {NG} groups", flush=True)

    out = open(args.out, "w")
    out.write("seed,decIdx,screen,nCand,modelIdx,bestIdx,chosenIdx,margin,fired,predQ,labelQ\n")

    g_start = 0
    for g in range(min(NG, max_groups)):
        sz = int(sizes[g])
        if sz < 2:
            g_start += sz
            continue
        lo = block_start[g]
        rows = np.arange(lo, lo + sz)

        # Q prediction
        q_pred = np.empty(sz, np.float32)
        for i in range(0, sz, CHUNK):
            r = rows[i:i + CHUNK]
            gl = glob_t[r]
            tk = tok[r]
            with torch.no_grad():
                _, _, q, _ = net(gl, tk)
            q_pred[i:i + len(r)] = q.cpu().numpy()

        # Determine indices
        best = int(np.argmax(q_pred))
        second = np.partition(q_pred, -2)[-2] if sz >= 2 else q_pred[0]
        margin = float(q_pred[best] - second)
        fired = 1 if margin >= args.threshold else 0

        model_best = int(np.argmax(q_pred))
        label_best = -1
        if label_q is not None:
            lq = label_q[rows]
            label_best = int(np.argmax(lq))
        else:
            label_best = model_best

        cho = int(chosen_off[g])
        seed_val = int(df.seed.iloc[lo])
        dec_val = int(df.decIdx.iloc[lo])
        scr_val = int(screen[lo])

        pred_str = "|".join(f"{v:.6f}" for v in q_pred)
        label_str = ""
        if label_q is not None:
            lq_vals = label_q[rows]
            label_str = "|".join(f"{v:.6f}" for v in lq_vals)

        out.write(f"{seed_val},{dec_val},{scr_val},{sz},{model_best},{label_best},"
                  f"{cho},{margin:.6f},{fired},{pred_str},{label_str}\n")

        g_start += sz

    out.close()
    print(f"wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
