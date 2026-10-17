import json, glob, itertools, collections, sys, statistics as st
rows=[];runs=[]
for f in sorted(glob.glob(sys.argv[1]+'/w*.jsonl')):
    for l in open(f):
        r=json.loads(l)
        (runs if r.get('kind')=='run' else rows).append(r)
print('runs',len(runs),'floors',collections.Counter(r.get('floor') for r in runs).most_common(8),'errors',[r['error'] for r in runs if r.get('error')])
print('roots',len(rows),collections.Counter(r['room'] for r in rows))
def agree(ch):
    n=len(ch); p=[a==b for a,b in itertools.combinations(ch,2)]
    return sum(p)/len(p)
# agreement per rule/budget
for rule in ('visits_rule','strat_rule'):
    for room in (None,'BOSS','ELITE','MONSTER'):
        res=collections.defaultdict(list)
        for r in rows:
            if room and r['room']!=room: continue
            byb=collections.defaultdict(list)
            for x in r[rule]: byb[x['budget']].append(x['chosen'])
            for b,ch in byb.items(): res[b].append(agree(ch))
        print(rule,room or 'ALL',{b:(round(st.mean(v),3),len(v)) for b,v in sorted(res.items())})
# reference = plurality of all 30k searches (both rules); match rate per rule/budget
for rule in ('visits_rule','strat_rule'):
    res=collections.defaultdict(list)
    for r in rows:
        top=max(x['budget'] for x in r['visits_rule'])
        ref=collections.Counter(x['chosen'] for k in ('visits_rule','strat_rule') for x in r[k] if x['budget']==top).most_common(1)[0][0]
        for x in r[rule]: res[x['budget']].append(x['chosen']==ref)
    print('match_pooled_top_ref',rule,{b:round(st.mean(v),3) for b,v in sorted(res.items())})
# leave-one-out: reference from the OTHER rule's top budget only (avoid self-reference)
for rule,other in (('visits_rule','strat_rule'),('strat_rule','visits_rule')):
    res=collections.defaultdict(list)
    for r in rows:
        top=max(x['budget'] for x in r[other])
        c=collections.Counter(x['chosen'] for x in r[other] if x['budget']==top).most_common()
        if len(c)>1 and c[0][1]==c[1][1]: continue
        ref=c[0][0]
        for x in r[rule]: res[x['budget']].append(x['chosen']==ref)
    print('match_other_rule_ref',rule,{b:(round(st.mean(v),3),len(v)) for b,v in sorted(res.items())})
# leaf inversion
inv=collections.defaultdict(lambda:[0,0]); lossAbove=collections.defaultdict(list); gap=collections.defaultdict(list)
for r in rows:
    ro=r['rollouts']; W=[o[3] for o in ro if o[0]==1]; L=[o for o in ro if o[0]==2]
    key=(r['room'],r['act'],r['actHealFollows'],r['finalFightLeaf'])
    if W and L:
        Ls=[o[3] for o in L]
        pairs=sum(1 for l in Ls for w in W if l>w); inv[key][0]+=pairs; inv[key][1]+=len(Ls)*len(W)
        gap[key].append(st.mean(W)-st.mean(Ls))
        mw=min(W); lossAbove[key].append(sum(1 for l in Ls if l>mw)/len(Ls))
print('leaf inversion P(loss score > win score) over root-matched pairs, by (room,act,actHeal,finalLeaf)')
for k in sorted(inv):
    a,b=inv[k]; print(k, 'pairs',b,'P=%.3f'%(a/b), 'meanGap %.1f'%st.mean(gap[k]), 'roots',len(gap[k]))
# loss score vs death turn
bt=collections.defaultdict(list); wt=collections.defaultdict(list)
for r in rows:
    for o in r['rollouts']:
        t=min(o[1]//5*5,40)
        (bt if o[0]==2 else wt)[t].append(o[3])
print('loss score by turn bucket',{t:(round(st.mean(v),1),len(v)) for t,v in sorted(bt.items())})
print('win score by turn bucket',{t:(round(st.mean(v),1),len(v)) for t,v in sorted(wt.items())})
