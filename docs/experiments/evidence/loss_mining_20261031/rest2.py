import sys; sys.path.insert(0, sys.argv[0].rsplit('/',1)[0]); from common import *
G=load(*sys.argv[1:])
allc=collections.Counter()
for g in G:
    for r in rests(g): allc[(r['act'],r['c'])]+=1
print('campfire choices by act:', sorted(allc.items()))
tab=collections.defaultdict(collections.Counter)
for g in G:
    R=rests(g)
    for fi in g['fights']:
        if not isboss(fi) or ENC[fi['enc']]=='SHIELD_AND_SPEAR' or ENC[fi['enc']]=='THE_HEART': continue
        prev=[r for r in R if fi['floor']-2<=r['floor']<fi['floor']]
        if not prev: continue
        r=prev[-1]; key=(fi['act'], hpb(r['hp']/r['maxhp']), r['c'])
        tab[key]['n']+=1; tab[key]['d']+= fi['post']<=0; tab[key]['entry']+=fi['hp']/fi['maxhp']
for k in sorted(tab):
    v=tab[k]
    if v['n']>=5: print(f"act{k[0]} boss  campfireHP {k[1]:6s} {k[2]:7s} n={v['n']:5d} death={v['d']/v['n']*100:5.1f}% entryHP={v['entry']/v['n']*100:4.0f}%")
