import sys, json, numpy as np, xgboost as xgb
sys.path.insert(0, '/home/user/sts_ai/tools'); import heart_leaf_fit as h
S='/tmp/claude-0/-home-user-sts-ai/8ac63195-4fbf-5961-bc57-cc83a7c8592b/scratchpad'
out=h.load_outcomes([S+'/data/r2/train',S+'/data/r2/validation'])
d=h.load_tails([f'{S}/tails/out{k}.jsonl' for k in range(4)], out)
cr=np.load(S+'/exp/cr.npy'); ce=np.load(S+'/exp/ce.npy')
tr=d['train']; va=~tr; z=d['z']
mr=d['X'][:,h.COL['x2bMargin']].astype(float); me=d['E'][:,h.COL['x2bMargin']].astype(float)
w_tr=h.run_weights(d['seed'][tr]); a,b=h.platt(mr[tr],z[tr],w_tr)
def run(name, w_anchor, critic, rounds=1, depth=5):
    names=h.NAMES+(['hlCritic'] if critic else [])
    X=np.c_[d['X'],cr] if critic else d['X']; E=np.c_[d['E'],ce] if critic else d['E']
    ev=h.sigmoid(a+b*me)
    for k in range(rounds):
        tail=(d['term_sum']+np.bincount(d['owner'],weights=ev,minlength=len(mr)))/d['repeats']
        y=(1-w_anchor)*tail+w_anchor*z
        p={'objective':'binary:logistic','eta':0.03,'max_depth':depth,'min_child_weight':2,'subsample':0.8,'colsample_bytree':0.5,'lambda':5,'nthread':4,'seed':0,'base_score':0.5}
        dt=xgb.DMatrix(X[tr],label=y[tr],weight=w_tr,base_margin=a+b*mr[tr],feature_names=names)
        dv=xgb.DMatrix(X[va],label=y[va],weight=h.run_weights(d['seed'][va]),base_margin=a+b*mr[va],feature_names=names)
        bst=xgb.train(p,dt,1500,evals=[(dv,'v')],early_stopping_rounds=50,verbose_eval=False); it=(0,bst.best_iteration+1)
        pr=bst.predict(xgb.DMatrix(X,base_margin=a+b*mr,feature_names=names),iteration_range=it)
        ev=np.concatenate([bst.predict(xgb.DMatrix(E[i:i+100000],base_margin=a+b*me[i:i+100000],feature_names=names),iteration_range=it) for i in range(0,len(me),100000)])
    rep=h.report(name,pr,d,va)
    print(name,'trees',it[1],'bce %.4f auc %.3f'%(rep['bce_runweighted'],rep['auc_runweighted']),' '.join('a%s %.3f/%.3f auc%.3f'%(k,v['mean_pred'],v['mean_z'],v['auc']) for k,v in rep['acts'].items()),flush=True)
for args in [('base',0.5,False),('critic',0.5,True),('w1',1.0,False),('w1critic',1.0,True),('w25',0.25,False),('w0',0.0,False)]:
    run(*args)
