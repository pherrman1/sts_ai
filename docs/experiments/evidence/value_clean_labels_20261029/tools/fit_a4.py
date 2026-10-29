#!/usr/bin/env python3
"""Stage 2 V_A4 fit + gate (plan: ../STAGE2-PLAN.md).
usage: fit_a4.py A4.pkl OUT_DIR"""
import sys, json, math, pickle, os
import numpy as np
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), *['..'] * 5))
sys.path.insert(0, os.path.join(REPO, 'docs/experiments/evidence/outcome_divergence_pairs_20261025'))
import s0  # noqa: E402
CAMPS = {'key-rules-ab', 'gumbel-qcap-ab', 'expert-anchored-ab', 'card-rule-ab'}
SS, HEART = 56, 57

def load_trees(path):
    L = open(path).read().split('\n'); i = 0
    nfeat = int(L[i].split()[1]); i += 1
    feats = [L[i + k].split()[1] for k in range(nfeat)]; i += nfeat
    assert L[i] == 'logistic 1'; i += 1
    base = float(L[i].split()[1]); i += 1
    nt = int(L[i].split()[1]); i += 1
    trees = []
    for t in range(nt):
        _, ti, nn = L[i].split(); i += 1
        nodes = []
        for k in range(int(nn)):
            p = L[i].split(); i += 1
            nodes.append(('L', float(p[1])) if p[0] == 'L' else ('S', int(p[1]), float(p[2]), int(p[3]), int(p[4])))
        trees.append(nodes)
    return feats, math.log(base / (1 - base)), trees

CARDS, RELICS, POTS = 400, 200, 50
SCAL = ['heart', 'cur_hp', 'max_hp', 'hp_frac', 'gold', 'potion_capacity', 'potion_count', 'deck_size', 'upgraded']
NAMES = SCAL + [f'card_{i}' for i in range(CARDS)] + [f'relic_{i}' for i in range(RELICS)] + [f'potion_{i}' for i in range(POTS)]
def ctm_feats(p, heart):
    g = p['globals']; x = {}
    x.update(heart=float(heart), cur_hp=g['curHp'], max_hp=g['maxHp'], hp_frac=np.float32(g['curHp']) / np.float32(g['maxHp']),
             gold=g['gold'], potion_capacity=g['potionCapacity'], potion_count=g['potionCount'], deck_size=len(p['cards']),
             upgraded=sum(c['upgraded'] for c in p['cards']))
    for c in p['cards']: x[f'card_{c["cardId"]}'] = x.get(f'card_{c["cardId"]}', 0) + 1
    for r in p['relics']: x[f'relic_{r["relicId"]}'] = 1
    for q in p['potions']:
        if q['slot'] < g['potionCapacity'] and q['potionId'] > 1: x[f'potion_{q["potionId"]}'] = x.get(f'potion_{q["potionId"]}', 0) + 1
    return x
def tree_pred(model, x):
    feats, m, trees = model
    v = [float(np.float32(x.get(f, 0.0))) for f in feats]
    for nodes in trees:
        k = 0
        while nodes[k][0] == 'S':
            _, fi, th, y, n = nodes[k]; k = y if v[fi] < np.float32(th) else n
        m += nodes[k][1]
    return 1 / (1 + math.exp(-m))

def bce(p, y): p = np.clip(p, 1e-6, 1 - 1e-6); return -(y * np.log(p) + (1 - y) * np.log(1 - p))
def auc(p, y):
    o = np.argsort(p); r = np.empty(len(p)); r[o] = np.arange(1, len(p) + 1)
    n1 = y.sum(); n0 = len(y) - n1; return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
def boot(seeds, v, n=4000, rng=np.random.default_rng(29)):
    us = np.unique(seeds); idx = {s: np.where(seeds == s)[0] for s in us}; out = []
    for _ in range(n):
        pick = rng.choice(us, len(us)); ii = np.concatenate([idx[s] for s in pick]); out.append(v[ii].mean())
    return [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))]

def main(pkl, out):
    import xgboost as xgb
    from sklearn.linear_model import LogisticRegression
    os.makedirs(out, exist_ok=True)
    recs = [r for r in pickle.load(open(pkl, 'rb')) if r['campaign'] in CAMPS and r['strong'] and r['reachedA4']]
    model = load_trees(os.path.join(REPO, 'models/candidates/ctm_act4_survival_trees.txt'))
    X = np.zeros((len(recs), s0.N_FEAT + 1), np.float32); y = np.zeros(len(recs)); seed = np.zeros(len(recs), int); c = np.full(len(recs), np.nan)
    for i, r in enumerate(recs):
        cols, vals = s0.features(r['entry']); X[i, cols] = vals
        fo = r['entry']['record']['obs.fixed_observation']; X[i, -1] = fo[0] / max(fo[1], 1)
        y[i] = r['heartKilled']; seed[i] = r['seed']
        ss = [q for q in r.get('ctm_a4', []) if q['roomClass'] == 'ELITE' and q['predictorInput']['globals']['encounter'] == SS]
        if ss:
            p = ss[0]['predictorInput']
            c[i] = (1 - tree_pred(model, ctm_feats(p, 0))) * (1 - tree_pred(model, ctm_feats(p, 1)))
    split = np.array([s0.split_of(int(s)) for s in seed])
    tr, va, te = split == 'train', split == 'validation', split == 'test'
    has = ~np.isnan(c)
    info = {'n': int(len(y)), 'kill_rate': float(y.mean()), 'by_split': {s: int((split == s).sum()) for s in ('train', 'validation', 'test')},
            'ctm_missing': int((~has).sum()), 'campaigns': {k: sum(r['campaign'] == k for r in recs) for k in CAMPS}}
    # missing S&S row (e.g. died before S&S? no: S&S is first fight) -> fill CTM with train mean
    cf = np.where(has, c, np.nanmean(c[tr]))
    lc = np.log(np.clip(cf, 1e-4, 1 - 1e-4) / (1 - np.clip(cf, 1e-4, 1 - 1e-4)))
    rec = LogisticRegression(C=1e6).fit(lc[tr, None], y[tr]); c_cal = rec.predict_proba(lc[:, None])[:, 1]
    hpcols = [0, 1, X.shape[1] - 1]
    hp = LogisticRegression(C=1e6, max_iter=1000).fit(X[tr][:, hpcols], y[tr]); h = hp.predict_proba(X[:, hpcols])[:, 1]
    def gbm(Xm, tag):
        best = None
        for depth in (2, 3, 4):
            for mcw in (5, 20):
                prm = {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'eta': 0.03, 'subsample': 0.8,
                       'colsample_bytree': 0.5, 'lambda': 5, 'max_depth': depth, 'min_child_weight': mcw, 'seed': 29, 'nthread': 4}
                b = xgb.train(prm, xgb.DMatrix(Xm[tr], label=y[tr]), 3000, evals=[(xgb.DMatrix(Xm[va], label=y[va]), 'v')],
                              early_stopping_rounds=100, verbose_eval=False)
                p = b.predict(xgb.DMatrix(Xm), iteration_range=(0, b.best_iteration + 1))
                v = float(bce(p[va], y[va]).mean())
                if best is None or v < best[0]: best = (v, depth, mcw, int(b.best_iteration), p, b)
        info[tag] = {'val_bce': best[0], 'depth': best[1], 'mcw': best[2], 'iters': best[3]}
        best[5].save_model(os.path.join(out, f'{tag}.ubj'))
        return best[4]
    g = gbm(X, 'G'); gc = gbm(np.hstack([X, lc[:, None]]), 'GC')
    pick = 'G' if info['G']['val_bce'] <= info['GC']['val_bce'] else 'GC'
    info['picked_on_validation'] = pick
    gp = g if pick == 'G' else gc
    # ---- TEST (opened once) ----
    res = {}
    for name, p in (('G', g), ('GC', gc), ('picked', gp), ('HP', h), ('CTM_raw', cf), ('CTM_recal', c_cal), ('const', np.full(len(y), y[tr].mean()))):
        res[name] = {'bce': float(bce(p[te], y[te]).mean()), 'auc': float(auc(p[te], y[te])), 'mean_p': float(p[te].mean())}
    d = bce(gp[te], y[te]) - bce(c_cal[te], y[te])
    res['picked_minus_CTM_recal'] = {'mean': float(d.mean()), 'ci': boot(seed[te], d)}
    d2 = bce(gp[te], y[te]) - bce(h[te], y[te])
    res['picked_minus_HP'] = {'mean': float(d2.mean()), 'ci': boot(seed[te], d2)}
    q = np.quantile(gp[te], np.linspace(0, 1, 11)); dec = []
    for k in range(10):
        m = (gp[te] >= q[k]) & (gp[te] <= q[k + 1] if k == 9 else gp[te] < q[k + 1])
        n = int(m.sum()); obs = float(y[te][m].mean()); pr = float(gp[te][m].mean()); se = math.sqrt(max(obs * (1 - obs), 1e-9) / max(n, 1))
        dec.append({'n': n, 'pred': pr, 'obs': obs, 'ok': abs(pr - obs) <= 0.03 or abs(pr - obs) <= 1.96 * se})
    res['deciles'] = dec
    res['gate'] = {'bce_better_than_ctm': res['picked_minus_CTM_recal']['ci'][1] < 0, 'calibration_ok': all(x['ok'] for x in dec)}
    res['gate']['PASS'] = res['gate']['bce_better_than_ctm'] and res['gate']['calibration_ok']
    json.dump({'info': info, 'test': res}, open(os.path.join(out, 'result.json'), 'w'), indent=1)
    print(json.dumps({'info': info, 'test': res}, indent=1))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
