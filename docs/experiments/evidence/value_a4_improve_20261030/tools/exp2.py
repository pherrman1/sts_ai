import sys, json, pickle, numpy as np, xgboost as xgb, core, feats
d = core.build(False); X = d['X']; y, n = d['y'], d['n']
dev = (d['seed'] % 4) != 3
recs = [e['entry']['record'] for e in core.entries(False)]
E = feats.eng(recs)
lce = core.logit(d['ce']); cp = core.logit((1 - d['ce'][:, 0]) * (1 - d['ce'][:, 1]))
XC = np.hstack([X, cp[:, None], lce]); XCE = np.hstack([XC, E])
mono_C = [0] * XC.shape[1]; mono_C[0] = 1; mono_C[X.shape[1] - 1] = 1; mono_C[X.shape[1]] = 1; mono_C[X.shape[1] + 1] = -1; mono_C[X.shape[1] + 2] = -1
def xg(Xm, o=None, w=None):
    w = n if w is None else w
    def fp(tr, te, iv):
        prm = {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'eta': 0.03, 'subsample': 0.8,
               'colsample_bytree': 0.5, 'lambda': 5, 'max_depth': 3, 'min_child_weight': 20, 'seed': 29, 'nthread': 4}
        prm.update(o or {})
        b = xgb.train(prm, xgb.DMatrix(Xm[tr], label=y[tr], weight=w[tr]), 5000,
                      evals=[(xgb.DMatrix(Xm[iv], label=y[iv], weight=w[iv]), 'v')], early_stopping_rounds=150, verbose_eval=False)
        return b.predict(xgb.DMatrix(Xm[te]), iteration_range=(0, b.best_iteration + 1))
    return fp
def lr(Xm, C):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    def fp(tr, te, iv):
        tr = np.r_[tr, iv]; sc = StandardScaler().fit(Xm[tr])
        A = sc.transform(Xm); Xg = np.r_[A[tr], A[tr]]; yg = np.r_[np.ones(len(tr)), np.zeros(len(tr))]; wg = np.r_[y[tr] * n[tr], (1 - y[tr]) * n[tr]]
        return LogisticRegression(C=C, max_iter=3000).fit(Xg, yg, sample_weight=wg).predict_proba(A[te])[:, 1]
    return fp
small = np.hstack([cp[:, None], lce, X[:, [0, 1, X.shape[1] - 1]], E])
V = {
 'GCe': xg(XC), 'GCe_eta01': xg(XC, {'eta': 0.01}), 'GCe_col02': xg(XC, {'colsample_bytree': 0.2}), 'GCe_col1': xg(XC, {'colsample_bytree': 1.0}),
 'GCe_lam20_mcw50': xg(XC, {'lambda': 20, 'min_child_weight': 50}), 'GCe_mcw5': xg(XC, {'min_child_weight': 5}),
 'GCe_mono': xg(XC, {'monotone_constraints': '(' + ','.join(map(str, mono_C)) + ')'}),
 'GCe_d1': xg(XC, {'max_depth': 1}),
 'GCeE': xg(XCE), 'GCeE_col02': xg(XCE, {'colsample_bytree': 0.2}),
 'LR_small_C1': lr(small, 1.0), 'LR_full_C001': lr(XCE, 0.01), 'LR_full_C0003': lr(XCE, 0.003),
 'ctm_only_LR': lr(np.hstack([cp[:, None], lce]), 1e3),
}
which = sys.argv[1:] or list(V)
P = {}
for k in which:
    P[k] = core.oof(V[k], d, dev); print(k, json.dumps(core.score(P[k], d, dev)), flush=True)
pickle.dump(P, open(core.D + 'P_exp2.pkl', 'wb'))
for k in P:
    if k != 'GCe' and 'GCe' in P: print(k, '- GCe', core.paired(core.per_seed_loss(P[k], d, dev), core.per_seed_loss(P['GCe'], d, dev), d, dev))
