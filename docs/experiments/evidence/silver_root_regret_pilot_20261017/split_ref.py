#!/usr/bin/env python3
"""Per-root pilot (§526) with independent references: each half of the replicates is scored against its own 20k
reference, so reference noise cannot correlate the halves. Written by the post-merge review of #648.
usage: python3 -I split_ref.py DIR [DIR ...]"""
import glob, json, os, sys
import numpy as np
rows=[]
for d in sys.argv[1:]:
    for p in sorted(glob.glob(os.path.join(d,'**','*.roots.jsonl'),recursive=True)):
        rows += [json.loads(l) for l in open(p) if l.strip()]
ARMS=list(rows[0]['arms']); cands=[a for a in ARMS if a not in('base2500','base10000')]
def q1(ref):
    q=np.array([np.nan if e[2] is None else e[2] for e in ref],float); lo=np.nanmin(q); q[np.isnan(q)]=lo
    v=np.array([e[1] for e in ref],float); return q, int(np.argmax(v))
R={(a,j):[] for a in ARMS for j in (0,1)}; seeds=[]
for r in rows:
    for j in (0,1):
        q,b=q1(r['ref'][j])
        for a in ARMS: R[(a,j)].append([q[b]-q[p[0]] for p in r['arms'][a]])
    seeds.append(r['sourceSeed'])
R={k:np.array(v,float) for k,v in R.items()}; seeds=np.array(seeds); us=np.unique(seeds)
groups=[np.where(seeds==s)[0] for s in us]; rng=np.random.default_rng(0)
def boot(f,n=1000):
    v=[f(np.concatenate([groups[i] for i in rng.integers(0,len(us),len(us))])) for _ in range(n)]
    return np.round(np.percentile(v,[2.5,97.5]),4)
print('roots',len(rows))
for a in ARMS:
    k=min(R[(a,0)].shape[1],4); d=np.mean([(R[(a,j)][:,:k]-R[('base2500',j)][:,:k]).mean(1) for j in (0,1)],0)
    print('%-16s diff (per-ref avg) %+.4f CI %s'%(a,d.mean(),boot(lambda p:d[p].mean())))
print('== covariance, half1 scored on ref0, half2 on ref1 (and swapped, averaged)')
for a in cands:
    def cv(p):
        out=[]
        for j1,j2 in ((0,1),(1,0)):
            d1=(R[(a,j1)][p,:2]-R[('base2500',j1)][p,:2]).mean(1); d2=(R[(a,j2)][p,2:4]-R[('base2500',j2)][p,2:4]).mean(1)
            out.append(np.cov(d1,d2)[0,1])
        return np.mean(out)
    print('%-16s split-ref cov %.3f CI %s'%(a,cv(np.arange(len(rows))),boot(cv)))
    def cvs(p):
        d1=(R[(a,0)][p,:2]-R[('base2500',0)][p,:2]).mean(1); d2=(R[(a,0)][p,2:4]-R[('base2500',0)][p,2:4]).mean(1); return np.cov(d1,d2)[0,1]
    print('%-16s same-ref0 cov %.3f'%(a,cvs(np.arange(len(rows)))))
A=['base2500']+cands
def xfit(p, split=True):
    g=[]
    for s1,s2 in ((slice(0,2),slice(2,4)),(slice(2,4),slice(0,2))):
        for j1 in (0,1):
            j2=1-j1 if split else j1
            M1=np.stack([R[(a,j1)][p,s1].mean(1) for a in A],1); M2=np.stack([R[(a,j2)][p,s2].mean(1) for a in A],1)
            g.append((M2[:,0]-M2[np.arange(len(p)),M1.argmin(1)]).mean())
    return np.mean(g)
pa=np.arange(len(rows))
print('xfit oracle, select with ref j, score with other ref: %.4f CI %s'%(xfit(pa),boot(xfit)))
print('xfit oracle, same single ref: %.4f CI %s'%(xfit(pa,False),boot(lambda p:xfit(p,False))))
