import glob, os, numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
feats=[l.strip() for l in open('/tmp/claude-0/feats_rich.txt')]
cols=['seed','decIdx']+feats+['won','endFloor']
OUT='/tmp/claude-0/a20v/parts'; os.makedirs(OUT,exist_ok=True)
def load(f):
    o=os.path.join(OUT,f.split('/')[-2]+'_'+os.path.basename(f).replace('.csv.gz','.parquet'))
    if os.path.exists(o): return 1
    try:
        d=pd.read_csv(f,usecols=cols,engine='pyarrow')
    except Exception as e:
        open(o+'.err','w').write(str(e)); return 0
    d=d.drop_duplicates(['seed','decIdx'])
    d[feats+['won','endFloor']]=d[feats+['won','endFloor']].astype(np.float32)
    d.to_parquet(o); return 1
fs=sorted(glob.glob('/mnt/project-files/a20-value-retrain/runs-2c89ed97/*/chunk-*.csv.gz'))
with ProcessPoolExecutor(4) as ex:
    n=sum(ex.map(load,fs,chunksize=4))
print(len(fs),'files',n,'ok',flush=True)
