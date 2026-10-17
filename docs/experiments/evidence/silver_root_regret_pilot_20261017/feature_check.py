import json,glob,numpy as np,lightgbm as lgb,sys
import os
# usage: python3 -I feature_check.py DIR [DIR ...]; reuses the loading part of analyze_roots.py
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'analyze_roots.py')).read().split("print('\\n== mean regret")[0])
share=np.array([r['arms']['base2500'][0][2]/2500 for r in rows])
ref1=np.array([max(e[1] for e in r['ref'][0])/sum(e[1] for e in r['ref'][0]) for r in rows])
F2=np.column_stack([F[:,[0,1,2,3,4,5,6,7,8,10]],share])
cands=['c12_2500','c50_2500','endwide2500','othernarrow2500']
Y={a:(R[a][:,1:4].mean(1)-R['base2500'][:,1:4].mean(1)) for a in cands}
us=np.unique(seeds);rng=np.random.default_rng(0);fold={s:i%5 for i,s in enumerate(rng.permutation(us))};fo=np.array([fold[s] for s in seeds])
P=np.zeros((len(rows),5))
for k in range(5):
  tr,te=fo!=k,fo==k
  for j,a in enumerate(cands,1):
    m=lgb.LGBMRegressor(n_estimators=200,learning_rate=0.03,num_leaves=8,min_child_samples=80,verbose=-1).fit(F2[tr],Y[a][tr]);P[te,j]=m.predict(F2[te])
ch=P.argmin(1);real=np.stack([np.zeros(len(rows))]+[Y[a] for a in cands],1);gain=-real[np.arange(len(rows)),ch]
groups=[np.where(seeds==s)[0] for s in us]
b=[gain[np.concatenate([groups[i] for i in rng.integers(0,len(us),len(us))])].mean() for _ in range(2000)]
print('with base-search visit share: reduction %.4f CI %s choices %s'%(gain.mean(),np.round(np.percentile(b,[2.5,97.5]),4),np.bincount(ch,minlength=5)))
for a in cands:
  print(a,'corr(pred,actual) %.3f'%np.corrcoef(P[:,cands.index(a)+1],Y[a])[0,1])
# share bins
for lo,hi in ((0,.5),(.5,.8),(.8,1.01)):
  m=(share>=lo)&(share<hi); print('share %.1f-%.1f n %d'%(lo,hi,m.sum()),' '.join('%s %+.3f'%(a[:6],Y[a][m].mean()) for a in cands))
