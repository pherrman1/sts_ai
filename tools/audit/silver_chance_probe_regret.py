import json, glob, collections, statistics as st, sys
rows=[json.loads(l) for f in sorted(glob.glob(sys.argv[1]+'/w*.jsonl')) for l in open(f)]
rows=[r for r in rows if 'rollouts' in r]
# pooled Q per edge index: visit-weighted mean of q over all 30k searches of both rules
out=collections.defaultdict(list); big=collections.Counter(); n=collections.Counter()
for r in rows:
    top=30000
    runs=[x for k in ('visits_rule','strat_rule') for x in r[k] if x['budget']==top]
    E=len(runs[0]['q']); qs=[0]*E; ws=[0]*E
    for x in runs:
        for i in range(E): qs[i]+=x['q'][i]*x['visits'][i]; ws[i]+=x['visits'][i]
    Q=[qs[i]/ws[i] if ws[i]>0 else -1e9 for i in range(E)]
    best=max(Q)
    for k in ('visits_rule','strat_rule'):
        for x in r[k]:
            i=max(range(E),key=lambda i:(x['visits'][i],-i))
            reg=best-Q[i]
            out[(k,x['budget'],r['room'])].append(reg); out[(k,x['budget'],'ALL')].append(reg)
for key in sorted(out):
    v=out[key]
    print(key,'n',len(v),'mean regret %.2f'%st.mean(v),'P(reg>1) %.3f'%(sum(1 for a in v if a>1)/len(v)),'P(reg>3) %.3f'%(sum(1 for a in v if a>3)/len(v)))
