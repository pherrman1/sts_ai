import sys, json, pickle, numpy as np, core, feats, inspect
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
d = core.build(False); X = d['X']; y, n = d['y'], d['n']
E = feats.eng([e['entry']['record'] for e in core.entries(False)])
lce = core.logit(d['ce']); cp = core.logit((1 - d['ce'][:, 0]) * (1 - d['ce'][:, 1]))
XCE = np.hstack([X, cp[:, None], lce, E]); keep = XCE[(d['seed'] % 4) != 3].std(0) > 0; XCE = XCE[:, keep]
dev = (d['seed'] % 4) != 3
print('sample_weight' in inspect.signature(MLPClassifier.fit).parameters)
def mlp(h, alpha):
    def fp(tr, te, iv):
        tr = np.r_[tr, iv]; sc = StandardScaler().fit(XCE[tr]); A = np.clip(sc.transform(XCE), -5, 5)
        Xg = np.r_[A[tr], A[tr]]; yg = np.r_[np.ones(len(tr)), np.zeros(len(tr))]; wg = np.r_[y[tr] * n[tr], (1 - y[tr]) * n[tr]]
        ps = []
        for s in range(3):
            m = MLPClassifier(h, alpha=alpha, max_iter=300, early_stopping=False, learning_rate_init=1e-3, batch_size=128, random_state=s)
            m.fit(Xg[wg > 0], yg[wg > 0], sample_weight=wg[wg > 0]); ps.append(m.predict_proba(A[te])[:, 1])
        return np.mean(ps, 0)
    return fp
P = {}
for k, fp in {'MLP64_a10': mlp((64,), 10.0), 'MLP64_a30': mlp((64,), 30.0), 'MLP128x32_a10': mlp((128, 32), 10.0)}.items():
    P[k] = core.oof(fp, d, dev, reps=(0,)); print(k, json.dumps(core.score(P[k], d, dev)), flush=True)
pickle.dump(P, open(core.D + 'P_exp4.pkl', 'wb'))
