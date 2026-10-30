#!/usr/bin/env python3
"""Fine-tune heart1.pt's encoder on Act-4 outcomes, same seed-grouped CV as core.oof (PC GPU).
usage: heart1_finetune.py ENTRIES.jsonl.gz HEART1_PT SILVERBOT_DIR OUT.npz [--mode frozen|top2|full] [--reps 0,1,2]
Rows with seed % 4 == 3 are never trained on or predicted (NaN). For each rep r and fold f (folds as core.folds:
rng(1000 + r).permutation(unique seeds), i % 5), train on the other folds minus the inner-validation fold (f + 1) % 5,
early-stop on it, predict fold f. Head: [pooled (256), src_run1, strong] -> 128 ReLU -> 1; loss = per-game BCE
(label = mean kill over the entry's games, weight = games). Encoder LR 2e-5 (top2/full), head 1e-3, AdamW wd 1e-2,
batch 64, up to 12 epochs, patience 3. Output: P (reps x N) out-of-fold probabilities + identity."""
import argparse, gzip, json, hashlib, sys, copy, time
from pathlib import Path
import numpy as np, torch
from torch import nn

def trim_record(record):
    record = copy.deepcopy(record)
    if record['obs.mapY'] >= 0:
        keep = [i for i, y in enumerate(record['obs.map.ys']) if y >= record['obs.mapY']]
        for key in ('obs.map.xs', 'obs.map.ys', 'obs.map.roomTypes', 'obs.map.pathXs'):
            record[key] = [record[key][i] for i in keep]
    return record

def folds(seed, k, rep):
    us = np.unique(seed); perm = np.random.default_rng(1000 + rep).permutation(us)
    f = {s: i % k for i, s in enumerate(perm)}; return np.array([f[s] for s in seed])

class Model(nn.Module):
    def __init__(s, enc, dim):
        super().__init__(); s.enc = enc
        s.head = nn.Sequential(nn.Linear(dim + 2, 128), nn.ReLU(), nn.Dropout(0.1), nn.Linear(128, 1))
    def forward(s, batch, flags):
        _, _, pooled = s.enc(batch, return_pooled=True)
        return s.head(torch.cat([pooled.float(), flags], -1)).squeeze(-1)

def main():
    a = argparse.ArgumentParser(); a.add_argument('entries'); a.add_argument('checkpoint'); a.add_argument('silverbot'); a.add_argument('out')
    a.add_argument('--mode', default='top2', choices=('frozen', 'top2', 'full')); a.add_argument('--reps', default='0,1,2')
    a.add_argument('--device', default='cuda'); a.add_argument('--epochs', type=int, default=12); a.add_argument('--batch', type=int, default=64)
    a.add_argument('--enc_lr', type=float, default=2e-5)
    args = a.parse_args(); dev = args.device
    sb = Path(args.silverbot); sys.path[:0] = [str(sb), str(sb / 'build')]
    from silverbot import network
    sd = torch.load(args.checkpoint, map_location='cpu', weights_only=True)
    hp = network.ModelHP(dim=256, n_layers=4, n_heads=8, mlp_dim_mult=4, use_value_head=True)
    rows = [json.loads(l) for l in gzip.open(args.entries, 'rt')]
    N = len(rows); seed = np.array([r['seed'] for r in rows]); y = np.array([r['y'] for r in rows], np.float32); n = np.array([r['n'] for r in rows], np.float32)
    flags = np.array([[r['src'] == 'run1', r['src'] != 'extra'] for r in rows], np.float32)
    recs = [{**trim_record(r['record']), 'chosen_idx': 0, 'outcome': 0.} for r in rows]
    pool = seed % 4 != 3
    def batches(idx, bs, shuffle, rng=None):
        idx = rng.permutation(idx) if shuffle else idx
        for s in range(0, len(idx), bs):
            b = idx[s:s + bs]
            yield b, network.move_to_device(network.collate_fn([recs[i] for i in b]), dev), torch.tensor(flags[b], device=dev)
    def predict(m, idx):
        m.eval(); out = []
        with torch.inference_mode():
            for b, bt, fl in batches(idx, 256, False): out.append(torch.sigmoid(m(bt, fl)).float().cpu().numpy())
        return np.concatenate(out)
    reps = [int(x) for x in args.reps.split(',')]
    P = np.full((len(reps), N), np.nan); log = []; t0 = time.time()
    for ri, rep in enumerate(reps):
        fo = folds(seed, 5, rep)
        for f in range(5):
            te = np.where(pool & (fo == f))[0]; iv = np.where(pool & (fo == (f + 1) % 5))[0]; tr = np.where(pool & (fo != f) & (fo != (f + 1) % 5))[0]
            torch.manual_seed(29 + rep * 10 + f)
            enc = network.NN(hp); enc.load_state_dict(sd, strict=True); enc.to(dev)
            for p in enc.parameters(): p.requires_grad_(args.mode == 'full')
            if args.mode == 'top2':
                for name, p in enc.named_parameters():
                    if name.startswith('layers.2') or name.startswith('layers.3') or not name.startswith(('layers.', 'obs_embed', 'choice_embed')): p.requires_grad_(True)
            m = Model(enc, 256).to(dev)
            groups = [{'params': m.head.parameters(), 'lr': 1e-3}]
            encp = [p for p in enc.parameters() if p.requires_grad]
            if encp: groups.append({'params': encp, 'lr': args.enc_lr})
            opt = torch.optim.AdamW(groups, weight_decay=1e-2); rng = np.random.default_rng(rep * 10 + f)
            yv, nv = y[iv], n[iv]; best = (1e9, None, -1)
            for ep in range(args.epochs):
                m.train()
                if args.mode == 'frozen': enc.eval()
                for b, bt, fl in batches(tr, args.batch, True, rng):
                    out = m(bt, fl); yt = torch.tensor(y[b], device=dev); wt = torch.tensor(n[b], device=dev)
                    loss = (nn.functional.binary_cross_entropy_with_logits(out, yt, reduction='none') * wt).sum() / wt.sum()
                    opt.zero_grad(); loss.backward(); opt.step()
                pv = np.clip(predict(m, iv), 1e-6, 1 - 1e-6)
                v = float((-(yv * np.log(pv) + (1 - yv) * np.log(1 - pv)) * nv).sum() / nv.sum())
                log.append(dict(rep=rep, fold=f, ep=ep, val=v, t=round(time.time() - t0)))
                print(json.dumps(log[-1]), flush=True)
                if v < best[0]: best = (v, {k: t.detach().clone() for k, t in m.state_dict().items()}, ep)
                elif ep - best[2] >= 3: break
            m.load_state_dict(best[1]); P[ri, te] = predict(m, te)
            del m, enc, opt; torch.cuda.empty_cache()
    ident = {'checkpoint_sha256': hashlib.sha256(open(args.checkpoint, 'rb').read()).hexdigest(),
             'entries_sha256': hashlib.sha256(open(args.entries, 'rb').read()).hexdigest(), 'mode': args.mode, 'reps': reps,
             'enc_lr': args.enc_lr, 'epochs': args.epochs, 'batch': args.batch, 'torch': torch.__version__, 'seconds': round(time.time() - t0)}
    np.savez_compressed(args.out, P=P, reps=np.array(reps), identity=json.dumps(ident), log=json.dumps(log))
    print(json.dumps(ident))

if __name__ == '__main__':
    main()
