import csv,glob,os,json,random
R=os.path.dirname(os.path.abspath(__file__))
def load(arm):
    d={}
    for f in glob.glob(f'{R}/{arm}/*.csv'):
        if f.endswith('.mcts.csv'): continue
        ex=f.replace('.csv','.exit')
        if not os.path.exists(ex) or open(ex).read().strip()!='0': continue
        rows=list(csv.DictReader(open(f)))
        if len(rows)==1: d[int(rows[0]['seed'])]=rows[0]
    return d
arms={a:load(a) for a in ('A_playout','B_direct','C_screen')}
seeds=sorted(set.intersection(*[set(v) for v in arms.values()])); n=len(seeds)
def col(a,k): return [float(arms[a][s][k]) for s in seeds]
def boot(x,y,reps=10000):
    rng=random.Random(379); d=[b-a for a,b in zip(x,y)]; m=sorted(sum(d[rng.randrange(n)] for _ in range(n))/n for _ in range(reps))
    return [sum(d)/n, m[int(.025*reps)], m[int(.975*reps)]]
out={'pairs':n,'arms':{a:{'win':sum(col(a,'won'))/n,'floor':sum(col(a,'floor'))/n,'sec':sum(col(a,'sec'))/n} for a in arms}}
for x,y in (('A_playout','B_direct'),('A_playout','C_screen'),('B_direct','C_screen')):
    out[f'{y}-{x}']={'win':boot(col(x,'won'),col(y,'won')),'floor':boot(col(x,'floor'),col(y,'floor')),
        'discordant':[sum(a and not b for a,b in zip(col(x,'won'),col(y,'won'))),sum(b and not a for a,b in zip(col(x,'won'),col(y,'won')))]}
ev=fb=0
for f in glob.glob(f'{R}/C_screen/*.support.jsonl'):
    for l in open(f):
        j=json.loads(l); ev+=j.get('screen_leaf_evaluations',0); fb+=j.get('screen_leaf_fallbacks',0)
out['screen_leaf_evaluations']=ev; out['screen_leaf_fallbacks_to_direct']=fb
print(json.dumps(out,indent=1))
