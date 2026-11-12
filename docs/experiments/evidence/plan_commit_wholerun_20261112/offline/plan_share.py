import json,glob,collections,sys,statistics as S
import sys; D=sys.argv[1] if len(sys.argv)>1 else 'out2'; R=collections.defaultdict(list)
for f in sorted(glob.glob(D+'/*/A4P-*.roots.jsonl')):
    rows=[json.loads(l) for l in open(f)]; rows=[r for r in rows if not r.get('summary')]
    fights=collections.defaultdict(list)
    for r in rows: fights[r['fight']].append(r)
    for h in fights.values():
        h.sort(key=lambda r:r['decision'])
        cls='heart' if h[0]['encounter']=='THE_HEART' else 'other'
        for i,r in enumerate(h):
            p=h[i-1] if i else None
            if not(p and p['turn']==r['turn'] and r['decision']==p['decision']+1 and r['handSize']==p['handSize']-1): continue
            pe=[e for e in r.get('preEdges',[]) if e[1]>0]
            if not pe: continue
            tot=sum(e[1] for e in pe); top=max(pe,key=lambda e:e[1]); share=top[1]/tot
            q={e[0]:e[2] for e in r['edges'] if e[2] is not None}
            gap=q[r['chosen']]-q[top[0]] if top[0] in q and r['chosen'] in q else 0.0
            R[cls].append((share,top[0]==r['chosen'],gap,r['simulations'],tot))
for cls,v in R.items():
    allsims=sum(x[3] for x in v)
    print(cls,'cont roots',len(v))
    for th in (0,0.5,0.7,0.8,0.9,0.95):
        s=[x for x in v if x[0]>=th]
        if not s: continue
        ag=sum(x[1] for x in s)/len(s); gaps=[x[2] for x in s if not x[1]]
        print(f"  share>={th:.2f}: roots {len(s)/len(v):.2f} sims saved {sum(x[3] for x in s)/allsims:.2f} agree {ag:.3f} gap mean {S.mean(gaps) if gaps else 0:.3f} median {S.median(gaps) if gaps else 0:.3f} p90 {sorted(gaps)[int(.9*len(gaps))] if gaps else 0:.2f}")
