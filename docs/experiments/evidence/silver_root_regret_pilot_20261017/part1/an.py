import pandas as pd,numpy as np,lightgbm as lgb
df=pd.read_csv('/tmp/claude-0/x518/an/rep.csv')
ARMS=["endwide2500","othernarrow2500","spire2500"]
rng=np.random.default_rng(0)
seeds=df.seed.unique()
def boot(f,n=2000):
  g={s:i for i,s in enumerate(seeds)}; idx=df.seed.map(g).values
  groups=[np.where(idx==i)[0] for i in range(len(seeds))]
  vals=[]
  for _ in range(n):
    pick=np.concatenate([groups[i] for i in rng.integers(0,len(seeds),len(seeds))]); vals.append(f(pick))
  return np.percentile(vals,[2.5,97.5])
for a in ARMS:
  df[f'd_{a}_0']=df[f'{a}_k0']-df['base2500_k0']; df[f'd_{a}_1']=df[f'{a}_k1']-df['base2500_k1']; df[f'd_{a}']=(df[f'd_{a}_0']+df[f'd_{a}_1'])/2
print("n",len(df),"seeds",len(seeds))
print("== A. replicate consistency: cov(d_k0,d_k1)=Var(true per-fight effect)")
for a in ARMS:
  d0,d1=df[f'd_{a}_0'].values,df[f'd_{a}_1'].values
  f=lambda p:np.cov(d0[p],d1[p])[0,1]
  c=f(np.arange(len(df)));ci=boot(f,1000)
  print(a,"mean %.2f sd(d) %.1f cov %.1f CI [%.1f,%.1f] corr %.3f  => sd(tau) ~ %s"%(df[f'd_{a}'].mean(),d0.std(),c,ci[0],ci[1],np.corrcoef(d0,d1)[0,1], ("%.1f"%np.sqrt(c)) if c>0 else "0"))
# also replicate noise of base itself
print("base k0 vs k1 sd of diff %.1f"%(df.base2500_k0-df.base2500_k1).std())
print("== B. cross-fit oracle (choose arm incl base per fight on k0, score on k1, and swap)")
def xfit(p):
  g=0
  for a_,b_ in ((0,1),(1,0)):
    D=np.stack([np.zeros(len(p))]+[df[f'd_{a}_{a_}'].values[p] for a in ARMS],1)
    E=np.stack([np.zeros(len(p))]+[df[f'd_{a}_{b_}'].values[p] for a in ARMS],1)
    ch=D.argmax(1); g+=E[np.arange(len(p)),ch].mean()
  return g/2
p=np.arange(len(df));print("gain vs base %.2f CI %s"%(xfit(p),boot(xfit,1000)))
# by act
for act in (1,2,3,4):
  m=np.where(df.act==act)[0]
  if len(m): print(" act",act,"n",len(m)," ".join("%s %.2f"%(a[:6],df[f'd_{a}'].values[m].mean()) for a in ARMS)," xfit %.2f"%xfit(m))
print("== C. feature models, 5-fold grouped by seed, out-of-fold policy")
df['roomc']=df.room.astype('category').cat.codes; df['encc']=df.enc.astype('category').cat.codes
df['hpfrac']=df.preHp/df.preMaxHp
F=['act','floor','roomc','encc','preHp','preMaxHp','hpfrac','pots','ctmPDeath','ctmExpHp','ctrlDec','ctrlCpu','ctrlHp','ctrlWon']
fold=pd.Series(seeds).sample(frac=1,random_state=1).reset_index(drop=True)
fmap={s:i%5 for i,s in enumerate(fold)}; df['fold']=df.seed.map(fmap)
pred={a:np.zeros(len(df)) for a in ARMS}; predcell={a:np.zeros(len(df)) for a in ARMS}
df['cell']=df.act.astype(str)+df.room
for k in range(5):
  tr=df.fold!=k; te=df.fold==k
  for a in ARMS:
    m=lgb.LGBMRegressor(n_estimators=150,learning_rate=0.03,num_leaves=8,min_child_samples=80,subsample=0.8,subsample_freq=1,verbose=-1)
    m.fit(df.loc[tr,F],df.loc[tr,f'd_{a}']); pred[a][te.values]=m.predict(df.loc[te,F])
    cm=df[tr].groupby('cell')[f'd_{a}'].mean(); predcell[a][te.values]=df.loc[te,'cell'].map(cm).fillna(0).values
for name,P in (("gbm",pred),("act x room cell",predcell)):
  Pm=np.stack([np.zeros(len(df))]+[P[a] for a in ARMS],1); ch=Pm.argmax(1)
  E=np.stack([np.zeros(len(df))]+[df[f'd_{a}'].values for a in ARMS],1)
  f=lambda p:E[p,ch[p]].mean()
  print(name,"gain vs base %.2f CI %s"%(f(np.arange(len(df))),boot(f,2000)),"choice counts",np.bincount(ch,minlength=4))
  for a in ARMS: print("  ",a,"corr(pred,actual) %.3f"%np.corrcoef(P[a],df[f'd_{a}'])[0,1])
best=max(ARMS,key=lambda a:df[f'd_{a}'].mean()); print("best global arm",best,"%.2f"%df[f'd_{best}'].mean())
