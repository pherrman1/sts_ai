import sys, json, numpy as np, xgboost as xgb, core
d = core.build(False); X = d['X']; y, n = d['y'], d['n']
dev = (d['seed'] % 4) != 3
lce = core.logit(d['ce']); lss = core.logit(np.where(np.isnan(d['c_ss']), np.nanmean(d['c_ss']), d['c_ss']))
ce_prod = core.logit((1 - d['ce'][:, 0]) * (1 - d['ce'][:, 1]))
def xg(Xm, prm_over=None, rounds=3000, w=None):
    w = n if w is None else w
    def fp(tr, te, iv):
        prm = {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'eta': 0.03, 'subsample': 0.8,
               'colsample_bytree': 0.5, 'lambda': 5, 'max_depth': 3, 'min_child_weight': 20, 'seed': 29, 'nthread': 4}
        prm.update(prm_over or {})
        b = xgb.train(prm, xgb.DMatrix(Xm[tr], label=y[tr], weight=w[tr]), rounds,
                      evals=[(xgb.DMatrix(Xm[iv], label=y[iv], weight=w[iv]), 'v')], early_stopping_rounds=100, verbose_eval=False)
        return b.predict(xgb.DMatrix(Xm[te]), iteration_range=(0, b.best_iteration + 1))
    return fp
V = {
 'G_d3': (X, {}), 'G_d2': (X, {'max_depth': 2}), 'G_d4': (X, {'max_depth': 4}),
 'GCss_d2(leak)': (np.hstack([X, lss[:, None]]), {'max_depth': 2}),
 'GCe_d3': (np.hstack([X, ce_prod[:, None], lce]), {}),
 'GCe_d2': (np.hstack([X, ce_prod[:, None], lce]), {'max_depth': 2}),
}
which = sys.argv[1:] or list(V)
P = {}; out = {}
for k in which:
    Xm, o = V[k]; P[k] = core.oof(xg(Xm, o), d, dev); out[k] = core.score(P[k], d, dev); print(k, json.dumps(out[k]), flush=True)
np.save(core.D + 'P_exp1.npy', P, allow_pickle=True)
base = 'G_d3'
for k in P:
    if k != base: print(k, '-', base, core.paired(core.per_seed_loss(P[k], d, dev), core.per_seed_loss(P[base], d, dev), d, dev))
