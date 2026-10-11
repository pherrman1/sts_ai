import sys, json, glob, numpy as np
target = sys.argv[1]
Z = np.load('/tmp/claude-0/a401/work/a20.npz')
va = Z['splits'] == 'VAL'; y = Z[target][va]; seeds = Z['seeds'][va]
us, si = np.unique(seeds, return_inverse=True)
rng = np.random.default_rng(438)
B = [rng.integers(0, len(us), len(us)) for _ in range(1000)]
cnt = np.bincount(si, minlength=len(us))
def loss(p):
    if target == 'won':
        p = np.clip(p, 1e-6, 1 - 1e-6); return -(y * np.log(p) + (1 - y) * np.log(1 - p))
    return (p - y) ** 2
def auc(p):
    o = np.argsort(p); r = np.empty(len(p)); r[o] = np.arange(1, len(p) + 1); n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
recs = [json.loads(l) for l in open(f'/tmp/claude-0/a401/work/abl_{target}.jsonl')]
full = loss(np.load(f'/tmp/claude-0/a401/work/pred_{target}_FULL.npy'))
rows = []
for r in recs:
    p = np.load(f"/tmp/claude-0/a401/work/pred_{target}_{r['arm']}.npy"); l = loss(p); d = l - full
    per = np.bincount(si, weights=d, minlength=len(us))
    bs = [per[b].sum() / cnt[b].sum() for b in B]
    m = dict(arm=r['arm'], n_feats=r['n_feats'], trees=r['trees'], metric=float(l.mean()),
             delta=float(d.mean()), ci=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))])
    if target == 'won':
        m['auc'] = float(auc(p))
    else:
        m['rmse'] = float(np.sqrt(l.mean()))
    rows.append(m)
rows.sort(key=lambda m: -m['delta'])
json.dump(dict(target=target, val_rows=int(va.sum()), val_runs=len(us), arms=rows),
          open(f'/tmp/claude-0/a401/work/abl_{target}_scored.json', 'w'), indent=1)
lab = 'MSE' if target == 'floor' else 'logloss'
print(f'{target}: VAL rows {va.sum()}, runs {len(us)}; delta = arm - FULL {lab} (positive = worse without)')
for m in rows:
    extra = f"rmse={m['rmse']:.3f}" if target == 'floor' else f"auc={m['auc']:.4f}"
    print(f"{m['arm']:28s} n={m['n_feats']:3d} trees={m['trees']:4d} {lab}={m['metric']:.4f} d={m['delta']:+.4f} [{m['ci'][0]:+.4f},{m['ci'][1]:+.4f}] {extra}")
