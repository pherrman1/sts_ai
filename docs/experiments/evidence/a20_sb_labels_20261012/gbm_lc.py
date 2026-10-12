import json, numpy as np, pandas as pd, xgboost as xgb
T='/tmp/claude-0/-home-user-sts-ai/b94b232e-4edc-561a-9463-dedf147e0ad5/scratchpad/train/'
drop={'seed','decIdx','action','chosen','won','endFloor','endHp','labelWon','labelHp','labelFloor','labelBootstrap','labelWonAlt','labelFloorAlt',
      'nextEliteId','nextFight0','nextFight1','nextFight2','remElites','remFights','monOffset','eliteOffset','potionChance','cardRarityFactor'}
d=pd.read_csv(T+'sbl_a20.csv'); d=d[d.labelFloor.notna()]
d=d[d.groupby(['seed','decIdx']).labelFloor.transform('size')>=2].sort_values(['seed','decIdx'],kind='stable')
feats=[c for c in d.columns if c not in drop]
sp=json.load(open(T+'split_sbl.json')); va=d.seed.isin(sp['val_seeds'])
def dm(x,rank=False):
    g=x.groupby(['seed','decIdx'],sort=False).size().to_numpy()
    y=(x.labelFloor-x.groupby(['seed','decIdx']).labelFloor.transform('mean')).to_numpy(np.float32)
    if rank: y=(x.groupby(['seed','decIdx']).labelFloor.rank(method='dense')-1).to_numpy(np.float32)
    m=xgb.DMatrix(x[feats].to_numpy(np.float32),label=y,feature_names=feats); m.set_group(g); return m
res={}
import sys
obj='reg:squarederror'
trs=np.array(sorted(d[~va].seed.unique())); np.random.default_rng(7).shuffle(trs)
for frac in [0.25,0.5]:
    keep=set(trs[:int(len(trs)*frac)].tolist())
    dtr,dva=dm(d[~va & d.seed.isin(keep)]),dm(d[va])
    P=dict(objective=obj,eta=0.05,max_depth=6,subsample=0.8,colsample_bytree=0.5,min_child_weight=20,nthread=4,tree_method='hist')
    if obj.startswith('rank'): P['eval_metric']='ndcg@1'; P['ndcg_exp_gain']=False
    b=xgb.train(P,dtr,2000,evals=[(dva,'va')],early_stopping_rounds=100,verbose_eval=200)
    b.save_model(T+f'gbm_lc{frac}.json')
    g2=pd.read_csv(T+'gold2.csv'); g2=g2[g2.labelFloor.notna()]
    g2['pred']=b.predict(xgb.DMatrix(g2[feats].to_numpy(np.float32),feature_names=feats),iteration_range=(0,b.best_iteration+1))
    # val regret on SB labels
    for name,x,pc in [('val_sb',d[va].assign(pred=b.predict(dva,iteration_range=(0,b.best_iteration+1))),'labelFloor'),('gold2',g2,'labelFloor')]:
        r=[];key=[]
        for k,z in x.groupby(['seed','decIdx']):
            if len(z)<2: continue
            t=z[pc].to_numpy(); r.append(t.max()-t[int(np.argmax(z.pred.to_numpy()))]); key.append(k[0]*1000000+k[1])
        print(frac,name,'regret %.3f n=%d'%(np.mean(r),len(r)),flush=True)
        if name=='gold2': json.dump(list(zip(key,r)),open(T+f'gbm_lc{frac}_gold2.json','w'))
