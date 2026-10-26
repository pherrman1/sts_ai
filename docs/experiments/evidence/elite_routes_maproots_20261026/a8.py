import os
import pickle,random,collections
P=pickle.load(open(os.path.join(os.environ.get('ELITE_DIR', '.'), 'divpairs.pkl'),'rb'))
def summ(L,lab):
  # orient: elite-heavier side = h
  v=[(p['ya']-p['yb'])*(1 if p['ea']>p['eb'] else -1) for p in L]
  w=[(p['a4a']-p['a4b'])*(1 if p['ea']>p['eb'] else -1) for p in L]
  if not v: print(lab,'n 0'); return
  rng=random.Random(3); bs=sorted(sum(rng.choice(v) for _ in v)/len(v) for _ in range(4000))
  bw=sorted(sum(rng.choice(w) for _ in w)/len(w) for _ in range(4000))
  print(f'{lab:38s} pairs {len(v):4d}  kill(elite-heavier - other) {sum(v)/len(v)*100:+.1f} pp [{bs[100]*100:+.1f},{bs[3900]*100:+.1f}]  act4 {sum(w)/len(w)*100:+.1f} [{bw[100]*100:+.1f},{bw[3900]*100:+.1f}]')
E=[p for p in P if p['ea']!=p['eb']]
print('map-root first divergences',len(P),'with different elite potential',len(E))
summ(E,'all')
for act in (1,2,3): summ([p for p in E if p['act']==act],f'act {act}')
for lo,hi in ((0,.4),(.4,.6),(.6,.8),(.8,1.01)): summ([p for p in E if lo<=p['hp']/p['maxhp']<hi],f'hp {lo:.0%}-{hi:.0%}')
summ([p for p in E if p['act']==1 and p['hp']/p['maxhp']>=.6],'act 1, hp>=60%')
