import glob, hashlib, json, gzip, numpy as np, pandas as pd
fs=sorted(glob.glob('/tmp/claude-0/a401/a20parts/*.parquet'))
D=pd.concat([pd.read_parquet(f) for f in fs],ignore_index=True)
feats=[l.strip() for l in open('feats_b0.txt')]
extra=['fmDElite','fmDRest','fmDShop','fmDBoss','fmCElite','fmCRest','fmCShop','fmCEvent','fmCMonster','fmCTreasure','curMapX','curMapY']
def split(s):
    u=int(hashlib.sha256(f'issue401-a20-v1:{s}'.encode()).hexdigest()[:8],16)/2**32
    return 'TEST' if u>=0.85 else 'VAL' if u>=0.70 else 'ES' if u>=0.62 else 'TRAIN'
seeds=D.seed.to_numpy(); us=np.unique(seeds); sm={s:split(s) for s in us}
sp=np.array([sm[s] for s in seeds])
v419=set(json.load(gzip.open('/home/user/sts_ai/docs/experiments/evidence/v4_a20_retrain_20261009/gold2/a20_trees/val_seeds.json.gz')))
np.savez('a20.npz',X=D[feats+extra].to_numpy(np.float32),won=D.won.to_numpy(np.float32),floor=D.endFloor.to_numpy(np.float32),
  seeds=seeds,splits=sp,names=np.array(feats+extra),in419val=np.isin(seeds,list(v419)))
r=D.groupby('seed').agg(won=('won','first'),fl=('endFloor','first'))
print('rows',len(D),'runs',len(r),'win',r.won.mean(),'floor',r.fl.mean(),{k:int((sp==k).sum()) for k in set(sp)},'419val rows',int(np.isin(seeds,list(v419)).sum()))
