import glob, sys, json, numpy as np, pandas as pd, xgboost as xgb
sys.path.insert(0,'/home/user/sts_ai'); from export_win_model import export_booster
feats=[l.strip() for l in open('/tmp/claude-0/feats_rich.txt')]
def _ld(f):
    d=pd.read_parquet(f)
    return d.sample(frac=1,random_state=0).groupby('seed').head(10)
D=pd.concat([_ld(f) for f in sorted(glob.glob('/tmp/claude-0/a20v/parts/*.parquet'))],ignore_index=True)
runs=D.groupby('seed').agg(won=('won','first'),fl=('endFloor','first'))
print('rows',len(D),'runs',len(runs),'win',runs.won.mean().round(4),'floor',runs.fl.mean().round(2),flush=True)
rng=np.random.default_rng(20261011); s=runs.index.to_numpy(); va_s=set(rng.choice(s,len(s)//10,replace=False))
va=D.seed.isin(va_s).to_numpy(); tr=~va
X=np.ascontiguousarray(D[feats].to_numpy(np.float32)); yF=D.endFloor.to_numpy(np.float32); yW=D.won.to_numpy(np.float32)
del D
json.dump(sorted(int(x) for x in va_s),open('/tmp/claude-0/a20v/val_seeds.json','w'))
def run(kind,y,base,obj,metric,out):
    dtr=xgb.QuantileDMatrix(X[tr],label=y[tr],feature_names=feats,max_bin=256)
    dva=xgb.DMatrix(X[va],label=y[va],feature_names=feats)
    b0=xgb.Booster(); b0.load_model(base)
    p0=b0.predict(dva)
    res={}
    if kind=='floor':
        res['A0']=dict(rmse=float(np.sqrt(np.mean((p0-y[va])**2))),bias=float(np.mean(p0-y[va])),r2=float(1-np.mean((p0-y[va])**2)/np.var(y[va])))
    else:
        from sklearn.metrics import roc_auc_score, log_loss
        res['A0']=dict(ll=float(log_loss(y[va],np.clip(p0,1e-6,1-1e-6))),auc=float(roc_auc_score(y[va],p0)),mean=float(p0.mean()),actual=float(y[va].mean()))
    print(kind,'A0',res['A0'],flush=True)
    P=dict(objective=obj,eta=0.05,max_depth=6,subsample=0.8,colsample_bytree=0.5,min_child_weight=20,eval_metric=metric,nthread=4,tree_method='hist',max_bin=256)
    for arm in ['warm','scratch']:
        if arm=='warm':
            # warm start: refit base_score shift via continued boosting on top of A0 trees
            b=xgb.train(P,dtr,num_boost_round=1500,evals=[(dva,'va')],early_stopping_rounds=50,xgb_model=base,verbose_eval=100)
        else:
            b=xgb.train(P,dtr,num_boost_round=3000,evals=[(dva,'va')],early_stopping_rounds=50,verbose_eval=200)
        p=b.predict(dva,iteration_range=(0,b.best_iteration+1))
        if kind=='floor':
            r=dict(rmse=float(np.sqrt(np.mean((p-y[va])**2))),bias=float(np.mean(p-y[va])),r2=float(1-np.mean((p-y[va])**2)/np.var(y[va])),trees=b.best_iteration+1)
        else:
            r=dict(ll=float(log_loss(y[va],np.clip(p,1e-6,1-1e-6))),auc=float(roc_auc_score(y[va],p)),mean=float(p.mean()),actual=float(y[va].mean()),trees=b.best_iteration+1)
        res[arm]=r; print(kind,arm,r,flush=True)
        export_booster(b,f'{out}_{arm}.txt',tree_count=b.best_iteration+1); b.save_model(f'{out}_{arm}.json')
    json.dump(res,open(f'{out}_metrics.json','w'),indent=1)
run('floor',yF,'/home/user/sts_ai/models/v_rich_xgb.json','reg:squarederror','rmse','/tmp/claude-0/a20v/v_rich_a20')
run('win',yW,'/home/user/sts_ai/models/v_win_xgb.json','binary:logistic','logloss','/tmp/claude-0/a20v/v_win_a20')
