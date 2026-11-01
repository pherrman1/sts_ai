import sys; sys.path.insert(0, sys.argv[0].rsplit('/',1)[0]); from common import *
G=load(*sys.argv[1:]); N=len(G)
off=collections.Counter(); taken=collections.Counter(); full=collections.Counter(); fullnotaken=collections.Counter()
used=collections.Counter(); runs_act=collections.Counter()
for g in G:
    st=g['states']; fs=g['fights']
    caps={f['floor']:f['cap'] for f in fs}
    seen=set()
    for k,s in enumerate(st):
        if s['screen']!=2 or not s['pots'] is not None: continue
    # potion offers: first reward state per floor with potions_offered
    for k,s in enumerate(st):
        if s['screen']!=2 or not s['potions_offered'] or s['floor'] in seen: continue
        seen.add(s['floor'])
        cap=s['cap']
        nx=next((t for t in st[k+1:] if t['floor']>s['floor']), None)
        if nx is None: continue
        a=s['act']; off[a]+=1
        isfull=len(s['pots'])>=cap
        full[a]+=isfull
        got = len(nx['pots'])>len(s['pots']) or (isfull and sorted(nx['pots'])!=sorted(s['pots']))
        taken[a]+=got
        if isfull and not got: fullnotaken[a]+=1
    for f in fs:
        if f['room']=='BOSS' or ENC[f['enc']] in ('THE_HEART','SHIELD_AND_SPEAR'): continue
        used[(f['act'],f['room'])]+=max(len(f['pots'])-len(f['postpots']),0)
    for a in set(f['act'] for f in fs): runs_act[a]+=1
for a in (1,2,3):
    print(f'act{a}: runs={runs_act[a]} potion offers/run={off[a]/runs_act[a]:.2f} taken={taken[a]/max(off[a],1)*100:.0f}% belt full at offer={full[a]/max(off[a],1)*100:.0f}% full&not taken/run={fullnotaken[a]/runs_act[a]:.2f} | used per run: elite {used[(a,"ELITE")]/runs_act[a]:.2f} hallway {used[(a,"NORMAL")]/runs_act[a]:.2f} event {used[(a,"OTHER")]/runs_act[a]:.2f}')
