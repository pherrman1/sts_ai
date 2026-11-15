"""Hit-rate table of the memostat arm (#1051): python analyze_memostat.py RESULTS_DIR."""
import json,glob,sys,statistics as st
rows={}
for f in sorted(glob.glob(sys.argv[1]+'/*memostat.jsonl')):
    g=f.split('/')[-1].split('-')[0]
    if g=='T': continue
    rows[g]=[json.loads(l) for l in open(f) if '"memo"' in l]
order=['A12','A3','SS','H']
tot={}
print('group n  hit%pooled  hit%mean[min,max]  turn0 turn1 turn2+  first  keys/search  calls/sim  mlp_us key_us bc_us look_us feat_us  mismatch bcInc')
for g in order+['ALL']:
    rs=rows.get(g) if g!='ALL' else sum((rows[x] for x in order if x in rows),[])
    if not rs: continue
    M=[r['memo'] for r in rs]
    S=lambda k: sum(m[k] for m in M)
    c=S('calls'); h=S('hits')
    per=[m['hits']/m['calls'] for m in M if m['calls']]
    ct=[sum(m['callsByTurn'][i] for m in M) for i in range(3)]
    ht=[sum(m['hitsByTurn'][i] for m in M) for i in range(3)]
    sims=sum(r['sims'] for r in rs)
    us=lambda k: 1e6*S(k)/c
    print(f"{g:4} {len(rs):2} {100*h/c:6.1f} {100*st.mean(per):8.1f}[{100*min(per):.0f},{100*max(per):.0f}] "
          + ' '.join(f"{100*ht[i]/max(ct[i],1):5.1f}({100*ct[i]/c:.0f}%)" for i in range(3))
          + f" {100*S('hitsFirst')/S('callsFirst'):5.1f} {S('keys')/len(rs):9.0f} {c/sims:6.1f} "
          + f"{us('mlpSeconds'):6.2f} {us('keySeconds'):5.2f} {us('bcHashSeconds'):5.2f} {us('lookupSeconds'):5.2f} {us('featureSeconds'):5.2f} {S('mismatches'):5} {S('bcHits')}/{S('bcInconsistent')}"
          + f"  cpu/sim {1e6*sum(r['cpu'] for r in rs)/sims:.1f}us")
