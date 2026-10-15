"""§425 OOC MCTS picks (prod, rollout3) scored on Gold2 labels, by decision type. Unowned searches fall back to the heuristic (live)."""
import sys, json, gzip, collections, numpy as np, pandas as pd
sys.path.insert(0,'/root/gold/ana'); from gold_common import *
EV='/home/user/sts_ai/docs/experiments/evidence/ooc_mcts_a20_gold_20261011/'
arm=sys.argv[1]
df=pd.read_csv(G+'gold2.csv',usecols=['seed','decIdx','screen','action','actionType','c1','c2','c3','cand1','cand2','cand3','chosen','act','floor','labelFloor'])
df=df[df.labelFloor.notna()]
S=collections.defaultdict(list)
for l in gzip.open(EV+f'searches-{arm}.jsonl.gz','rt'):
    r=json.loads(l); S[(r['seed'],r['decIdx'])].append(r)
rows=[]; skipped=collections.Counter()
for (s,di),x in df.groupby(['seed','decIdx']):
    if len(x)<2 or not (x.chosen==1).any(): continue
    if (s,di) not in S: skipped['no search']+=1; continue
    srs=S[(s,di)]
    gold_bits=set(x.action.astype(int))
    if any(not set(r['actionBits'])>=gold_bits for r in srs): skipped['state mismatch (option set differs)']+=1; continue
    lab=dict(zip(x.action.astype(int),x.labelFloor)); best=max(lab.values())
    xr={int(b):r for b,r in zip(x.action,x.itertuples())}
    hb=int(x.action[x.chosen==1].iloc[0]); scr=SCR.get(int(x.screen.iloc[0]),'?')
    picks=[]; owned=0
    for r in srs:
        b=r['selectedBits'] if r['selected'] and not r['aborted'] else None
        if b is not None and b in lab: picks.append(b); owned+=1
        else: picks.append(hb)
    gain=np.mean([lab[b]-lab[hb] for b in picks]); reg=np.mean([best-lab[b] for b in picks])
    modal=collections.Counter(picks).most_common(1)[0][0]
    dh,dm=desc(xr[hb]),desc(xr[modal])
    rows.append(dict(seed=s,dec=di,act=int(x.act.iloc[0]),floor=int(x.floor.iloc[0]),screen=scr,heur=dh,v4=dm,heur_c=coarse(scr,dh),v4_c=coarse(scr,dm),
        best=desc(xr[max(lab,key=lab.get)]),reg_h=best-lab[hb],reg_v=reg,gain=gain,agree=int(all(b==hb for b in picks)),owned=owned/len(srs)))
R=pd.DataFrame(rows); R.to_csv(G+f'ana/decisions_mcts_{arm}.csv',index=False)
rng=np.random.default_rng(20261012)
def ci(a):
    a=np.asarray(a)
    if len(a)<2: return f'{a.mean():+.2f}'
    m=a[rng.integers(0,len(a),(5000,len(a)))].mean(1); return f'{a.mean():+.2f} [{np.percentile(m,2.5):+.2f},{np.percentile(m,97.5):+.2f}]'
print(f'MCTS {arm}: {len(R)} decisions (skipped {dict(skipped)}); owned {R.owned.mean():.2f}; regret heur {R.reg_h.mean():.2f} MCTS {R.reg_v.mean():.2f}; MCTS-minus-heur {ci(R.gain)}; all 4 searches = heuristic {R.agree.mean():.2f}')
print('\n## By screen (gain = MCTS label minus heuristic label, floors, averaged over 4 searches; + = MCTS better)')
print(f"{'screen':11} {'n':>4} {'owned':>5} {'agree':>5} {'regH':>5} {'regM':>5} {'gain/dec':>22} {'sum':>6} {'better':>6} {'worse':>6}")
for s,x in R.groupby('screen'):
    print(f"{s:11} {len(x):4} {x.owned.mean():5.2f} {x.agree.mean():5.2f} {x.reg_h.mean():5.2f} {x.reg_v.mean():5.2f} {ci(x.gain):>22} {x.gain.sum():6.1f} {(x.gain>0).sum():6} {(x.gain<0).sum():6}")
print('\n## By act')
for a,x in R.groupby('act'): print(f"act {a}: n {len(x)} gain/dec {ci(x.gain)} sum {x.gain.sum():.1f}")
D=R[R.agree==0]
print(f'\n## Disagreements ({len(D)}): heuristic -> MCTS modal pick (coarse), sorted by total gain')
g=D.groupby(['screen','heur_c','v4_c']).gain.agg(['count','mean','sum']).reset_index().sort_values('sum')
for _,r in g.iterrows():
    if r['count']>=3 or abs(r['sum'])>=8: print(f"  {r.screen:10} {r.heur_c[:28]:28} -> {r.v4_c[:28]:28} n={r['count']:3} mean {r['mean']:+.2f} sum {r['sum']:+.1f}")
print('\n## Worst 10'); [print(f"  {r.seed} f{r.floor:2} {r.screen:9} heur '{r.heur}' -> MCTS '{r.v4}'  {r.gain:+.2f} (best '{r.best}')") for _,r in D.sort_values('gain').head(10).iterrows()]
print('\n## Best 10'); [print(f"  {r.seed} f{r.floor:2} {r.screen:9} heur '{r.heur}' -> MCTS '{r.v4}'  {r.gain:+.2f} (best '{r.best}')") for _,r in D.sort_values('gain',ascending=False).head(10).iterrows()]
