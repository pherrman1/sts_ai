import sys, numpy as np, pandas as pd
c=pd.read_csv(sys.argv[1]).set_index('seed'); t=pd.read_csv(sys.argv[2]).set_index('seed')
s=c.index.intersection(t.index); c=c.loc[s]; t=t.loc[s]
d=(t.floor-c.floor).to_numpy(float); rng=np.random.default_rng(20261012)
bs=np.array([d[rng.integers(0,len(d),len(d))].mean() for _ in range(10000)])
lo,hi=np.percentile(bs,[2.5,97.5]); m=d.mean()
v='GBM_BETTER' if lo>0 else 'GBM_WORSE' if hi<0 else 'NOT_SHOWN'
print(f'n={len(s)} C wins {c.won.sum()} floor {c.floor.mean():.2f} act3 {(c.act>=3).sum()} | T wins {t.won.sum()} floor {t.floor.mean():.2f} act3 {(t.act>=3).sum()}')
print(f'T-C floor {m:+.2f} [{lo:+.2f}, {hi:+.2f}] {v}; seeds differ {(t.floor!=c.floor).sum()}')
for a in (1,2,3): print('deaths act',a,'C',((c.act==a)&(c.won==0)).sum(),'T',((t.act==a)&(t.won==0)).sum())
print('sec/run C %.1f T %.1f'%(c.sec.mean(),t.sec.mean()))
