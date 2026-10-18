import json,sys,glob,collections,statistics as st
rows=[]
for f in glob.glob(sys.argv[1]+'/**/*.decisions.json',recursive=True):
    for line in open(f):
        d=json.loads(line)
        if d.get('aborted') or d.get('singletonBypass'): continue
        c=d.get('rootCandidates') or []
        if len(c)<2: continue
        tot=sum(x['visits'] for x in c)
        ap=max(c,key=lambda x:x['prior']); av=max(c,key=lambda x:x['visits'])
        sel=[x for x in c if x['selected']][0]
        vis2=[x for x in c if x['visits']>=2]
        mq=max(c,key=lambda x:x['q'])
        mq10=max([x for x in c if x['visits']>=10] or [av],key=lambda x:x['q'])
        rows.append(dict(act=d['act'],screen=d['screen'].split('@')[0],n=len(c),tot=tot,
          topprior=ap['prior'],selIsArgPrior=sel is ap,topshare=av['visits']/tot,
          lock=d.get('earlyStopLock',0),altsMulti=sum(1 for x in c if x is not av and x['visits']>=2),
          altsMax=max(x['visits'] for x in c if x is not av),
          mqDiff=mq is not sel, mq10Diff=mq10 is not sel,
          qgap=mq['q']-sel['q'],sims=d['completedSimulations']))
print('roots',len(rows))
def summ(rs,name):
    if not rs: return
    n=len(rs)
    f=lambda k: sum(1 for r in rs if r[k])/n
    print(f"{name:28s} n={n:5d} topPrior med={st.median(r['topprior'] for r in rs):.4f} p>0.99={sum(r['topprior']>0.99 for r in rs)/n:.2f} "
          f"pick=argmaxPrior {f('selIsArgPrior'):.3f} topVisitShare med={st.median(r['topshare'] for r in rs):.4f} "
          f"lock {f('lock'):.2f} altMaxVisits med={st.median(r['altsMax'] for r in rs)} "
          f"rootsWithAnyAlt>=2visits {sum(r['altsMulti']>0 for r in rs)/n:.2f} maxQ!=pick {f('mqDiff'):.2f} maxQ(n>=10)!=pick {f('mq10Diff'):.2f}")
summ(rows,'ALL')
for a in (1,2,3,4): summ([r for r in rows if r['act']==a],f'act{a}')
by=collections.Counter(r['screen'] for r in rows)
for s,_ in by.most_common(8): summ([r for r in rows if r['screen']==s],s)
