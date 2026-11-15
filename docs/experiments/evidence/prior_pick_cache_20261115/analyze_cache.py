"""Cache on/off table (#1051): python analyze_cache.py RESULTS_DIR LABEL... (pairs GROUP-BUDGET-pcLABEL with pc0)."""
import json,glob,sys,math
d=sys.argv[1]
def load(g,b,pc):
    try: return [json.loads(l) for l in open(f'{d}/{g}-{b}-pc{pc}.jsonl')]
    except FileNotFoundError: return None
groups=[('A12',16000),('A3',16000),('SS',10000),('H',40000)]
pcs=sys.argv[2:] or ['18','20','22']
print('group pc  hit%   cpu ratio(sum)  geomean  identical')
for pc in pcs:
    allb=allc=0; logs=[]; ident=0; n=0
    for g,b in groups:
        base=load(g,b,0); on=load(g,b,pc)
        if not base or not on: continue
        cb=sum(r['cpu'] for r in base); co=sum(r['cpu'] for r in on)
        h=sum(r['cacheHits'] for r in on); l=sum(r['cacheLookups'] for r in on)
        idn=sum(all(x[k]==y[k] for k in ('rootVisits','playoutActions','priorCalls','edge','sims')) for x,y in zip(base,on))
        lg=[math.log(y['cpu']/x['cpu']) for x,y in zip(base,on)]
        print(f"{g:4} {pc:3} {100*h/l:5.1f}  {co/cb:6.3f}  {math.exp(sum(lg)/len(lg)):6.3f}  {idn}/{len(base)}")
        allb+=cb; allc+=co; logs+=lg; ident+=idn; n+=len(base)
    if n: print(f"ALL  {pc:3}        {allc/allb:6.3f}  {math.exp(sum(logs)/len(logs)):6.3f}  {ident}/{n}")
