"""Gold2 per-decision breakdown: heuristic (chosen) vs V4 Q argmax, by decision type."""
import re, sys, json, numpy as np, pandas as pd
REPO='/home/user/sts_ai'; G='/root/gold/'
def enum_strings(path, marker):
    s=open(path).read(); i=s.index(marker); j=s.index('};',i); return re.findall(r'"([^"]*)"',s[i:j])
CARDS=enum_strings(REPO+'/include/constants/Cards.h','cardEnumStrings[]')
RELICS=enum_strings(REPO+'/include/constants/Relics.h','relicEnumNames[]')
EVENTS=enum_strings(REPO+'/include/constants/Events.h','eventIdStrings[]')
POTS=enum_strings(REPO+'/include/constants/Potions.h','potionEnumNames') if 'potionEnumNames' in open(REPO+'/include/constants/Potions.h').read() else []
ROOMS=['SHOP','REST','EVENT','ELITE','MONSTER','TREASURE','BOSS','BOSS_TREASURE','NONE','INVALID']
REST=['REST','SMITH','RECALL','LIFT','TOKE','DIG','SKIP']
SCR={1:'EVENT',2:'REWARDS',3:'BOSS_RELIC',4:'UPGRADE',5:'MAP',6:'TREASURE',7:'REST',8:'SHOP'}
nm=lambda L,i: L[i] if 0<=i<len(L) else str(i)
def desc(r):
    s=SCR.get(r.screen,str(r.screen)); t=int(r.actionType); c1,c2,k1=int(r.c1),int(r.c2),int(r.cand1)
    if s=='REWARDS':
        if t==0: return 'skip card' if c2==5 else 'take '+nm(CARDS,k1)
        return ['card','gold','key','potion','relic','remove','skip'][t] if 0<=t<7 else str(t)
    if s=='SHOP':
        return {0:'buy card '+nm(CARDS,k1),3:'buy potion',4:'buy relic '+nm(RELICS,k1),5:'remove',6:'leave'}.get(t,str(t))
    if s=='MAP': return nm(ROOMS,int(r.cand3))
    if s=='REST': return nm(REST,c1)
    if s=='EVENT': return f'{nm(EVENTS,k1)} opt{c1}'
    if s=='BOSS_RELIC': return 'skip' if k1<0 else nm(RELICS,k1)
    if s=='UPGRADE': return nm(CARDS,k1)
    if s=='TREASURE': return 'open' if c1==0 else f'opt{c1}'
    return f'{t}/{c1}'
def coarse(s, d):
    if s=='REWARDS': return 'skip card' if d=='skip card' else ('take card' if d.startswith('take') else d)
    if s=='SHOP': return d.split(' ')[0]+(' '+d.split(' ')[1] if d.startswith('buy') else '')
    if s=='EVENT': return d.split(' opt')[0]
    if s in('UPGRADE','BOSS_RELIC'): return 'pick'
    return d
name=sys.argv[1] if len(sys.argv)>1 else 'v4final'
df=pd.read_csv(G+'gold2.csv',usecols=['seed','decIdx','screen','action','actionType','c1','c2','c3','cand1','cand2','cand3','chosen','act','floor','labelFloor'])
q=np.load(G+f'q_{name}.npy'); df['q']=np.nan; df.loc[q[0].astype(np.int64),'q']=q[1]
df=df[df.labelFloor.notna()]
rows=[]
for (s,di),x in df.groupby(['seed','decIdx']):
    if len(x)<2 or not (x.chosen==1).any() or x.q.isna().any(): continue
    lab=x.labelFloor.to_numpy(); best=lab.max()
    h=int(np.flatnonzero(x.chosen.to_numpy()==1)[0]); v=int(np.argmax(x.q.to_numpy()))
    qs=np.sort(x.q.to_numpy())[::-1]
    xr=x.iloc
    scr=SCR.get(int(xr[0].screen),str(xr[0].screen))
    dh,dv=desc(xr[h]),desc(xr[v])
    rows.append(dict(seed=s,dec=di,act=int(xr[0].act),floor=int(xr[0].floor),screen=scr,n=len(x),
        heur=dh,v4=dv,heur_c=coarse(scr,dh),v4_c=coarse(scr,dv),best=desc(xr[int(np.argmax(lab))]),
        reg_h=best-lab[h],reg_v=best-lab[v],gain=lab[v]-lab[h],agree=int(h==v),v4margin=qs[0]-qs[1],
        q_gap_vh=x.q.to_numpy()[v]-x.q.to_numpy()[h]))
R=pd.DataFrame(rows); R.to_csv(G+f'ana/decisions_{name}.csv',index=False)
rng=np.random.default_rng(20261012)
def ci(a):
    a=np.asarray(a); 
    if len(a)<2: return f'{a.mean():+.2f}'
    m=a[rng.integers(0,len(a),(5000,len(a)))].mean(1); return f'{a.mean():+.2f} [{np.percentile(m,2.5):+.2f},{np.percentile(m,97.5):+.2f}]'
print(f'model {name}: {len(R)} decisions; regret heur {R.reg_h.mean():.2f} V4 {R.reg_v.mean():.2f}; V4-minus-heur floors/decision {ci(R.gain)}; agree {R.agree.mean():.2f}')
print('\n## By screen (gain = V4 label minus heuristic label, floors; + means V4 better)')
print(f"{'screen':11} {'n':>4} {'agree':>5} {'regH':>5} {'regV':>5} {'gain/dec':>22} {'sum':>6} {'V4 better':>9} {'V4 worse':>8}")
for s,x in R.groupby('screen'):
    print(f"{s:11} {len(x):4} {x.agree.mean():5.2f} {x.reg_h.mean():5.2f} {x.reg_v.mean():5.2f} {ci(x.gain):>22} {x.gain.sum():6.1f} {(x.gain>0).sum():9} {(x.gain<0).sum():8}")
print('\n## By act'); 
for a,x in R.groupby('act'): print(f"act {a}: n {len(x)} gain/dec {ci(x.gain)} sum {x.gain.sum():.1f}")
D=R[R.agree==0]
print(f'\n## Disagreements ({len(D)}): heuristic choice -> V4 choice (coarse), sorted by total gain')
g=D.groupby(['screen','heur_c','v4_c']).gain.agg(['count','mean','sum']).reset_index().sort_values('sum')
for _,r in g.iterrows():
    if r['count']>=3 or abs(r['sum'])>=8: print(f"  {r.screen:10} {r.heur_c[:28]:28} -> {r.v4_c[:28]:28} n={r['count']:3} mean {r['mean']:+.2f} sum {r['sum']:+.1f}")
print('\n## Does V4 confidence (its own Q margin over the heuristic pick) predict a real gain? (disagreements only)')
D=D.assign(bin=pd.cut(D.q_gap_vh,[0,0.25,0.5,1,2,4,1e9]))
for b,x in D.groupby('bin',observed=True): print(f"  V4 Q(best)-Q(heur) in {b}: n {len(x):3} gain/dec {ci(x.gain)}")
print('\n## Worst 12 V4 overrides')
for _,r in D.sort_values('gain').head(12).iterrows(): print(f"  {r.seed} f{r.floor:2} {r.screen:9} heur '{r.heur}' -> V4 '{r.v4}'  {r.gain:+.2f} (best '{r.best}')")
print('\n## Best 12 V4 overrides')
for _,r in D.sort_values('gain',ascending=False).head(12).iterrows(): print(f"  {r.seed} f{r.floor:2} {r.screen:9} heur '{r.heur}' -> V4 '{r.v4}'  {r.gain:+.2f} (best '{r.best}')")
print('\n## Live-style gate on gold decisions: play V4 when its best-vs-second Q margin >= m, else heuristic')
for m in [0,0.25,0.5,1,2,4,8]:
    use=R.v4margin>=m; g=np.where(use,R.gain,0.0)
    print(f"  m={m:<4} V4 overrides {int((use&(R.agree==0)).sum()):3}  gain vs heuristic {ci(g)} floors/decision")
