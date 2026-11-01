import sys; sys.path.insert(0, sys.argv[0].rsplit('/',1)[0]); from common import *
G=load(*sys.argv[1:]); N=len(G)
cat=collections.Counter(); grp=collections.Counter()
prevlow=collections.Counter()
for g in G:
    if g['o']['kill']: continue
    fs=g['fights']
    if not fs or fs[-1]['post']>0: cat['non-fight']+=1; continue
    f=fs[-1]; frac=f['hp']/f['maxhp']; p=len(f['pots'])
    e=ENC[f['enc']]
    stage = 'Heart' if e=='THE_HEART' else ('S&S' if e=='SHIELD_AND_SPEAR' else f"act{f['act']} {f['room'].lower()}")
    res = 'healthy (HP>=80%, >=1 potion)' if frac>=.8 and p>=1 else ('low HP (<50%)' if frac<.5 else ('mid HP, 0 potions' if p==0 else 'mid HP 50-80%'))
    cat[(stage,res)]+=1; grp[stage]+=1
    # for non-boss deaths: HP before previous fight
    if f['room'] in ('ELITE','NORMAL'):
        prevlow[(stage, hpb(frac))]+=1
print('deaths by stage x entry resource (share of all runs):')
for s in sorted(grp, key=lambda s:-grp[s]):
    parts=[f"{r}: {cat[(s,r)]/N*100:.1f}" for r in ('healthy (HP>=80%, >=1 potion)','mid HP 50-80%','mid HP, 0 potions','low HP (<50%)')]
    print(f'  {s:13s} {grp[s]/N*100:5.1f}% | '+' | '.join(parts))
tot=collections.Counter()
for key,v in cat.items():
    if isinstance(key,tuple): tot[key[1]]+=v
print('all deaths by resource:', {k:f'{v/N*100:.1f}%' for k,v in tot.items()})
print('non-boss death entry HP:', sorted(prevlow.items()))
