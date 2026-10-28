import os
import pickle,statistics as st,random,sys
import numpy as np
P=os.environ.get('ELITE_DIR', '.') + '/'
def ne(g,act): return sum(1 for f in g['fights'] if f['act']==act and f['room']=='ELITE')
rows=[]
for ds in ('683','661','676'):
  d=pickle.load(open(P+f'elite{ds}.pkl','rb'))
  for (s,a),g in d.items():
    for act in (1,2,3):
      r=[r for r in g['roots'] if r['act']==act and r['row']==0]
      if not r: continue
      f=r[0]['feats']; em=max(c['emax'] for c in r[0]['kids'])
      rows.append(dict(ds=ds,seed=s,arm=a,act=act,emax=em,emin=min(c['emin'] for c in r[0]['kids']),nel=f['n_elite_nodes'],rest=f['rest'],shop=f['shop'],event=f['event'],mon=f['monster'],
        kill=g['kill'],a4=int(g['finalAct']>=4),clear=int(g['finalAct']>act),fought=ne(g,act) if g['finalAct']>act else None, hpstart=r[0]['hp']/r[0]['maxhp']))
def ols(R,y,cols):
  X=np.array([[1]+[r[c] for c in cols] for r in R],float); Y=np.array([r[y] for r in R],float)
  return np.linalg.lstsq(X,Y,rcond=None)[0]
def boot(R,y,cols,B=400):
  seeds=sorted({(r['ds'],r['seed']) for r in R}); by={}
  for r in R: by.setdefault((r['ds'],r['seed']),[]).append(r)
  b0=ols(R,y,cols)[1]; bs=[]
  rng=random.Random(7)
  for _ in range(B):
    RR=[x for s in (rng.choice(seeds) for _ in seeds) for x in by[s]]
    bs.append(ols(RR,y,cols)[1])
  bs.sort(); return b0,bs[int(.025*B)],bs[int(.975*B)]
for act in (1,2,3):
  for ds in ('683','661','676','all'):
    R=[r for r in rows if r['act']==act and (ds=='all' or r['ds']==ds)]
    ns=len({(r['ds'],r['seed']) for r in R})
    out=[]
    for y,cols in (('kill',['emax']),('kill',['emax','rest','shop','event','mon']),('a4',['emax']),('clear',['emax'])):
      b,lo,hi=boot(R,y,cols); out.append(f'{y}{"+ctl" if len(cols)>1 else ""} {b*100:+.1f} [{lo*100:+.1f},{hi*100:+.1f}]')
    F=[r for r in R if r['fought'] is not None]
    fb=ols(F,'fought',['emax'])[1]
    print(f'act{act} {ds:4s} seeds {ns:4d} games {len(R):5d} | elites fought/extra reachable {fb:+.2f} | '+' | '.join(out))
