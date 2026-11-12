import json,glob,collections,sys,statistics as S
D=sys.argv[1] if len(sys.argv)>1 else '/tmp/claude-0/pw/out2'
A=collections.defaultdict(lambda: collections.defaultdict(list))
for f in sorted(glob.glob(D+'/*/A4P-*.roots.jsonl')):
    if not glob.glob(f.rsplit('/',1)[0]+'/*.done'): continue
    rows=[json.loads(l) for l in open(f)]; rows=[r for r in rows if not r.get('summary')]
    fights=collections.defaultdict(list)
    for r in rows: fights[r['fight']].append(r)
    for h in fights.values():
        h.sort(key=lambda r:r['decision'])
        cls='heart' if h[0]['encounter']=='THE_HEART' else ('act4-elite' if h[0]['act']==4 else h[0]['room'].lower())
        for i,r in enumerate(h):
            p=h[i-1] if i else None
            cont = p is not None and p['turn']==r['turn'] and r['decision']==p['decision']+1 and r['handSize']==p['handSize']-1
            pe=[e for e in r.get('preEdges',[]) if e[1]>0]
            kind='cont' if cont else 'other'
            A[cls][kind+'_n'].append(1); A[cls][kind+'_sims'].append(r['simulations'])
            if not pe: A[cls][kind+'_noplan'].append(1); continue
            plan=max(pe,key=lambda e:(e[1], e[2] if e[2] is not None else -1e9))[0]
            q={e[0]:e[2] for e in r['edges'] if e[2] is not None}
            agree= plan==r['chosen']
            A[cls][kind+'_agree'].append(agree)
            A[cls][kind+'_inh'].append(r['inheritedVisits'])
            if not agree and plan in q and r['chosen'] in q: A[cls][kind+'_regret'].append(q[r['chosen']]-q[plan])
for cls,v in sorted(A.items()):
    for kind in ('cont','other'):
        n=len(v[kind+'_n']); 
        if not n: continue
        ag=v[kind+'_agree']; rg=v[kind+'_regret']
        print(f"{cls:12s} {kind:5s} roots {n:5d} sims {sum(v[kind+'_sims'])/1e6:7.1f}M  with plan {len(ag):5d}  plan==choice {sum(ag)/max(len(ag),1):.3f}  inh median {S.median(v[kind+'_inh']) if v[kind+'_inh'] else 0:7.0f}  Q-gap when differ median {S.median(rg) if rg else float('nan'):.2f} mean {S.mean(rg) if rg else float('nan'):.2f} n {len(rg)}")
