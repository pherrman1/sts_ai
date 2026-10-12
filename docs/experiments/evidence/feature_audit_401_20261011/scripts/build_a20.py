import glob, os, sys, numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
feats=[l.strip() for l in open('/tmp/claude-0/a401/work/feats_b0.txt')]
extra=['fmDElite','fmDRest','fmDShop','fmDBoss','fmCElite','fmCRest','fmCShop','fmCEvent','fmCMonster','fmCTreasure','curMapX','curMapY']
cols=['seed','decIdx']+feats+extra+['won','endFloor']
OUT='/tmp/claude-0/a401/a20parts'; os.makedirs(OUT,exist_ok=True)
def load(f):
    o=os.path.join(OUT,f.split('/')[-2]+'_'+os.path.basename(f).replace('.csv.gz','.parquet'))
    if os.path.exists(o): return 1
    try: d=pd.read_csv(f,usecols=cols,engine='pyarrow')
    except Exception as e:
        open(o+'.err','w').write(str(e)); return 0
    d=d.drop_duplicates(['seed','decIdx'])
    d=d.sample(frac=1,random_state=401).groupby('seed').head(8)
    d[feats+extra+['won','endFloor']]=d[feats+extra+['won','endFloor']].astype(np.float32)
    d.to_parquet(o); return 1
if __name__=='__main__':
    fs=sorted(glob.glob('/mnt/project-files/a20-value-retrain/runs-2c89ed97/*/chunk-*.csv.gz'))[::2]
    with ProcessPoolExecutor(16) as ex: n=sum(ex.map(load,fs,chunksize=2))
    print(len(fs),'files',n,'ok',flush=True)
