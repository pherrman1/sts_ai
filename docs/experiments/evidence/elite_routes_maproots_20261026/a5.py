import os
import pickle,collections,statistics as st
d=pickle.load(open(os.path.join(os.environ.get('ELITE_DIR', '.'), 'elite683.pkl'),'rb'))
# map roots where kids differ in emax (elite-heavier route available) 
for arm in ('MAP','D','OFF'):
  print('==',arm)
  T=collections.defaultdict(lambda:[0,0,[],[]])
  N=collections.Counter()
  for (s,a),g in d.items():
    if a!=arm: continue
    for r in g['roots']:
      k=r['kids']; N[r['act']]+=1
      if len(k)<2: continue
      em=max(c['emax'] for c in k)
      if min(c['emax'] for c in k)==em: continue
      sel=[c for c in k if c['x']==r['sel']]
      if not sel: continue
      hpb=min(int(r['hp']/r['maxhp']*10),9)//2*2
      key=(r['act'],hpb)
      T[key][0]+=1; T[key][1]+= sel[0]['emax']==em
      top=[c for c in k if c['emax']==em]; oth=[c for c in k if c['emax']<em]
      if True:
        if top[0]["prior"] is not None: T[key][2].append(max(c["prior"] for c in top))
        if all(c['q'] is not None for c in k) and r['searched']: T[key][3].append(max(c['q'] for c in top)-max(c['q'] for c in oth))
  print(' roots per act',dict(N))
  for key in sorted(T):
    n,h,p,q=T[key]
    print(f'  act {key[0]} hp {key[1]*10:2d}-{key[1]*10+19}%: roots w/ elite-heavier option {n:5d} take it {h/n:.2f}  prior(top) {st.mean(p) if p else float("nan"):.2f}  Q(top)-Q(other) {st.mean(q) if q else float("nan"):+.4f}')
