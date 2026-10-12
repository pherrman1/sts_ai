import sys, json, re, numpy as np
sys.path.insert(0,'/tmp/claude-0/a401/work'); sys.path.insert(0,'/home/user/sts_ai')
from fasttrees import Forest
from tools.analysis.vwin_tree_utils import split_counts
which=sys.argv[1]
rng=np.random.default_rng(4381)
if which=='B0':
    Z=np.load('a0.npz'); names=list(Z['names']); X=Z['X']; y=Z['y']; path='/home/user/sts_ai/models/v_win_trees.txt'
else:
    Z=np.load('a20.npz'); names=list(Z['names']); m=Z['in419val']; X=Z['X'][m]; y=Z['won'][m]; path='/home/user/sts_ai/models/candidates/v_win_a20_419.txt'
sub=rng.choice(len(y),min(40000,len(y)),replace=False); X=X[sub]; y=y[sub]
F=Forest(path); idx=[names.index(f) for f in F.feats]; X=X[:,idx]
def ll(p): p=np.clip(p,1e-6,1-1e-6); return -(y*np.log(p)+(1-y)*np.log(1-p))
base=ll(F.predict(X)).mean(); sc=split_counts(F.trees,F.feats)
res=[]
rj=[j for j,f in enumerate(F.feats) if re.fullmatch(r'r\d+',f) and sc[f]>0]
# relic count proxy
for j in sorted(rj,key=lambda j:-sc[F.feats[j]])[:40]:
    Xp=X.copy(); Xp[:,j]=X[rng.permutation(len(y)),j]
    res.append((F.feats[j],sc[F.feats[j]],float(ll(F.predict(Xp)).mean()-base),float((X[:,j]>0).mean())))
res.sort(key=lambda t:-t[2]); json.dump(res,open(f'relic_perm_{which}.json','w'))
for t in res[:15]: print(t)
