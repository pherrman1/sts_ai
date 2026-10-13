import sys, numpy as np, pandas as pd, xgboost as xgb
h=open(sys.argv[2]).read().strip().split(',')
rich=h[h.index('ascension'):h.index('won')]
cols=['dseed','dfloor','dec','cand','bits','score','screen','actionType','c1','c2','c3','cand1','cand2','cand3']+rich
d=pd.read_csv(sys.argv[1],header=None); d.columns=cols
b=xgb.Booster();b.load_model(sys.argv[3])
p=b.predict(xgb.DMatrix(d[b.feature_names].to_numpy(np.float32),feature_names=b.feature_names),iteration_range=(0,1157))
print('rows',len(d),'max abs diff',np.abs(p-d.score).max(), 'decisions',d.groupby(['dseed','dec']).ngroups)
g=d.assign(p=p).groupby(['dseed','dec']); print('argmax agree',np.mean([z.score.idxmax()==z.p.idxmax() for _,z in g]))
print('screens',d.groupby(['dseed','dec']).screen.first().value_counts().to_dict())
