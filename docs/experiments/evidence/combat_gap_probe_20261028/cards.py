# usage: cards.py UNITS_DIR RUNS_DIR (expert_runs.tar extracted)
# per-fight gap (bot mean - expert) vs approximate deck contents (cards acquired before the fight floor)
import glob,json,statistics as st,collections,sys,random
KEY=['Whirlwind','Rage','Double Tap','Barricade','Entrench','Demon Form','Limit Break','Corruption','Feel No Pain','Dark Embrace',
     'Body Slam','Impervious','Offering','Shockwave','Disarm','Flame Barrier','Reaper','Feed','Heavy Blade','Spot Weakness','Inflame',
     'Metallicize','Juggernaut','Fiend Fire','Immolate','Pommel Strike','Shrug It Off','Battle Trance','Uppercut','Carnage','Hemokinesis','Bludgeon','Sword Boomerang','Thunderclap','Clothesline','Headbutt','True Grit','Second Wind','Sentinel','Burning Pact','Power Through','Ghostly Armor','Flex','Armaments','Seeing Red','Bloodletting','Exhume','Havoc','Infernal Blade','Dual Wield','Perfected Strike','Searing Blow','Blood for Blood','Evolve','Fire Breathing','Rupture','Combust','Brutality','Berserk','Intimidate','Dropkick','Reckless Charge','Sever Soul','Wild Strike','Clash','Iron Wave','Twin Strike','Anger','Cleave','Warcry','Rampage','Bash']
rows=[]
for p in glob.glob(sys.argv[1]+'/**/*.fights.json',recursive=True):
    x=json.load(open(p)); run=json.load(open(sys.argv[2]+'/'+x['runFile']))
    acq=collections.defaultdict(list)
    for c in run['card_choices']:
        if c['picked'] not in ('SKIP','Singing Bowl'): acq[c['picked'].split('+')[0]].append(c['floor'])
    for it,fl in zip(run['items_purchased'],run['item_purchase_floors']): acq[it.split('+')[0]].append(fl)
    for f in x['fights']:
        e=f['expert']; reps=[r for r in f['replicates'] if r['valid']]
        if not reps or e['exitHp'] is None or f['loggedFightsOnFloor']>1 or f['room'] not in 'EB': continue
        if f['act']==3 and f['floor']==51: continue
        el=f['hp']-(0 if e['died'] else e['exitHp'])
        bl=st.mean(f['hp']-(r['exitHp'] if r['won'] else 0) for r in reps)
        have={k for k in KEY if any(fl<f['floor'] for fl in acq.get(k,[]))}
        rows.append(dict(run=x['runFile'],d=bl-el,act=f['act'],room=f['room'],have=have))
print('fights',len(rows), 'mean gap',round(st.mean(r['d'] for r in rows),2))
# within act/room demeaned gap, compare have vs not
mu=collections.defaultdict(list)
for r in rows: mu[(r['act'],r['room'])].append(r['d'])
mu={k:st.mean(v) for k,v in mu.items()}
for r in rows: r['z']=r['d']-mu[(r['act'],r['room'])]
out=[]
for k in KEY:
    a=[r['z'] for r in rows if k in r['have']]; b=[r['z'] for r in rows if k not in r['have']]
    if len(a)<40: continue
    # run-cluster bootstrap of difference
    g=collections.defaultdict(list)
    for r in rows: g[r['run']].append(r)
    G=list(g.values()); rng=random.Random(1); ds=[]
    for _ in range(1000):
        s=[r for _ in G for r in rng.choice(G)]
        A=[r['z'] for r in s if k in r['have']]; B=[r['z'] for r in s if k not in r['have']]
        if A and B: ds.append(st.mean(A)-st.mean(B))
    ds.sort()
    out.append((st.mean(a)-st.mean(b),k,len(a),ds[25],ds[-25]))
for d,k,n,lo,hi in sorted(out,reverse=True): print(f'{k:16s} n={n:4d} {d:+5.2f} [{lo:+.2f},{hi:+.2f}]')
