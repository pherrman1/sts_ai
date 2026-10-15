import glob, sys, numpy as np, pandas as pd
G='/tmp/claude-0/-home-user-sts-ai/b94b232e-4edc-561a-9463-dedf147e0ad5/scratchpad/train/gold.csv'
g=pd.read_csv(G,usecols=['seed','decIdx','action','chosen','labelFloor'])
fs=glob.glob('/tmp/claude-0/sb2/w*/out/s-*.csv')
cols=['seed','decIdx','action','chosen','labelFloor','labelFloorAlt','labelWon','labelWonAlt']
t=pd.concat([pd.read_csv(f,usecols=cols) for f in fs]).drop_duplicates(['seed','decIdx','action'])
t=t[t.labelFloor.notna()]
m=t.merge(g[g.labelFloor.notna()],on=['seed','decIdx','action'],suffixes=('','_g'))
mismatch=(m.chosen!=m.chosen_g).sum()
res={k:[] for k in ['random','heur','A0floor','A20floor','A0win','A20win']}; reg={k:[] for k in res}
rng=np.random.default_rng(0); n=0
for k,x in m.groupby(['seed','decIdx']):
    if len(x)<2: continue
    gold=x.labelFloor_g.to_numpy(); best=gold.max(); n+=1
    def pick(v): return int(np.argmax(v))
    picks={'heur':int(np.flatnonzero(x.chosen.to_numpy()==1)[0]) if (x.chosen==1).any() else None,
           'A0floor':pick(x.labelFloor.to_numpy()),'A20floor':pick(x.labelFloorAlt.to_numpy()),
           'A0win':pick(x.labelWon.to_numpy()+1e-3*x.labelFloor.to_numpy()),'A20win':pick(x.labelWonAlt.to_numpy()+1e-3*x.labelFloorAlt.to_numpy())}
    res['random'].append(float(np.mean(gold==best))); reg['random'].append(best-gold.mean())
    for kk,p in picks.items():
        if p is None: continue
        res[kk].append(int(gold[p]==best)); reg[kk].append(best-gold[p])
print('decisions',n,'chosen mismatches',mismatch,'gold decisions total',g[g.labelFloor.notna()].groupby(['seed','decIdx']).ngroups)
for kk in res:
    a=np.array(res[kk]); r=np.array(reg[kk])
    print(f'{kk:9s} top1 {a.mean():.3f}  regret {r.mean():.2f} floors  n={len(a)}')
R={k:np.array(v) for k,v in reg.items()}
# paired bootstrap over decisions (heur has n-? missing; align by using decisions where heur present)
idx=[i for i in range(len(reg['random']))]
def ci(a,b,label):
    a=np.array(reg[a]);b=np.array(reg[b]);n=min(len(a),len(b))
    d=(a-b) if len(a)==len(b) else None
    if d is None: return
    bs=np.random.default_rng(20261011).integers(0,len(d),(10000,len(d)))
    m=d[bs].mean(1); print(f'{label}: {d.mean():.2f} [{np.percentile(m,2.5):.2f}, {np.percentile(m,97.5):.2f}]')
ci('A0win','A20win','regret A0win - A20win')
ci('A0floor','A20floor','regret A0floor - A20floor')
ci('random','A20win','regret random - A20win')
ci('A0floor','A0win','regret A0floor - A0win')
# heuristic paired CI on decisions where heur exists
H=[];A=[];Fl=[]
for k,x in m.groupby(['seed','decIdx']):
    if len(x)<2 or not (x.chosen==1).any(): continue
    gold=x.labelFloor_g.to_numpy(); best=gold.max()
    h=int(np.flatnonzero(x.chosen.to_numpy()==1)[0])
    H.append(best-gold[h]); A.append(best-gold[int(np.argmax(x.labelFloorAlt.to_numpy()))])
d=np.array(H)-np.array(A); bs=np.random.default_rng(1).integers(0,len(d),(10000,len(d))); mm=d[bs].mean(1)
print('heur - A20floor regret: %.2f [%.2f, %.2f] n=%d'%(d.mean(),np.percentile(mm,2.5),np.percentile(mm,97.5),len(d)))
