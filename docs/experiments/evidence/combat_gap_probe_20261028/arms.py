# usage: arms.py OUTDIR [ref_dir]  -- paired arm analysis of expertfights runs with STS_EXPERT_FIGHTS_ARMS
import glob,json,statistics as st,collections,sys,random,os
def loss(f,r): return f['hp']-(r['exitHp'] if r['won'] else 0)
R=[]; armset=set(); runs=0
for p in sorted(glob.glob(sys.argv[1]+'/**/*.fights.json',recursive=True)):
    x=json.load(open(p)); runs+=1
    for f in x['fights']:
        if 'arms' not in f: continue
        e=f['expert']
        if e['exitHp'] is None or f['loggedFightsOnFloor']>1: continue
        K=len(f['arms'][next(iter(f['arms']))])
        prod=f['replicates'][:K]
        if not all(r['valid'] for r in prod): continue
        row=dict(run=x['runFile'],act=f['act'],room=f['room'],enc=f['encounter'],floor=f['floor'],
                 e=f['hp']-(0 if e['died'] else e['exitHp']),
                 P=st.mean(loss(f,r) for r in prod), Pd=st.mean(not r['won'] for r in prod),
                 Pu=st.mean(len(r['potionsUsed']) for r in prod), Pc=st.mean(r['cpu'] for r in prod))
        for a,reps in f['arms'].items():
            armset.add(a)
            row[a]=st.mean(loss(f,r) for r in reps); row[a+'_d']=st.mean(not r['won'] for r in reps)
            row[a+'_u']=st.mean(len(r['potionsUsed']) for r in reps); row[a+'_c']=st.mean(r['cpu'] for r in reps)
        R.append(row)
def boot(rows,fn,B=4000,seed=20261028):
    g=collections.defaultdict(list)
    for r in rows: g[r['run']].append(fn(r))
    G=list(g.values()); rng=random.Random(seed); ms=[]
    for _ in range(B):
        s=[v for _ in G for v in rng.choice(G)]; ms.append(st.mean(s))
    ms.sort(); return st.mean(fn(r) for r in rows), ms[int(.025*B)], ms[int(.975*B)]
print('runs',runs,'fights',len(R))
def report(lbl,rows):
    if len(rows)<3: return
    print(f'-- {lbl}: n={len(rows)} expert={st.mean(r["e"] for r in rows):.2f} prod={st.mean(r["P"] for r in rows):.2f} (death {st.mean(r["Pd"] for r in rows):.3f}, pots {st.mean(r["Pu"] for r in rows):.2f}, cpu {st.mean(r["Pc"] for r in rows):.1f}s)')
    for a in sorted(armset):
        m,lo,hi=boot(rows,lambda r:r[a]-r['P'])
        print(f'   {a:18s} loss {st.mean(r[a] for r in rows):6.2f}  arm-prod {m:+.2f} [{lo:+.2f},{hi:+.2f}]  death {st.mean(r[a+"_d"] for r in rows):.3f} pots {st.mean(r[a+"_u"] for r in rows):.2f} cpu {st.mean(r[a+"_c"] for r in rows):.1f}s')
report('all',R)
for k in sorted({(r['act'],r['room']) for r in R}): report(k,[r for r in R if (r['act'],r['room'])==k])
for k in sorted({r['enc'] for r in R}): report(k,[r for r in R if r['enc']==k])
