import sys, json, csv, os, numpy as np, warnings
sys.path.insert(0, sys.argv[3]); import fit_value as V
from sklearn.linear_model import LogisticRegression
rows = sorted(csv.DictReader(open(sys.argv[1])), key=lambda r: (int(r['base']), int(r['variant'])))
st = [[json.loads(l) for l in open(os.path.join(sys.argv[2], f'v{k}.jsonl'))] for k in range(16)]
S = [st[int(r['variant'])][int(r['base'])] for r in rows]; L = np.array([V.leaf(s) for s in S])[:, None]
y = np.array([float(r['won']) for r in rows]); g = np.array([int(r['source_seed']) for r in rows]); nb = len(y)//16
P = np.zeros(len(y)); Pd = np.zeros(len(y))
for f in range(5):
    tr, te = g % 5 != f, g % 5 == f
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always'); lr = LogisticRegression(C=1e6).fit(L[tr], y[tr]); print('fold', f, 'default warn', [str(x.message)[:40] for x in w])
    Pd[te] = lr.predict_proba(L[te])[:, 1]
    lr = LogisticRegression(C=1e6, max_iter=10000).fit(L[tr], y[tr]); P[te] = lr.predict_proba(L[te])[:, 1]; print(f, lr.coef_[0][0], lr.intercept_[0])
res = json.load(open(sys.argv[4])); 
Y = y.reshape(nb, 16); D = (Y[:, 2:] - Y[:, :1]).reshape(-1)
def dh(p): p = p.reshape(nb, 16); return (p[:, 2:] - p[:, :1]).reshape(-1)
print('mse L default', ((D - dh(Pd))**2).mean(), 'converged', ((D - dh(P))**2).mean())
# A predictions not saved; report L-only change
