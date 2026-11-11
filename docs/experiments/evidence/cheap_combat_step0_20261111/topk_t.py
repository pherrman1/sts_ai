import sys, json, numpy as np
sys.path.insert(0,'/home/user/sts_ai/tools/combat_net'); import model as M
A=M.Arrays('/tmp/claude-0/s0/tval'); a=A.a
ao=np.asarray(a['act_off']); g=np.asarray(a['gumbelChoice']); multi=np.asarray(a['multi']); act=np.asarray(a['act']); eb=np.asarray(a['elite_boss'])
qb=np.asarray(a['qb']); vis=np.asarray(a['visits']); prior=np.asarray(a['prior'])
score={'prior':prior}
for f in sys.argv[1:]: score[f]=np.load(f)
KS=[1,2,3,4,6,8]
def cls(r): return 'act4' if act[r]==4 else ['normal','elite','boss','other'][eb[r]]
res={}
for name,sc in score.items():
    agg={}
    for r in np.nonzero((multi>0)&(g>=0))[0]:
        s,e=ao[r],ao[r+1]; q=qb[s:e].astype(float); v=vis[s:e]; p=sc[s:e]; gi=g[r]
        if not np.isfinite(q[gi]): continue
        order=np.argsort(-p,kind='stable')
        for c in (cls(r),'all'):
            A_=agg.setdefault(c,{'n':0,'hit':np.zeros(len(KS)),'reg':np.zeros(len(KS))}); A_['n']+=1
            for i,k in enumerate(KS):
                top=order[:k]
                if gi in top: A_['hit'][i]+=1; continue
                qt=q[top]; ok=np.isfinite(qt)&(v[top]>0)
                A_['reg'][i]+= max(0.0,q[gi]-qt[ok].max()) if ok.any() else 50.0
    res[name]={c:{'roots':A_['n'],'hit':dict(zip(KS,(A_['hit']/A_['n']).round(4).tolist())),'regret':dict(zip(KS,(A_['reg']/A_['n']).round(3).tolist()))} for c,A_ in agg.items()}
    for c in ['all','normal','elite','boss','act4']:
        A_=agg[c]; print(name[:14].ljust(14),c.ljust(7),A_['n'],'hit',(A_['hit']/A_['n']).round(3),'reg',(A_['reg']/A_['n']).round(3))
json.dump(res,open('/tmp/claude-0/s0/topk_tensor.json','w'),indent=1)
