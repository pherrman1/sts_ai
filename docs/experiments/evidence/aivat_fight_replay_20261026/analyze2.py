# CTM-baseline control variates: correction_k = V(post_k) - E_CTM[V(post_k)], with the SAME value function V
# (GBM P(Heart kill | post-fight state), trained only on the other campaigns). Heart: V(post) = outcome.
import json, sys, csv, numpy as np, xgboost as xgb
exec(open('analyze.py').read().split('P = dict')[0])  # reuse runs/feat/rows/is_heart
P = dict(n_estimators=400, max_depth=5, learning_rate=0.05, subsample=0.8, colsample_bytree=0.5, n_jobs=4)
DIRS = {'676': 'ctm-calibration-ab', '661': 'value-level-ab', '683': 'ooc-map-only-search'}
GRID = 3
out = {}
for key in DS:
    ctm = {}
    for arm in DS[key][1]:
        for r in csv.reader(open(f'rows/{DIRS[key]}/{arm}.csv')):
            if r[0] == 'source_seed': continue
            hmin, *h = r[-1][1:].split(' ')
            ctm[(arm, int(r[0]), int(r[1]))] = (float(r[16]), int(hmin), np.array(h, float))
    train = [r for k, rs in runs.items() if k != key for r in rs]
    Xp, Xq, y, ids = rows(train)
    alive = np.array([train[i]['fights'][k]['out'] == 1 and not is_heart(train[i]['fights'][k]) for i, k in ids])
    vm = xgb.XGBClassifier(objective='binary:logistic', **P).fit(Xp[alive], y[alive])
    rs = runs[key]; res = []
    for r in rs:
        fl = []
        X = []; meta = []
        for k, f in enumerate(r['fights']):
            pd_, hmin, hist = ctm[(r['arm'], r['seed'], k)]
            base = feat(f['post'])
            hs = np.arange(max(1, hmin), hmin + len(hist), GRID) if len(hist) else np.array([1])
            for h in hs:
                v = base.copy(); v[2] = h; v[4] = h / max(1, f['post']['mhp']); X.append(v)
            meta.append((k, hs, pd_, hmin, hist, base))
        X.append(np.zeros(NB, np.float32))
        X = np.array(X); pr = vm.predict_proba(X)[:, 1]; j = 0
        vreal = vm.predict_proba(np.array([m[5] for m in meta]))[:, 1]
        for (k, hs, pd_, hmin, hist, base), vr in zip(meta, vreal):
            f = r['fights'][k]; vh = pr[j:j + len(hs)]; j += len(hs)
            mass = hist.sum()
            vfull = np.interp(np.arange(hmin, hmin + len(hist)), hs, vh) if len(hist) else np.zeros(0)
            if is_heart(f):
                V = float(f['out'] == 1); E = 1 - pd_
            else:
                V = float(vr) if f['out'] == 1 else 0.0
                E = (1 - pd_) * float((hist * vfull).sum() / mass) if mass > 0 else 0.0
            # per-fight conditional variance of V under the CTM (for the replay-cost estimate)
            if is_heart(f): var = pd_ * (1 - pd_)
            else:
                m2 = (1 - pd_) * float((hist * vfull ** 2).sum() / mass) if mass > 0 else 0.0
                var = max(0.0, m2 - E ** 2)
            fl.append((f['pre']['act'], f['rc'], f['out'], f['pre']['hp'], V, E, var))
        res.append(dict(arm=r['arm'], seed=r['seed'], y=r['y'], f=fl))
    out[key] = res
    print(key, 'done', file=sys.stderr)
json.dump(out, open('scored2.json', 'w'))
