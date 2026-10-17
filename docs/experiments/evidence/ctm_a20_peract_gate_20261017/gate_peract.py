"""Per-act boss shift gate (PREREG-PERACT.md 47f72819). Usage: gate_peract.py SCORES.csv OUT.json"""
import csv,sys,math,random,collections,json
GLOBAL=-0.18325317250506112          # death-logit shift = §470 survival shift (runtime: survival logit -= shift)
PER={'1':-0.4747,'2':-0.2371,'3':0.0720}
BOSS_ENC={18,19,20,37,38,39,53,54,55,57}
rows=[r for r in csv.DictReader(open(sys.argv[1]))]
assert all(r['scored']=='1' for r in rows)
def lg(p): p=min(max(p,1e-12),1-1e-12); return math.log(p/(1-p))
def sig(x): return 1/(1+math.exp(-x))
def pd(r,arm):
    p=float(r['p_death']); enc=int(r['encounter'])
    if arm=='inc': return sig(lg(p)+GLOBAL) if enc in BOSS_ENC else p
    if r['room_class']=='BOSS' and r['act'] in PER: return sig(lg(p)+PER[r['act']])
    # candidate: non-room-BOSS boss encounters keep the incumbent rule only if act 4 excluded? prereg: shift by act on boss rows
    if enc in BOSS_ENC and r['act'] in PER: return sig(lg(p)+PER[r['act']])
    return p
def nll(p,y): p=min(max(p,1e-12),1-1e-12); return -math.log(p if y else 1-p)
by=collections.defaultdict(list)
for r in rows: by[r['source_seed']].append(r)
seeds=list(by)
def stat(sel,keys):
    n=dn=dc=bi=bc=0
    for k in keys:
        for r in by[k]:
            if not sel(r): continue
            y=r['combat_outcome']=='2'; pi,pc=pd(r,'inc'),pd(r,'cand')
            n+=1; dn+=nll(pc,y)-nll(pi,y); bc+=pc-y; bi+=pi-y
    return (dn/n,bc/n,bi/n,n) if n else (float('nan'),)*3+(0,)
def boot(sel,B=2000):
    pt=stat(sel,seeds); rnd=random.Random(20261017); d=[];b=[]
    for _ in range(B):
        s=[rnd.choice(seeds) for _ in seeds]; x=stat(sel,s); d.append(x[0]); b.append(x[1])
    d.sort(); b.sort(); q=lambda v:[v[int(.025*B)],v[int(.975*B)-1]]
    return {'n':pt[3],'nllDiff':pt[0],'nllDiffCi':q(d),'candBias':pt[1],'candBiasCi':q(b),'incBias':pt[2]}
res={}
res['boss']=boot(lambda r:r['room_class']=='BOSS')
for a in '123': res[f'boss_act{a}']=boot(lambda r,a=a:r['room_class']=='BOSS' and r['act']==a,B=1000)
res['other_boss_encounter']=stat(lambda r:r['room_class']!='BOSS' and int(r['encounter']) in BOSS_ENC,seeds)
nonboss_diff=sum(1 for r in rows if int(r['encounter']) not in BOSS_ENC and pd(r,'inc')!=pd(r,'cand'))
c={'1_boss_nll_upper_ci_lt_0':res['boss']['nllDiffCi'][1]<0,
   '2_pooled_boss_bias_abs_le_0.01':abs(res['boss']['candBias'])<=0.01,
   '3_per_act_boss_bias_abs_le_0.02':all(abs(res[f'boss_act{a}']['candBias'])<=0.02 for a in '123'),
   '4_nonboss_identical':nonboss_diff==0}
res['criteria']=c; res['verdict']='PASS' if all(c.values()) else 'FAIL'
res['rows']=len(rows); res['seeds']=len(seeds)
json.dump(res,open(sys.argv[2],'w'),indent=2); print(json.dumps(res,indent=1))
