import glob, json, numpy as np, pandas as pd
T='/tmp/claude-0/-home-user-sts-ai/b94b232e-4edc-561a-9463-dedf147e0ad5/scratchpad/train/'
K=['seed','decIdx','action']
g2=pd.read_csv(T+'gold2.csv',usecols=K+['chosen','labelFloor','labelWon']); g2=g2[g2.labelFloor.notna()]
g1=pd.read_csv(T+'gold.csv',usecols=K+['labelFloor']).rename(columns={'labelFloor':'old'})
cols=K+['labelFloor','labelFloorAlt','labelWon','labelWonAlt']
sb=pd.concat([pd.read_csv(f,usecols=cols) for f in glob.glob('/tmp/claude-0/sb2/w*/out/s-*.csv')]).drop_duplicates(K)
sb=sb.rename(columns={c:'sb_'+c for c in cols[3:]})
m=g2.merge(g1,on=K,how='left').merge(sb,on=K,how='left')
neur={}
for n,lab in [('v4final','V4 (A0 transformer)'),('W30_best_qtop1','G2 retrain'),('R2W30_best_qtop1','G3 retrain')]:
    d=json.load(open(T+f'g2eval_{n}_metrics.json'))['_qd']; neur[lab]={k:r for k,r,_ in d}
R={}; n=0
for (s,di),x in m.groupby(['seed','decIdx']):
    if len(x)<2: continue
    key=s*1000000+di
    if any(key not in v for v in neur.values()): continue
    if x.sb_labelFloor.isna().any() or x.old.isna().any() or not (x.chosen==1).any(): continue
    gold=x.labelFloor.to_numpy(); best=gold.max(); n+=1
    def reg(i): return best-gold[i]
    r={'random':best-gold.mean(),'heuristic':reg(int(np.flatnonzero(x.chosen.to_numpy()==1)[0])),
       'old gold (1 sample)':reg(int(np.argmax(x.old.to_numpy()))),
       'SB A0 floor':reg(int(np.argmax(x.sb_labelFloor.to_numpy()))),'SB A20 floor':reg(int(np.argmax(x.sb_labelFloorAlt.to_numpy()))),
       'SB A0 win':reg(int(np.argmax(x.sb_labelWon.to_numpy()+1e-3*x.sb_labelFloor.to_numpy()))),
       'SB A20 win':reg(int(np.argmax(x.sb_labelWonAlt.to_numpy()+1e-3*x.sb_labelFloorAlt.to_numpy())))}
    for lab,v in neur.items(): r[lab]=v[key]
    for k,v in r.items(): R.setdefault(k,[]).append(v)
R={k:np.array(v) for k,v in R.items()}
print('decisions',n)
bs=np.random.default_rng(20261011).integers(0,n,(10000,n))
def ci(d): mm=d[bs].mean(1); return f'{d.mean():+.2f} [{np.percentile(mm,2.5):+.2f}, {np.percentile(mm,97.5):+.2f}]'
print(f"{'picker':22s} regret  top1   heur-minus-this       this-minus-SB_A20floor")
for k,v in sorted(R.items(),key=lambda kv:kv[1].mean()):
    print(f"{k:22s} {v.mean():5.2f}  {np.mean(v<1e-9):.3f}  {ci(R['heuristic']-v):24s} {ci(v-R['SB A20 floor'])}")
