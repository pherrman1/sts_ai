import sys; sys.path.insert(0, sys.argv[0].rsplit('/',1)[0]); from common import *
G=load(*sys.argv[1:])
inc=[k for k,v in RELIC.items() if v=="INCENSE_BURNER"][0]
R=collections.defaultdict(list)
for g in G:
    fs=g['fights']; ss=[f for f in fs if ENC[f['enc']]=='SHIELD_AND_SPEAR']; h=[f for f in fs if ENC[f['enc']]=='THE_HEART']
    if not ss: continue
    s=ss[0]
    R['ss_entry_pots'].append(len(s['pots'])); R['ss_used'].append(len(s['pots'])-len(s['postpots'])); R['ss_hploss'].append(s['hp']-s['post'])
    R['ss_cap'].append(s['cap'])
    if h:
        hh=h[0]; d=hh['post']<=0
        R['h_died' if d else 'h_surv'].append((hh['hp']/hh['maxhp'], len(hh['pots']), s['hp']-s['post'], len(s['pots'])-len(s['postpots']), inc in hh['relics'], len(hh['deck'])))
for k in ('ss_entry_pots','ss_used','ss_hploss','ss_cap'): print(k, np.mean(R[k]))
for k in ('h_died','h_surv'):
    a=np.array(R[k],float); print(k, len(a), 'entryHP%',a[:,0].mean(),'pots',a[:,1].mean(),'S&S hp loss',a[:,2].mean(),'S&S pots used',a[:,3].mean(),'incense',a[:,4].mean(),'deck',a[:,5].mean())
# share of potion slots full at S&S entry, and potions lost when full? skip
