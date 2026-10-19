import json,csv,math,sys,numpy as np
rows=[json.loads(l) for l in open(sys.argv[1])]
ctm={(int(r['source_seed']),int(r['fight_idx'])):r for r in csv.DictReader(open(sys.argv[2])) if r['scored']=='1'}
def heal(h,maxhp,rel):
    if h<=0: return 0
    if 87 in rel and h<=maxhp//2: h=min(maxhp,h+12)
    if 86 in rel: h=min(maxhp,h+6)
    if 85 in rel: h=min(maxhp,h+12)
    return h
res={'ctm':[], 'sil':[], 'silraw':[]}; mism=0; seeds=[]
for r in rows:
    t,fs,be=r['transition'],r.get('firstSearch'),r.get('battleEnd')
    if t is None or not r['runValid'] or fs is None: continue
    if t['combatOutcome']!=1 or t['post']['smokeBombUsed']: continue
    c=ctm.get((r['sourceSeed'],r['fightIdx']))
    if c is None or fs['skipped'] or fs['inheritedVisits']!=0: continue
    rel={x['id'] for x in t['pre']['relics']}
    mx=t['post']['maxHp']
    if heal(be['hp'],mx,rel)!=t['post']['curHp']: mism+=1
    L=fs['root']; cnt=np.zeros(mx+1)
    for h,k in enumerate(L['hpCounts']):
        if h>=1: cnt[heal(min(h,mx),mx,rel)]+=k
    if cnt.sum()==0: continue
    sm=cnt[1:]+0.5; sm/=sm.sum()
    y=t['post']['curHp']
    mean=(cnt*np.arange(mx+1)).sum()/cnt.sum()
    res['sil'].append((mean-y, math.log(sm[y-1])))
    res['ctm'].append((float(c['expected_win_hp'])-y, float(c['log_p_post_hp'])))
    seeds.append(r['sourceSeed'])
print('heal-model mismatches',mism,'n',len(seeds))
for k in ('ctm','sil'):
    e=np.array([x[0] for x in res[k]]); l=np.array([x[1] for x in res[k]])
    print(k,'bias(pred-real HP)',e.mean().round(2),'rmse',np.sqrt((e**2).mean()).round(2),'debiased rmse',e.std().round(2),'logscore',l.mean().round(3))
d=np.array([s[1]-c[1] for s,c in zip(res['sil'],res['ctm'])]); seeds=np.array(seeds)
u,inv=np.unique(seeds,return_inverse=True); S=np.bincount(inv,d); N=np.bincount(inv)
rng=np.random.default_rng(0); bs=[]
for _ in range(2000):
    i=rng.integers(0,len(u),len(u)); bs.append(S[i].sum()/N[i].sum())
print('logscore delta sil-ctm',d.mean().round(3),np.percentile(bs,[2.5,97.5]).round(3))
