#!/usr/bin/env python3
"""Run on the PC (heart1.pt + silverbot checkout). Encodes every Act-4 entry record with the frozen heart1 network.
usage: heart1_embed.py ENTRIES.jsonl.gz HEART1_PT SILVERBOT_DIR OUT.npz [--device cuda]
Writes pooled (N x dim) encoder output, the network's value-head output if it has one, and identity hashes.
Model hyperparameters are read off the checkpoint shapes (dim, layers); heads default to 4 (override --heads).
The trim (map rows >= mapY) and the appended-companion pattern follow tools/heart_outcome_value.py (§498)."""
import argparse, gzip, json, hashlib, sys, copy
from pathlib import Path
import numpy as np, torch

def trim_record(record):
    record = copy.deepcopy(record)
    if record['obs.mapY'] >= 0:
        keep = [i for i, y in enumerate(record['obs.map.ys']) if y >= record['obs.mapY']]
        for key in ('obs.map.xs', 'obs.map.ys', 'obs.map.roomTypes', 'obs.map.pathXs'):
            record[key] = [record[key][i] for i in keep]
    return record

def main():
    a = argparse.ArgumentParser(); a.add_argument('entries'); a.add_argument('checkpoint'); a.add_argument('silverbot'); a.add_argument('out')
    a.add_argument('--device', default='cuda'); a.add_argument('--heads', type=int, default=4); a.add_argument('--batch', type=int, default=256)
    a.add_argument('--mlp_mult', type=int, default=4)
    args = a.parse_args()
    sb = Path(args.silverbot); sys.path[:0] = [str(sb), str(sb / 'build')]
    from silverbot import network
    sd = torch.load(args.checkpoint, map_location='cpu', weights_only=True)
    shapes = {k: tuple(v.shape) for k, v in sd.items()}
    print(json.dumps(shapes, indent=0)[:3000])
    dim = next(v[-1] for k, v in shapes.items() if 'emb' in k.lower() and len(v) == 2)
    layers = len({k.split('.')[k.split('.').index('layers') + 1] for k in sd if '.layers.' in k}) or 2
    use_value = any('value' in k.lower() for k in sd)
    hp = network.ModelHP(dim=dim, n_layers=layers, n_heads=args.heads, mlp_dim_mult=args.mlp_mult, use_value_head=use_value)
    net = network.NN(hp); net.load_state_dict(sd, strict=True); net = net.requires_grad_(False).eval().to(args.device)
    rows = [json.loads(l) for l in gzip.open(args.entries, 'rt')]
    pooled, value, logit0 = [], [], []
    for s in range(0, len(rows), args.batch):
        chunk = rows[s:s + args.batch]
        recs = [{**trim_record(r['record']), 'chosen_idx': 0, 'outcome': 0.} for r in chunk]
        batch = network.move_to_device(network.collate_fn(recs), args.device)
        with torch.inference_mode():
            out = net(batch, return_pooled=True)
        logits, v, p = out[0], out[1], out[2]
        assert torch.isfinite(p).all()
        pooled.append(p.float().cpu().numpy())
        value.append(v.float().cpu().numpy().reshape(len(chunk), -1) if v is not None else np.full((len(chunk), 1), np.nan))
    P = np.concatenate(pooled); V = np.concatenate(value)
    ident = {'checkpoint_sha256': hashlib.sha256(open(args.checkpoint, 'rb').read()).hexdigest(),
             'entries_sha256': hashlib.sha256(open(args.entries, 'rb').read()).hexdigest(),
             'hp': dict(dim=dim, n_layers=layers, n_heads=args.heads, mlp_dim_mult=args.mlp_mult, use_value_head=use_value),
             'n': len(rows), 'pooled_dim': int(P.shape[1]), 'value_cols': int(V.shape[1])}
    np.savez_compressed(args.out, i=np.array([r['i'] for r in rows]), pooled=P, value=V, identity=json.dumps(ident))
    print(json.dumps(ident, indent=1))

if __name__ == '__main__':
    main()
