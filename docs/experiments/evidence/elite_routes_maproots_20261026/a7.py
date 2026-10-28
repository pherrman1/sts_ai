"""First-divergence pairs at map roots: elite-heavier child vs other, same seed."""
import gzip,json,os,sys,itertools,pickle
from multiprocessing import Pool

ELITE=3
def child_stats(r,x):
  xs,ys,rt,pxs=r['obs.map.xs'],r['obs.map.ys'],r['obs.map.roomTypes'],r['obs.map.pathXs']
  idx={(a,b):i for i,(a,b) in enumerate(zip(xs,ys))}; memo={}
  def go(i):
    if i in memo: return memo[i]
    e=1 if rt[i]==ELITE else 0
    nxt=[idx[(nx,ys[i]+1)] for nx in pxs[i] if nx>=0 and (nx,ys[i]+1) in idx]
    memo[i]=e+(max(go(j) for j in nxt) if nxt else 0); return memo[i]
  i=idx[(x,r['obs.mapY']+1)]
  return go(i), rt[i]
def unit(d):
  seed=os.path.basename(d); games={}
  for f in os.listdir(d):
    if f.endswith('.jsonl.gz') and not f.endswith('.ctm.jsonl.gz'):
      rows=[json.loads(l) for l in gzip.open(os.path.join(d,f))]
      games[f.split('-')[0]]=([x for x in rows if x['type']=='state'],rows[-1])
  out=[]
  for a,b in itertools.combinations(sorted(games),2):
    sa,sb=games[a][0],games[b][0]; k=0
    while k<min(len(sa),len(sb)) and sa[k]['record']==sb[k]['record']: k+=1
    if k==min(len(sa),len(sb)) or k==0: continue
    root=sa[k-1]
    if root['screen']!=5 or root['act']>3: continue
    r=root['record']; cy=r['obs.mapY']+1
    # chosen x = first later state with mapY==cy
    def chosen(ss):
      for s in ss[k:k+6]:
        if s['act']==root['act'] and s['record']['obs.mapY']==cy: return s['record']['obs.mapX']
    xa,xb=chosen(sa),chosen(sb)
    if xa is None or xb is None or xa==xb: continue
    ea,ra=child_stats(r,xa); eb,rb=child_stats(r,xb)
    fo=r['obs.fixed_observation']
    out.append(dict(seed=seed,a=a,b=b,act=root['act'],row=cy,hp=fo[0],maxhp=fo[1],ea=ea,eb=eb,ra=ra,rb=rb,
      ya=int(games[a][1]['heartKilled']),yb=int(games[b][1]['heartKilled']),a4a=int(games[a][1]['finalAct']>=4),a4b=int(games[b][1]['finalAct']>=4)))
  return out
if __name__=='__main__':
  res=[]
  for ds in sys.argv[1:]:
    root=os.path.join(os.environ.get('ELITE_DIR', '.'), f'u{ds}/out/units')
    dirs=[os.path.join(root,s) for s in sorted(os.listdir(root)) if s.isdigit()]
    with Pool(4) as p:
      for o in p.imap(unit,dirs,chunksize=8):
        for x in o: x['ds']=ds; res.append(x)
  pickle.dump(res,open(os.path.join(os.environ.get('ELITE_DIR', '.'), 'divpairs.pkl'),'wb'))
  print(len(res))
