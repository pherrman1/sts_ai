import sys; sys.path.insert(0, sys.argv[0].rsplit('/',1)[0]); from common import *
G=load(*sys.argv[1:]); N=len(G)
c=collections.Counter(); lastfire=collections.Counter(); drop=[]
for g in G:
    fs=g['fights']
    if g['o']['kill'] or not fs or fs[-1]['post']>0: continue
    f=fs[-1]
    if f['room'] not in ('NORMAL','ELITE') or f['act']>2: continue
    if f['hp']/f['maxhp']>=0.5: continue
    c[(f['act'],f['room'])]+=1
    R=[r for r in rests(g) if r['floor']<f['floor'] and r['act']==f['act']]
    if R:
        r=R[-1]; lastfire[(r['c'], hpb(r['hp']/r['maxhp']), f['floor']-r['floor']<=3)]+=1
    else: lastfire['no campfire this act yet']+=1
    prev=[x for x in fs[:-1] if x['act']==f['act']]
    if prev: drop.append((prev[-1]['hp']-prev[-1]['post'], prev[-1]['room'], f['hp']))
print('low-HP (<50%) non-boss deaths acts 1-2:', {k:f'{v} ({v/N*100:.1f}%)' for k,v in c.items()})
print('last campfire in that act before death (choice, HP band, within 3 floors):')
for k,v in lastfire.most_common(): print('  ',k,v)
d=np.array([x[0] for x in drop]); print('HP lost in the fight before the fatal one: mean',d.mean(),'median',np.median(d), 'entry HP of fatal fight median', np.median([x[2] for x in drop]))
