import numpy as np, xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
def xg(Xm, y, n, o=None, w=None, trainmask=None, rounds=5000):
    w = n if w is None else w
    def fp(tr, te, iv):
        if trainmask is not None: tr = tr[trainmask[tr]]; iv = iv[trainmask[iv]]
        prm = {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'eta': 0.03, 'subsample': 0.8,
               'colsample_bytree': 0.2, 'lambda': 5, 'max_depth': 3, 'min_child_weight': 20, 'seed': 29, 'nthread': 4}
        prm.update(o or {})
        b = xgb.train(prm, xgb.DMatrix(Xm[tr], label=y[tr], weight=w[tr]), rounds,
                      evals=[(xgb.DMatrix(Xm[iv], label=y[iv], weight=n[iv]), 'v')], early_stopping_rounds=150, verbose_eval=False)
        return b.predict(xgb.DMatrix(Xm[te]), iteration_range=(0, b.best_iteration + 1))
    return fp
def lr(Xm, y, n, C, w=None, trainmask=None):
    w = n if w is None else w
    def fp(tr, te, iv):
        tr = np.r_[tr, iv]
        if trainmask is not None: tr = tr[trainmask[tr]]
        sc = StandardScaler().fit(Xm[tr]); A = sc.transform(Xm)
        Xg = np.r_[A[tr], A[tr]]; yg = np.r_[np.ones(len(tr)), np.zeros(len(tr))]; wg = np.r_[y[tr] * w[tr], (1 - y[tr]) * w[tr]]
        return LogisticRegression(C=C, max_iter=3000).fit(Xg, yg, sample_weight=wg).predict_proba(A[te])[:, 1]
    return fp
