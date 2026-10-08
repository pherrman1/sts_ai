# Fit diagnostics for ledger §400 (run from the repo root):
#   python3 docs/experiments/evidence/silver_prior_v2_offline_20261008/compare_v1_v2.py FEATURES_DIR V1_PRIOR.txt prior-v2.txt
import sys, numpy as np, lightgbm as lgb
sys.path.insert(0,'tools')
from silver_prior_v2 import *
X, metas, ns = load(sys.argv[1])
F, acts, owner, roots = v2_rows(X, metas, ns)
share = visit_shares(metas, roots); y=np.array([share[a] for a in acts])
va = select(metas, acts, owner, roots, (VAL,)); st,_=groups_of(owner[va]); sizes=np.diff(np.r_[st,len(va)])
def xent(p): return float(-(y[va]*np.log(np.maximum(p,1e-12))).sum()/len(st))
v1=lgb.Booster(model_file=sys.argv[2]).predict(F[va][:, :X.shape[1]])
p1=v1/np.repeat(np.add.reduceat(v1,st),sizes)
v2=lgb.Booster(model_file=sys.argv[3]).predict(F[va],raw_score=True)
p2=group_softmax(v2,st)
pu=1/np.repeat(sizes,sizes)
top=lambda p: float(np.mean([ (np.argmax(p[s:s+n])==np.argmax(y[va][s:s+n])) for s,n in zip(st,sizes)]))
for n,p in [('uniform',pu),('v1',p1),('v2',p2)]: print(n, round(xent(p),4), 'top1', round(top(p),3))
print('floor', round(float(-(y[va]*np.log(np.maximum(y[va],1e-12))).sum()/len(st)),4))
# noise ceiling: second independent 10k search on roots that have it
idx=[]; 
for s,n in zip(st,sizes):
    rows=[acts[va[s+i]] for i in range(n)]
    if all(metas[a].get('visits2') is not None for a in rows): idx.append((s,n,rows))
vy=y[va]; agree=[];xe=[];a1=[];a2=[];x1=[];x2=[]
for s,n,rows in idx:
    v2s=np.array([metas[a]['visits2'] for a in rows],float); q=v2s/v2s.sum()
    agree.append(np.argmax(q)==np.argmax(vy[s:s+n]))
    xe.append(-(vy[s:s+n]*np.log(np.maximum(0.5*q+0.5/n,1e-12))).sum())
    a1.append(np.argmax(p1[s:s+n])==np.argmax(vy[s:s+n])); a2.append(np.argmax(p2[s:s+n])==np.argmax(vy[s:s+n]))
print('roots with second search', len(idx), 'second-search top1', np.mean(agree), 'v1', np.mean(a1), 'v2', np.mean(a2))
ag=np.array(agree); A1=np.array(a1); A2=np.array(a2)
print('agree roots', ag.mean(), 'v1 on agree', A1[ag].mean(), 'v1 on disagree', A1[~ag].mean(), 'v2 on agree', A2[ag].mean(), 'v2 on disagree', A2[~ag].mean())
# v2 vs averaged label (mean of both searches)
a2avg=[]; 
for (s,n,rows) in idx:
    v=np.array([metas[a]['visits2'] for a in rows],float); q=v/v.sum(); avg=0.5*(q+vy[s:s+n])
    a2avg.append(np.argmax(p2[s:s+n])==np.argmax(avg))
print('v2 vs averaged-2-search top', np.mean(a2avg))
