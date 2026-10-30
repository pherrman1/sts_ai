"""Fit the deployable V_A4 (ENS_rc of exp8 = exp6 ENS_all + relic counters + card state) on every entry with seed % 4 != 3 (stage 5's TEST seeds stay out).
GBM rounds: early stop on VALIDATION seeds (seed % 4 == 2) training on TRAIN, then refit on TRAIN+VALIDATION with that
round count x 4/3 (more rows). LR: C = 0.003 on TRAIN+VALIDATION. Selftest: va4_model.predict on the raw entry records
equals the training-matrix prediction. usage: VA4_DATA=DIR fit_va4.py"""
import os, json, hashlib, numpy as np, xgboost as xgb, core, feats, va4_model
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
d = core.build(2); es = core.entries(2)
Z = va4_model.assemble(d['X'], d['ce'], [e['entry']['record'] for e in es], d['src'] == 'run1', d['strong'])
y, n, seed = d['y'], d['n'], d['seed']
tr = (seed % 4 != 3) & (seed % 4 != 2); va = seed % 4 == 2; trva = seed % 4 != 3
prm = {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'eta': 0.03, 'subsample': 0.8,
       'colsample_bytree': 0.2, 'lambda': 5, 'max_depth': 3, 'min_child_weight': 20, 'seed': 29, 'nthread': 4}
b = xgb.train(prm, xgb.DMatrix(Z[tr], label=y[tr], weight=n[tr]), 5000, evals=[(xgb.DMatrix(Z[va], label=y[va], weight=n[va]), 'v')],
              early_stopping_rounds=150, verbose_eval=False)
rounds = int(round((b.best_iteration + 1) * 4 / 3))
g = xgb.train(prm, xgb.DMatrix(Z[trva], label=y[trva], weight=n[trva]), rounds)
sc = StandardScaler().fit(Z[trva]); A = sc.transform(Z[trva]); m = trva.sum()
lr = LogisticRegression(C=0.003, max_iter=3000).fit(np.r_[A, A], np.r_[np.ones(m), np.zeros(m)], sample_weight=np.r_[y[trva] * n[trva], (1 - y[trva]) * n[trva]])
os.makedirs(va4_model.MODEL_DIR, exist_ok=True)
g.save_model(os.path.join(va4_model.MODEL_DIR, 'va4_gbm.ubj'))
sd = np.where(sc.scale_ > 0, sc.scale_, 1.0)
json.dump({'mean': sc.mean_.tolist(), 'scale': sd.tolist(), 'coef': lr.coef_[0].tolist(), 'intercept': float(lr.intercept_[0]), 'C': 0.003},
          open(os.path.join(va4_model.MODEL_DIR, 'va4_lr.json'), 'w'))
M = va4_model.load()
p_mat = M.predict_matrix(Z)
idx = np.where(d['src'] == 'run1')[0][:50]
p_raw = M.predict([es[i]['entry'] for i in idx])
assert np.allclose(p_raw, p_mat[idx], atol=1e-6), np.abs(p_raw - p_mat[idx]).max()
info = {'rows_train': int(trva.sum()), 'games_train': float(n[trva].sum()), 'gbm_best_iter_trainonly': int(b.best_iteration), 'gbm_rounds': rounds,
        'selftest_max_abs_diff': float(np.abs(p_raw - p_mat[idx]).max()), 'mean_pred_trainrows': float(p_mat[trva].mean()),
        'sha256': {f: hashlib.sha256(open(os.path.join(va4_model.MODEL_DIR, f), 'rb').read()).hexdigest() for f in ('va4_gbm.ubj', 'va4_lr.json')}}
json.dump(info, open(os.path.join(va4_model.MODEL_DIR, 'fit_info.json'), 'w'), indent=1); print(json.dumps(info, indent=1))
