import sys, json, numpy as np
sys.path.insert(0,'/home/user/sts_ai'); sys.path.insert(0,'/tmp/claude-0/a401/work')
from tools.analysis.vwin_tree_utils import split_counts
from fasttrees import Forest
from groups import group_of
from collections import defaultdict
Z=np.load('/tmp/claude-0/a401/work/a0.npz'); names=list(Z['names']); X=Z['X']; y=Z['y']; seeds=Z['seeds']; sp=Z['splits']
models={'B0':'/home/user/sts_ai/models/v_win_trees.txt','X2B':'/home/user/sts_ai/models/candidates/v_win_x2b_trees.txt','A20_419':'/home/user/sts_ai/models/candidates/v_win_a20_419.txt'}
rng=np.random.default_rng(401)
def ll(p,y): p=np.clip(p,1e-6,1-1e-6); return -(y*np.log(p)+(1-y)*np.log(1-p))
def auc(p,y):
    o=np.argsort(p); r=np.empty(len(p)); r[o]=np.arange(1,len(p)+1); n1=y.sum(); n0=len(y)-n1
    return (r[y==1].sum()-n1*(n1+1)/2)/(n1*n0)
out={}
for m,path in [(k,v) for k,v in models.items() if k==sys.argv[1]]:
    F=Forest(path); feats,trees=F.feats,F.trees; P=F.predict
    idx=[names.index(f) for f in feats]
    rows = (sp=='VALIDATION') if m=='X2B' else np.ones(len(y),bool)   # X2B trained on #334 TRAIN
    Xm=X[rows][:,idx]; ym=y[rows]; sm=seds=seeds[rows]
    p=P(Xm); base=ll(p,ym)
    useq=np.unique(sm); seed_ix={s:i for i,s in enumerate(useq)}; si=np.array([seed_ix[s] for s in sm])
    B=np.stack([rng.integers(0,len(useq),len(useq)) for _ in range(400)])
    def boot(delta):
        per=np.bincount(si,weights=delta,minlength=len(useq)); cnt=np.bincount(si,minlength=len(useq))
        bs_=[per[b].sum()/cnt[b].sum() for b in B]; return float(np.percentile(bs_,2.5)),float(np.percentile(bs_,97.5))
    sc=split_counts(trees,feats)
    var=Xm.var(0)
    groups=defaultdict(list)
    for j,f in enumerate(feats): groups[group_of(f)].append(j)
    res={'rows':int(rows.sum()),'seeds':len(useq),'win_rate':float(ym.mean()),'pred_mean':float(p.mean()),
         'logloss':float(base.mean()),'brier':float(((p-ym)**2).mean()),'auc':float(auc(p,ym)),
         'n_feats':len(feats),'n_trees':len(trees),'feats_never_split':sum(1 for f in feats if sc[f]==0),
         'feats_zero_var_on_eval':int((var==0).sum()),'groups':{}}
    for g,js in groups.items():
        deltas=[]; bri=[]; aucs=[]
        for r_ in range(2):
            Xp=Xm.copy(); perm=rng.permutation(len(ym)); Xp[:,js]=Xm[perm][:,js]
            pp=P(Xp); deltas.append(ll(pp,ym)-base); bri.append(((pp-ym)**2).mean()-((p-ym)**2).mean()); aucs.append(auc(pp,ym))
        d=np.mean(deltas,0)
        res['groups'][g]={'n_feats':len(js),'splits':int(sum(sc[feats[j]] for j in js)),
            'n_nonconst':int((var[js]>0).sum()),'perm_dlogloss':float(d.mean()),'ci95':boot(d),
            'perm_dbrier':float(np.mean(bri)),'perm_auc':float(np.mean(aucs))}
    # top individual features by permutation (only those with splits)
    top=[]
    cand=sorted([j for j in range(len(feats)) if sc[feats[j]]>0], key=lambda j:-sc[feats[j]])[:30]
    for j in cand:
        Xp=Xm.copy(); Xp[:,j]=Xm[rng.permutation(len(ym)),j]
        top.append((feats[j],int(sc[feats[j]]),float((ll(P(Xp),ym)-base).mean())))
    res['top_features']=sorted(top,key=lambda t:-t[2])[:25]
    out[m]=res
    print(m,json.dumps({k:v for k,v in res.items() if k not in('groups','top_features')}),flush=True)
    for g,v in sorted(res['groups'].items(),key=lambda kv:-kv[1]['perm_dlogloss']): print(f"  {g:28s} n={v['n_feats']:4d} splits={v['splits']:6d} dLL={v['perm_dlogloss']:.4f} ci={v['ci95'][0]:.4f},{v['ci95'][1]:.4f} AUC={v['perm_auc']:.3f}",flush=True)
    for t in res['top_features'][:15]: print('   ',t)
json.dump(out,open('/tmp/claude-0/a401/work/a0_perm_'+sys.argv[1]+'.json','w'),indent=1)
