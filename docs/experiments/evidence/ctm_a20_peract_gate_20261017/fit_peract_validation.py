import csv,math,collections,random
def load(f): return [r for r in csv.DictReader(open(f)) if r['scored']=='1']
val=load('/tmp/claude-0/work/val.nocal.csv'); test=load('/tmp/claude-0/work/test.nocal.csv')
BOSS=lambda r:r['room_class']=='BOSS'   # fit rule used by §470
def lg(p): p=min(max(p,1e-7),1-1e-7); return math.log(p/(1-p))
def fit(rs):
    # MLE shift d on death logit: p'=sigmoid(logit(p)+d)
    d=0
    for _ in range(50):
        g=h=0
        for r in rs:
            p=1/(1+math.exp(-(lg(float(r['p_death']))+d))); y=r['combat_outcome']=='2'
            g+=p-y; h+=p*(1-p)
        d-=g/h
    return d
glob=fit([r for r in val if BOSS(r)])
per={a:fit([r for r in val if BOSS(r) and r['act']==a]) for a in '123'}
print('global death-logit shift',round(glob,4),'(§470 survival shift -0.1833 => death shift +... check sign)')
print('per-act',{a:round(v,4) for a,v in per.items()})
def ev(rs,shift):
    by=collections.defaultdict(list)
    for r in rs: by[r['source_seed']].append(r)
    def agg(keys):
        n=nll=b=0
        for k in keys:
            for r in by[k]:
                p=1/(1+math.exp(-(lg(float(r['p_death']))+shift(r)))); y=r['combat_outcome']=='2'
                n+=1; nll+=-math.log(p if y else 1-p); b+=p-y
        return nll/n,b/n
    return agg(list(by)),by
for a in '123':
    rs=[r for r in test if BOSS(r) and r['act']==a]
    for lab,sh in [('none',lambda r:0),('global',lambda r:glob),('per-act',lambda r:per[r['act']])]:
        (nll,b),_=ev(rs,sh); print(f'TEST act{a} boss {lab:8s} nll={nll:.4f} bias={b:+.4f}')
rs=[r for r in test if BOSS(r)]
for lab,sh in [('none',lambda r:0),('global',lambda r:glob),('per-act',lambda r:per[r['act']])]:
    (nll,b),by=ev(rs,sh); print(f'TEST all boss {lab:8s} nll={nll:.4f} bias={b:+.4f}')
# paired seed bootstrap of NLL diff per-act minus global on all boss rows
by=collections.defaultdict(list)
for r in rs: by[r['source_seed']].append(r)
def nlld(r,sh):
    p=1/(1+math.exp(-(lg(float(r['p_death']))+sh))); y=r['combat_outcome']=='2'; return -math.log(p if y else 1-p)
dd={k:(sum(nlld(r,per[r['act']])-nlld(r,glob) for r in v),len(v)) for k,v in by.items()}
keys=list(dd); rnd=random.Random(3); bs=[]
for _ in range(1000):
    s=[rnd.choice(keys) for _ in keys]; bs.append(sum(dd[k][0] for k in s)/sum(dd[k][1] for k in s))
bs.sort(); print('per-act minus global NLL, all TEST boss rows: %.5f [%.5f, %.5f]'%(sum(v[0] for v in dd.values())/sum(v[1] for v in dd.values()),bs[25],bs[975]))
