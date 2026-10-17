import sys, numpy as np, xgboost as xgb
sys.path.insert(0, '/home/user/sts_ai/tools'); import heart_leaf_fit as h
S='/tmp/claude-0/-home-user-sts-ai/8ac63195-4fbf-5961-bc57-cc83a7c8592b/scratchpad'
out=h.load_outcomes([S+'/data/r2/train',S+'/data/r2/validation'])
d=h.load_tails([f'{S}/tails/out{k}.jsonl' for k in range(4)], out)
cr=np.load(S+'/exp/cr.npy'); ce=np.load(S+'/exp/ce.npy')
tr=d['train']; va=~tr; z=d['z']; act=d['act']
mr=d['X'][:,h.COL['x2bMargin']].astype(float); me=d['E'][:,h.COL['x2bMargin']].astype(float)
w_tr=h.run_weights(d['seed'][tr]); a,b=h.platt(mr[tr],z[tr],w_tr)
names=h.NAMES+['hlCritic']; X=np.c_[d['X'],cr]; E=np.c_[d['E'],ce]
ev=h.sigmoid(a+b*me)
tail=(d['term_sum']+np.bincount(d['owner'],weights=ev,minlength=len(mr)))/d['repeats']
y=0.5*tail+0.5*z
p={'objective':'binary:logistic','eta':0.03,'max_depth':5,'min_child_weight':2,'subsample':0.8,'colsample_bytree':0.5,'lambda':5,'nthread':4,'seed':0,'base_score':0.5}
def fit(m, ntrees=None, evalm=None):
    dt=xgb.DMatrix(X[m],label=y[m],weight=h.run_weights(d['seed'][m]),base_margin=a+b*mr[m],feature_names=names)
    if ntrees: return xgb.train(p,dt,ntrees),ntrees
    dv=xgb.DMatrix(X[evalm],label=y[evalm],weight=h.run_weights(d['seed'][evalm]),base_margin=a+b*mr[evalm],feature_names=names)
    g=xgb.train(p,dt,1500,evals=[(dv,'v')],early_stopping_rounds=50,verbose_eval=False); return g,g.best_iteration+1
def margin(g,n,m): return g.predict(xgb.DMatrix(X[m],base_margin=a+b*mr[m],feature_names=names),iteration_range=(0,n),output_margin=True)
g,n=fit(tr,evalm=va); print('trees',n)
mfull=np.zeros(len(z)); mfull[:]=margin(g,n,np.ones(len(z),bool))
# OOF on TRAIN, 4 folds by seed hash, fixed tree count n
fold=(d['seed']*2654435761 % 2**32)%4; oof=np.zeros(len(z))
for k in range(4):
    te=tr&(fold==k); gk,_=fit(tr&(fold!=k),ntrees=n); oof[te]=margin(gk,n,te)
def cal(mm,m):
    for A in (1,2,3,4):
        r=m&(act==A); w=h.run_weights(d['seed'][r]); print('  act',A,'pred %.3f real %.3f'%(np.average(h.sigmoid(mm[r]),weights=w),np.average(z[r],weights=w)))
print('TRAIN in-sample'); cal(mfull,tr)
print('TRAIN OOF'); cal(oof,tr)
# per-act logit offsets fitted on OOF TRAIN by weighted BCE
off={}
for A in (1,2,3,4):
    r=tr&(act==A); w=h.run_weights(d['seed'][r]); lo,hi=-3,3
    for _ in range(60):
        c=(lo+hi)/2; g_=np.average(h.sigmoid(oof[r]+c)-z[r],weights=w)
        lo,hi=(c,hi) if g_<0 else (lo,c)
    off[A]=(lo+hi)/2
print('offsets',off)
adj=mfull+np.array([off[A] for A in act])
for nm,mm in (('raw',mfull),('actcal',adj)):
    rep=h.report(nm,h.sigmoid(mm),d,va)
    print(nm,'bce %.4f auc %.3f'%(rep['bce_runweighted'],rep['auc_runweighted']),' '.join('a%s %.3f/%.3f'%(k,v['mean_pred'],v['mean_z']) for k,v in rep['acts'].items()))
