import sys, json, pickle, numpy as np, xgboost as xgb, core, feats
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
ex = int(sys.argv[1]) if len(sys.argv) > 1 else 0
d = core.build(bool(ex)); X = d['X']; y, n = d['y'], d['n']
recs = [e['entry']['record'] for e in core.entries(bool(ex))]
E = feats.eng(recs); lce = core.logit(d['ce']); cp = core.logit((1 - d['ce'][:, 0]) * (1 - d['ce'][:, 1]))
src = d['src']; strong = d['strong'].astype(np.float32)
srcf = np.c_[(src == 'run1').astype(np.float32), strong]
XCE = np.hstack([X, cp[:, None], lce, E])
dev_core = ((d['seed'] % 4) != 3) & (src != 'extra')   # evaluation rows: same as exp2
def xg(Xm, o=None, w=None, trainmask=None):
    w = n if w is None else w
    def fp(tr, te, iv):
        if trainmask is not None: tr = tr[trainmask[tr]]
        prm = {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'eta': 0.03, 'subsample': 0.8,
               'colsample_bytree': 0.2, 'lambda': 5, 'max_depth': 3, 'min_child_weight': 20, 'seed': 29, 'nthread': 4}
        prm.update(o or {})
        b = xgb.train(prm, xgb.DMatrix(Xm[tr], label=y[tr], weight=w[tr]), 5000,
                      evals=[(xgb.DMatrix(Xm[iv], label=y[iv], weight=n[iv]), 'v')], early_stopping_rounds=150, verbose_eval=False)
        return b.predict(xgb.DMatrix(Xm[te]), iteration_range=(0, b.best_iteration + 1))
    return fp
def lr(Xm, C, w=None, trainmask=None):
    w = n if w is None else w
    def fp(tr, te, iv):
        tr = np.r_[tr, iv]
        if trainmask is not None: tr = tr[trainmask[tr]]
        sc = StandardScaler().fit(Xm[tr]); A = sc.transform(Xm)
        Xg = np.r_[A[tr], A[tr]]; yg = np.r_[np.ones(len(tr)), np.zeros(len(tr))]; wg = np.r_[y[tr] * w[tr], (1 - y[tr]) * w[tr]]
        return LogisticRegression(C=C, max_iter=3000).fit(Xg, yg, sample_weight=wg).predict_proba(A[te])[:, 1]
    return fp
# evaluation always only on dev_core rows; training pool = dev rows (incl. extra if ex)
pool = (d['seed'] % 4) != 3
def run(fp):
    P = core.oof(fp, d, pool); return P
V = {}
if not ex:
    V['GBM'] = xg(XCE); V['LR'] = lr(XCE, 0.003)
    V['GBM_srcf'] = xg(np.hstack([XCE, srcf]))
    V['GBM_w_s2half'] = xg(XCE, w=np.where(src == 'run1', n, 0.5))
    V['GBM_run1only'] = xg(XCE, trainmask=(src == 'run1'))
    V['LR_C001'] = lr(XCE, 0.001); V['LR_C001x'] = lr(XCE, 0.0003)
    # learning curve: drop fraction of training seeds
    for frac in (0.25, 0.5, 0.75):
        rng = np.random.default_rng(5); us = np.unique(d['seed']); keep = set(rng.choice(us, int(frac * len(us)), replace=False))
        km = np.array([s in keep for s in d['seed']])
        V[f'GBM_lc{frac}'] = xg(XCE, trainmask=km); V[f'LR_lc{frac}'] = lr(XCE, 0.003, trainmask=km)
else:
    XS = np.hstack([XCE, srcf])
    V['GBM_extra_srcf'] = xg(XS); V['LR_extra_srcf'] = lr(XS, 0.003)
    V['GBM_noextra_srcf'] = xg(XS, trainmask=(src != 'extra')); V['LR_noextra_srcf'] = lr(XS, 0.003, trainmask=(src != 'extra'))
P = {}
for k, fp in V.items():
    P[k] = run(fp); print(k, json.dumps(core.score(P[k], d, dev_core)), flush=True)
if not ex:
    P['ENS'] = (P['GBM'] + P['LR']) / 2; print('ENS', json.dumps(core.score(P['ENS'], d, dev_core)))
pickle.dump((P, dev_core), open(core.D + f'P_exp3_{ex}.pkl', 'wb'))
ref = 'GBM' if not ex else 'GBM_noextra_srcf'
for k in P:
    if k != ref: print(k, '-', ref, core.paired(core.per_seed_loss(P[k], d, dev_core), core.per_seed_loss(P[ref], d, dev_core), d, dev_core))
