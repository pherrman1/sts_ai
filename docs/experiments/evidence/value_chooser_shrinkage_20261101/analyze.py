#!/usr/bin/env python3
"""Optimizer's-curse shrinkage check on §727 (README.md). usage: analyze.py UNITS_PKL OUT_JSON"""
import pickle, sys, json, numpy as np, collections
U=pickle.load(open(sys.argv[1],'rb'))
ALPHAS=[0.16,0.17,0.18]; TAUS=[0.005,0.01,0.02]
rng=np.random.default_rng(20261101)
def boot(x,n=10000):
    x=np.asarray(x,float); 
    if len(x)==0: return [None,None]
    m=x[rng.integers(0,len(x),(n,len(x)))].mean(1); return [float(np.quantile(m,.025)),float(np.quantile(m,.975))]
def bootdiff(x,y,n=10000):
    x=np.asarray(x,float);y=np.asarray(y,float)
    mx=x[rng.integers(0,len(x),(n,len(x)))].mean(1); my=y[rng.integers(0,len(y),(n,len(y)))].mean(1)
    d=mx-my; return [float(np.quantile(d,.025)),float(np.quantile(d,.975))]
units=[]
for u in U:
    if not u.get('A') or not u.get('B') or ' rc=0 ' not in u.get('done','')+' ': continue
    ch=[]
    for c in u.get('ch',[]):
        v=[x['value'] for x in c['candidates']]; p=[x['prior'] for x in c['candidates']]
        ch.append(dict(act=c['act'],screen=c['screen'],floor=c['floor'],dv=v[c['chosen']]-v[0],chosen=c['chosen'],
                       maxdv=max(v)-v[0], ptie=p[c['chosen']]>=p[0]))
    d=float(u['B']['heartKilled'])-float(u['A']['heartKilled'])
    units.append(dict(seed=u['seed'],d=d,ch=ch,a=float(u['A']['heartKilled']),b=float(u['B']['heartKilled'])))
print('units',len(units))
res={'units':len(units)}
ov=[c for u in units for c in u['ch'] if c['chosen']!=0]
allc=[c for u in units for c in u['ch']]
dv=np.array([c['dv'] for c in ov])
res['choices']=len(allc); res['overrides']=len(ov); res['override_prior_ties']=sum(c['ptie'] for c in ov)
res['override_dv_quantiles']={q:float(np.quantile(dv,q)) for q in (.1,.25,.5,.75,.9,.95,.99)}
res['surviving_fraction']={f'a{a}_t{t}':float((a*dv>t).mean()) for a in ALPHAS for t in TAUS}
# primary: first override
def first(u):
    return next((c for c in u['ch'] if c['chosen']!=0),None)
prim={}
for a in ALPHAS:
  for t in TAUS:
    L=[u['d'] for u in units if first(u) and a*first(u)['dv']>t]
    S=[u['d'] for u in units if first(u) and a*first(u)['dv']<=t]
    prim[f'a{a}_t{t}']=dict(nL=len(L),L=float(np.mean(L)) if L else None,L_ci=boot(L),nS=len(S),S=float(np.mean(S)),S_ci=boot(S),
        L_minus_S=float(np.mean(L)-np.mean(S)) if L else None, L_minus_S_ci=bootdiff(L,S) if L else None)
res['first_override']=prim
# dv bins of first override
bins=[0,0.005,0.01,0.02,0.04,0.0588,0.1,1]
fb=[]
for lo,hi in zip(bins[:-1],bins[1:]):
    x=[u['d'] for u in units if first(u) and lo<first(u)['dv']<=hi]
    fb.append(dict(lo=lo,hi=hi,n=len(x),diff=float(np.mean(x)) if x else None,ci=boot(x)))
res['first_override_bins']=fb
# slope of unit diff on first dv
F=[(first(u)['dv'],u['d']) for u in units if first(u)]
x=np.array([f[0] for f in F]);y=np.array([f[1] for f in F])
def slope(x,y): X=np.c_[np.ones_like(x),x]; return np.linalg.lstsq(X,y,rcond=None)[0]
b=slope(x,y); bs=[]
for _ in range(5000):
    i=rng.integers(0,len(x),len(x)); bs.append(slope(x[i],y[i])[1])
res['first_dv_slope']=dict(intercept=float(b[0]),slope_pp_per_dv=float(b[1]),ci=[float(np.quantile(bs,.025)),float(np.quantile(bs,.975))],n=len(x))
# exact counterfactual subset: shrunk chooser == B when every B override survives (or none)
ex={}
for a in ALPHAS:
  for t in TAUS:
    al=[u['d'] for u in units if any(c['chosen']!=0 for c in u['ch']) and all(a*c['dv']>t for c in u['ch'] if c['chosen']!=0)]
    ex[f'a{a}_t{t}']=dict(n=len(al),diff=float(np.mean(al)) if al else None,ci=boot(al))
res['all_overrides_survive']=ex
# secondary regression: d ~ nL + nS (post-treatment counts, endogenous)
reg={}
for a in [0.17]:
  for t in [0.01]:
    X=np.array([[1,sum(1 for c in u['ch'] if c['chosen']!=0 and a*c['dv']>t),sum(1 for c in u['ch'] if c['chosen']!=0 and a*c['dv']<=t)] for u in units],float)
    Y=np.array([u['d'] for u in units]); co=np.linalg.lstsq(X,Y,rcond=None)[0]; bb=[]
    for _ in range(5000):
        i=rng.integers(0,len(Y),len(Y)); bb.append(np.linalg.lstsq(X[i],Y[i],rcond=None)[0])
    bb=np.array(bb)
    reg[f'a{a}_t{t}']=dict(coef=dict(zip(['const','per_large','per_small'],map(float,co))),
        ci={k:[float(np.quantile(bb[:,j],.025)),float(np.quantile(bb[:,j],.975))] for j,k in enumerate(['const','per_large','per_small'])})
res['count_regression']=reg
# by act/screen of first override, large vs small at a=.17 t=.01
by=collections.defaultdict(lambda:{'L':[],'S':[]})
for u in units:
    f=first(u)
    if f: by[f"act{f['act']}_s{f['screen']}"]['L' if .17*f['dv']>.01 else 'S'].append(u['d'])
res['first_override_by_screen']={k:{g:dict(n=len(v[g]),diff=float(np.mean(v[g])) if v[g] else None,ci=boot(v[g])) for g in 'LS'} for k,v in sorted(by.items())}
json.dump(res,open(sys.argv[2],'w'),indent=1)
print(json.dumps({k:res[k] for k in ('units','overrides','override_dv_quantiles','surviving_fraction','first_dv_slope')},indent=1))
print(json.dumps(res['first_override']['a0.17_t0.01'],indent=1))
print(json.dumps(res['first_override_bins'],indent=1))
print(json.dumps(res['all_overrides_survive'],indent=1)); print(json.dumps(res['count_regression'],indent=1)); print(json.dumps(res['first_override_by_screen'],indent=1))
