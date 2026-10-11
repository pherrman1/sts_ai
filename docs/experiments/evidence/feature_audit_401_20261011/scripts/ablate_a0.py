"""#401 A0 cross-check: retrain on #334 TRAIN seeds (ES on a hashed TRAIN subset), report #334 VALIDATION.
TEST seeds were excluded at load time (load_a0.py)."""
import sys, json, hashlib, numpy as np, xgboost as xgb
sys.path.insert(0, '/tmp/claude-0/a401/work')
from groups import group_of
Z = np.load('/tmp/claude-0/a401/work/a0.npz')
names = list(Z['names']); X = Z['X']; y = Z['y']; seeds = Z['seeds']; sp = Z['splits']
b0 = [l.strip() for l in open('/tmp/claude-0/a401/work/feats_b0.txt')]
fm = [n for n in names if group_of(n) == 'forward_map']
hidden = {'future_encounters(hidden)', 'queue_counters', 'rng_counters(hidden)'}
pub = [n for n in b0 if group_of(n) not in hidden]
es_seed = np.array([int(hashlib.sha256(f'issue401-a0-es:{s}'.encode()).hexdigest()[:8], 16) / 2**32 < 0.2 for s in seeds])
tr = (sp == 'TRAIN') & ~es_seed; es = (sp == 'TRAIN') & es_seed; va = sp == 'VALIDATION'
arms = {'FULL': b0, 'PUBLIC(-hidden)': pub, '+forward_map': b0 + fm, 'PUBLIC+forward_map': pub + fm,
        '-relics': [n for n in b0 if group_of(n) != 'relics'], '-upgrades': [n for n in b0 if group_of(n) != 'upgrades']}
P = dict(objective='binary:logistic', eval_metric='logloss', eta=0.05, max_depth=4, subsample=0.8,
         colsample_bytree=0.5, min_child_weight=20, tree_method='hist', nthread=4)
yv = y[va]; us, si = np.unique(seeds[va], return_inverse=True)
rng = np.random.default_rng(438); B = [rng.integers(0, len(us), len(us)) for _ in range(1000)]
cnt = np.bincount(si, minlength=len(us))
def ll(p): p = np.clip(p, 1e-6, 1 - 1e-6); return -(yv * np.log(p) + (1 - yv) * np.log(1 - p))
L = {}
for arm, fl in arms.items():
    idx = [names.index(n) for n in fl]; ls = []
    for sd in (401, 402, 403):
        P['seed'] = sd
        dtr = xgb.DMatrix(X[tr][:, idx], label=y[tr]); des = xgb.DMatrix(X[es][:, idx], label=y[es])
        b = xgb.train(P, dtr, 3000, evals=[(des, 'es')], early_stopping_rounds=100, verbose_eval=False)
        ls.append(ll(b.predict(xgb.DMatrix(X[va][:, idx]), iteration_range=(0, b.best_iteration + 1))))
    L[arm] = np.mean(ls, 0)
    print(arm, len(fl), 'VAL logloss (3-seed avg pred loss)', round(float(L[arm].mean()), 4),
          'per-seed', [round(float(l.mean()), 4) for l in ls], flush=True)
res = {}
for arm in arms:
    d = L[arm] - L['FULL']; per = np.bincount(si, weights=d, minlength=len(us))
    bs = [per[b].sum() / cnt[b].sum() for b in B]
    res[arm] = dict(logloss=float(L[arm].mean()), delta=float(d.mean()), ci=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))])
    print(f"{arm:22s} d={d.mean():+.4f} [{res[arm]['ci'][0]:+.4f},{res[arm]['ci'][1]:+.4f}]")
json.dump(dict(train_rows=int(tr.sum()), es_rows=int(es.sum()), val_rows=int(va.sum()), val_seeds=len(us), arms=res),
          open('/tmp/claude-0/a401/work/abl_a0.json', 'w'), indent=1)
