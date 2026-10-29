# usage: pot.py UNITS_DIR -- §711 fights acts 1-2 E/B: gap by potions held/used and entry HP (descriptive)
import glob,json,statistics as st,collections,sys
rows=[]
for p in glob.glob(sys.argv[1]+'/**/*.fights.json',recursive=True):
    x=json.load(open(p))
    for f in x['fights']:
        e=f['expert']; reps=[r for r in f['replicates'] if r['valid']]
        if not reps or e['exitHp'] is None or f['loggedFightsOnFloor']>1 or f['room'] not in 'EB' or f['act']>2: continue
        el=f['hp']-(0 if e['died'] else e['exitHp'])
        for r in reps:
            rows.append(dict(act=f['act'],room=f['room'],enc=f['encounter'],held=len(f['potions']),eu=e['potionsUsed'] or 0,
              bu=len(r['potionsUsed']),bl=f['hp']-(r['exitHp'] if r['won'] else 0),el=el,hp=f['hp'],mx=f['maxHp'],won=r['won'],ed=e['died']))
def show(lbl,R):
    if not R: return
    print(f"{lbl:40s} n={len(R):5d} bl={st.mean(r['bl'] for r in R):5.1f} el={st.mean(r['el'] for r in R):5.1f} d={st.mean(r['bl']-r['el'] for r in R):+5.1f} bu={st.mean(r['bu'] for r in R):.2f} eu={st.mean(r['eu'] for r in R):.2f} bdeath={1-st.mean(r['won'] for r in R):.3f}")
for key in [('2','E'),('2','B'),('1','E'),('1','B')]:
    R=[r for r in rows if str(r['act'])==key[0] and r['room']==key[1]]
    print('==',key)
    show('all',R)
    show('held0',[r for r in R if r['held']==0])
    show('held>=1',[r for r in R if r['held']>=1])
    show('held>=1 & bot used 0',[r for r in R if r['held']>=1 and r['bu']==0])
    show('held>=1 & bot used >=1',[r for r in R if r['held']>=1 and r['bu']>=1])
    show('expert used0',[r for r in R if r['eu']==0])
    show('expert used>=1',[r for r in R if r['eu']>=1])
    for lo,hi in [(0,.5),(.5,.75),(.75,1.01)]:
        show(f'entry hp frac {lo}-{hi}',[r for r in R if lo<=r['hp']/r['mx']<hi])
print('== equal potion use (per copy) by encounter, acts1-2 E/B')
by=collections.defaultdict(list)
for r in rows:
    if r['bu']==r['eu']: by[(r['act'],r['room'],r['enc'])].append(r)
for k,R in sorted(by.items()):
    if len(R)>=60: show(f'{k}',R)
show('ALL equal use',[r for r in rows if r['bu']==r['eu']])
show('ALL equal use, 0 potions both',[r for r in rows if r['bu']==r['eu']==0])
