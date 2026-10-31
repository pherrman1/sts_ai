#!/usr/bin/env python3
"""V_H: Heart-kill value at Heart entry (after Shield & Spear), monotone GBM, + teacher prices (exploratory).
usage: fit_heart.py HEART.pkl OUT_DIR
Model selection by 4-fold CV grouped by seed on non-TEST seeds (seed % 4 != 3) only. TEST (seed % 4 == 3) was already
read for Act-4 outcomes in stage 2 / §720, so its numbers are NOT fresh and are reported as descriptive only.
Models: G (public record + hp fraction + potion count), GC (G + logit of the Act-4 CTM's Heart survival).
Monotone increasing in cur HP, max HP, hp fraction, potion count, each potion type (and the CTM logit)."""
import sys, os, json, copy, collections, math, pickle
import numpy as np
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, os.path.join(REPO, 'docs/experiments/evidence/value_clean_labels_20261029/tools'))
import fit_a4 as F  # noqa
s0 = F.s0
import xgboost as xgb
CTM = F.load_trees(os.path.join(REPO, 'models/candidates/ctm_act4_survival_trees.txt'))
NF = s0.N_FEAT + 2

def design(rs):
    X = np.zeros((len(rs), NF), np.float32); c = np.full(len(rs), np.nan)
    for i, r in enumerate(rs):
        cols, vals = s0.features(r['entry']); X[i, cols] = vals
        rec = r['entry']['record']; fo = rec['obs.fixed_observation']
        X[i, -2] = fo[0] / max(fo[1], 1); X[i, -1] = sum(p > 1 for p in rec['obs.potions'])
        if r['heart_ctm'] is not None: c[i] = 1 - F.tree_pred(CTM, F.ctm_feats(r['heart_ctm'], 1))
    return X, c

def logit(p): p = np.clip(p, 1e-4, 1 - 1e-4); return np.log(p / (1 - p))
def bce(p, y): p = np.clip(p, 1e-6, 1 - 1e-6); return -(y * np.log(p) + (1 - y) * np.log(1 - p))

def mono(ncol):
    o = s0.OFF; mc = [0] * ncol
    mc[o['fixed'][0]] = mc[o['fixed'][0] + 1] = 1
    for i in range(2, o['potion'][1]): mc[o['potion'][0] + i] = 1
    mc[s0.N_FEAT] = mc[s0.N_FEAT + 1] = 1
    if ncol > NF: mc[NF] = 1
    return '(' + ','.join(map(str, mc)) + ')'

def params(depth, mcw, ncol):
    return {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'eta': 0.03, 'subsample': 0.8,
            'colsample_bytree': 0.5, 'lambda': 5, 'max_depth': depth, 'min_child_weight': mcw, 'seed': 29, 'nthread': 4,
            'monotone_constraints': mono(ncol)}

def cv_select(X, y, seed, info, tag):
    folds = (seed // 4) % 4  # non-TEST seeds only; grouped by seed
    best = None
    for depth in (2, 3, 4):
        for mcw in (5, 20):
            losses, iters = [], []
            for f in range(4):
                tr, va = folds != f, folds == f
                b = xgb.train(params(depth, mcw, X.shape[1]), xgb.DMatrix(X[tr], label=y[tr]), 3000,
                              evals=[(xgb.DMatrix(X[va], label=y[va]), 'v')], early_stopping_rounds=100, verbose_eval=False)
                p = b.predict(xgb.DMatrix(X[va]), iteration_range=(0, b.best_iteration + 1))
                losses.append(bce(p, y[va]).sum()); iters.append(b.best_iteration + 1)
            v = float(sum(losses) / len(y))
            if best is None or v < best[0]: best = (v, depth, mcw, int(np.mean(iters)))
    info[tag] = {'cv_bce': best[0], 'depth': best[1], 'mcw': best[2], 'iters': best[3]}
    return xgb.train(params(best[1], best[2], X.shape[1]), xgb.DMatrix(X, label=y), best[3])

def main(pkl, out):
    os.makedirs(out, exist_ok=True)
    rs = [r for r in pickle.load(open(pkl, 'rb')) if r['seed'] is not None]
    X, c = design(rs); y = np.array([float(r['heartKilled']) for r in rs]); seed = np.array([int(r['seed']) for r in rs])
    te = seed % 4 == 3; trn = ~te
    fill = np.nanmean(c[trn]); lc = logit(np.where(np.isnan(c), fill, c))
    info = {'n': len(rs), 'n_nontest': int(trn.sum()), 'n_test': int(te.sum()), 'kill_rate': float(y.mean()),
            'by_campaign': dict(collections.Counter(r['campaign'] for r in rs)), 'ctm_missing': int(np.isnan(c).sum())}
    XC = np.hstack([X, lc[:, None]])
    G = cv_select(X[trn], y[trn], seed[trn], info, 'G'); GC = cv_select(XC[trn], y[trn], seed[trn], info, 'GC')
    G.save_model(os.path.join(out, 'G.ubj')); GC.save_model(os.path.join(out, 'GC.ubj'))
    # CTM recalibrated on non-TEST; HP-only logistic
    from sklearn.linear_model import LogisticRegression
    rec = LogisticRegression(C=1e6).fit(lc[trn, None], y[trn]); c_cal = rec.predict_proba(lc[:, None])[:, 1]
    hpc = [s0.OFF['fixed'][0], s0.OFF['fixed'][0] + 1, NF - 2, NF - 1]
    hp = LogisticRegression(C=1e6, max_iter=2000).fit(X[trn][:, hpc], y[trn]); h = hp.predict_proba(X[:, hpc])[:, 1]
    pg = G.predict(xgb.DMatrix(X)); pgc = GC.predict(xgb.DMatrix(XC))
    res = {}
    for nm, p in (('G', pg), ('GC', pgc), ('CTM_recal', c_cal), ('HP_potions_logistic', h), ('const', np.full(len(y), y[trn].mean()))):
        res[nm] = {'test_bce_nonfresh': float(bce(p[te], y[te]).mean()), 'auc': float(F.auc(p[te], y[te]))}
    for a in ('G', 'GC'):
        for b in ('CTM_recal', 'HP_potions_logistic'):
            d = bce({'G': pg, 'GC': pgc}[a][te], y[te]) - bce({'CTM_recal': c_cal, 'HP_potions_logistic': h}[b][te], y[te])
            res[f'{a}_minus_{b}'] = {'mean': float(d.mean()), 'ci': F.boot(seed[te], d)}
    # ---- teacher prices (all states) ----
    def pert(r, hp=0, mhp=0, drop=None, add=None):
        r = copy.deepcopy(r); rec = r['entry']['record']; fo = rec['obs.fixed_observation']
        fo[1] += mhp; fo[0] = max(1, min(fo[0] + hp, fo[1])); dropid = None
        if drop is not None: dropid = rec['obs.potions'][drop]; rec['obs.potions'][drop] = 1
        if add is not None: rec['obs.potions'][rec['obs.potions'].index(1)] = add
        q = r['heart_ctm']
        if q is not None:
            g = q['globals']; g['maxHp'] += mhp; g['curHp'] = max(1, min(g['curHp'] + hp, g['maxHp']))
            for x in q['potions']:
                if drop is not None and x['potionId'] == dropid and x['slot'] < g['potionCapacity']:
                    x['potionId'] = 1; g['potionCount'] -= 1; break
            if add is not None:
                for x in sorted(q['potions'], key=lambda x: x['slot']):
                    if x['potionId'] == 1 and x['slot'] < g['potionCapacity']:
                        x['potionId'] = add; g['potionCount'] += 1; break
        return r
    def score(lst):
        Xp, cp = design(lst); lp = logit(np.where(np.isnan(cp), fill, cp))
        return {'G': G.predict(xgb.DMatrix(Xp)), 'GC': GC.predict(xgb.DMatrix(np.hstack([Xp, lp[:, None]])))}
    v0 = score(rs); vh = {d: score([pert(r, hp=-d) for r in rs]) for d in (1, 3, 6, 12)}
    m5 = score([pert(r, mhp=5) for r in rs])
    tp = {}
    for k in ('G', 'GC'):
        sl = (v0[k] - vh[12][k]) / 12; slc = np.maximum(sl, 1e-4)
        tp[k] = {'slope_median_pp_per_hp': float(np.median(sl) * 100), 'slope_p10_p90': [float(x * 100) for x in np.percentile(sl, [10, 90])],
                 'sign_right': {d: float(np.mean(vh[d][k] < v0[k])) for d in (1, 3, 6, 12)},
                 'le': {d: float(np.mean(vh[d][k] <= v0[k])) for d in (1, 3, 6, 12)},
                 'maxhp5_hp_eq_per_point': float(np.median((m5[k] - v0[k]) / slc / 5)), 'maxhp5_pos': float(np.mean(m5[k] > v0[k]))}
        # concavity: slope in the upper vs lower HP half
        fr = X[:, -2]; tp[k]['slope_by_hp_frac'] = {q: float(np.median(sl[(fr >= a) & (fr < b)]) * 100) for q, (a, b) in
                                                    {'<0.4': (0, .4), '0.4-0.7': (.4, .7), '>=0.7': (.7, 1.01)}.items()}
    idx = [(i, s) for i, r in enumerate(rs) for s, v in enumerate(r['entry']['record']['obs.potions']) if v > 1]
    dr = score([pert(rs[i], drop=s) for i, s in idx]); pot = collections.defaultdict(lambda: collections.defaultdict(list))
    for j, (i, s) in enumerate(idx):
        pid = rs[i]['entry']['record']['obs.potions'][s]
        for k in ('G', 'GC'):
            sl = max((v0[k][i] - vh[12][k][i]) / 12, 1e-4)
            pot[pid][k].append(((v0[k][i] - dr[k][j]) * 100, (v0[k][i] - dr[k][j]) / sl))
    tp['potion_drop'] = {str(t): {k: {'n': len(v[k]), 'dV_pp': float(np.median([a for a, b in v[k]])), 'hp_eq': float(np.median([b for a, b in v[k]]))} for k in v}
                         for t, v in sorted(pot.items())}
    for k in ('G', 'GC'):
        a = [x for v in pot.values() for x in v[k] ]
        nf = [x for t, v in pot.items() if t != 21 for x in v[k]]
        tp[k]['potion_all'] = {'n': len(a), 'hp_eq': float(np.median([b for _, b in a])), 'dV_pp': float(np.median([d for d, _ in a]))}
        tp[k]['potion_nonfairy'] = {'n': len(nf), 'hp_eq': float(np.median([b for _, b in nf])), 'dV_pp': float(np.median([d for d, _ in nf])),
                                    'pos_share': float(np.mean([d > 0 for d, _ in nf]))}
    json.dump({'info': info, 'test_nonfresh': res, 'teacher': tp}, open(os.path.join(out, 'heart.json'), 'w'), indent=1)
    print(json.dumps({'info': info, 'test_nonfresh': res, 'teacher': {k: v for k, v in tp.items() if k != 'potion_drop'}}, indent=1))

if __name__ == '__main__':
    main(*sys.argv[1:3])
