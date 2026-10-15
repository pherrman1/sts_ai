"""Public heart1 records -> typed tokens; no seed/RNG/target inputs.

Inspired by heart1/student-C observations, not a parity port of their trained network.
Map tokens retain room, coordinates, outgoing paths and burning-elite identity.
"""
import math
import numpy as np


def encode_record(r):
    for keys in [('obs.deck.cards','obs.deck.upgrades'),('obs.relics.relics','obs.relics.relic_counters'),
                 ('cards_offered.cards','cards_offered.upgrades'),
                 ('obs.map.xs','obs.map.ys','obs.map.roomTypes','obs.map.pathXs')]:
        if len({len(r[k]) for k in keys})!=1: raise ValueError('parallel record lengths differ')
    if any(len(edges)!=3 for edges in r['obs.map.pathXs']): raise ValueError('map edge width')
    if not isinstance(r['screen_state'],int) or not 0<=r['screen_state']<10:raise ValueError('screen vocabulary')
    fo=r['obs.fixed_observation']
    if len(fo)!=10: raise ValueError('fixed observation width')
    dense=[float(v)/s for v,s in zip(fo,[200,200,1800,60,4,5,20,1,1,1])]
    dense += [r['obs.mapX']/7,r['obs.mapY']/15,r['obs.map.burningEliteX']/7,r['obs.map.burningEliteY']/15]
    dense += [float(r['screen_state']==i) for i in range(10)]
    dense += [float(r['select_screen_type']==i) for i in range(16)]
    dense += [float('leaf.matchSlots' in r),float(r.get('leaf.matchAttempts',0))/5]
    if not all(math.isfinite(v) for v in dense): raise ValueError("nonfinite dense input")
    tokens=[]
    def add(kind,entity,*attrs):
        if not 0<=entity<1536: raise ValueError('entity vocabulary overflow')
        a=list(attrs)+[0.]*(8-len(attrs))
        if len(a)!=8 or not all(math.isfinite(float(x)) for x in a): raise ValueError('bad token numeric attributes')
        if kind in (1,4) and not 0<=entity<512: raise ValueError('card vocabulary overflow')
        if kind in (2,5) and not 512<=entity<768: raise ValueError('relic vocabulary overflow')
        if kind in (3,6) and not 768<=entity<832: raise ValueError('potion vocabulary overflow')
        a=[max(-8.,min(8.,float(v))) for v in a]
        tokens.append((kind,entity,a))
    for c,u in zip(r['obs.deck.cards'],r['obs.deck.upgrades']): add(1,int(c),u/10)
    for c,n in zip(r['obs.relics.relics'],r['obs.relics.relic_counters']): add(2,512+int(c),n/100)
    for p in r['obs.potions']: add(3,768+int(p))
    for c,u in zip(r['cards_offered.cards'],r['cards_offered.upgrades']): add(4,int(c),u/10)
    for c in r['relics_offered']: add(5,512+int(c))
    for p in r['potions_offered']: add(6,768+int(p))
    for a in r['fixed_actions']:
        add(7,832+int(a['action']),a['gold']/1800,a['card']/512,a['relic']/256,a['info']/200)
    offered=set(r['paths_offered']); my=r['obs.mapY']
    for x,y,room,edges in zip(r['obs.map.xs'],r['obs.map.ys'],r['obs.map.roomTypes'],r['obs.map.pathXs']):
        if y<my: continue
        add(8,1088+int(room),x/7,y/15,*[e/7 for e in edges],
            float(x==r['obs.map.burningEliteX'] and y==r['obs.map.burningEliteY']),
            float(y==my+1 and x in offered),(y-my)/15)
    if r['screen_state']==9:
        encounter=r['leaf.publicBattleEncounter']
        if not isinstance(encounter,int) or not 1<=encounter<=63: raise ValueError('public encounter vocabulary')
        add(9,1280+encounter)
    elif 'leaf.publicBattleEncounter' in r: raise ValueError('encounter outside battle boundary')
    if 'leaf.matchSlots' in r:
        if r['screen_state']!=1 or not 1<=len(r['leaf.matchSlots'])<=12:raise ValueError('memory-game screen/width')
        if not 0<=r['leaf.matchAttempts']<=5: raise ValueError('memory-game attempts')
        seen_positions=set()
        for slot in r['leaf.matchSlots']:
            state=slot['state'];card=slot['card'];position=slot['position'];up=slot['upgrades']
            if state not in (-1,0,1,2) or not 0<=position<12 or position in seen_positions:
                raise ValueError('memory-game public slot state')
            seen_positions.add(position)
            if state==-1:
                if card!=-1 or up!=0:raise ValueError('unseen memory-game card leaked')
                entity=1535
            else:
                if not 0<=card<512:raise ValueError('memory-game card vocabulary')
                entity=card
            add(10,entity,position/12,state/3,up/10)
    if not tokens: raise ValueError('empty public record')
    if len(tokens)>384: raise ValueError('token resource bound exceeded')
    # Count baseline has the same public entities and typed attribute sums.
    features={f'dense.{i}':float(v) for i,v in enumerate(dense)}
    for kind,entity,attrs in tokens:
        k=f'token.{kind}.{entity}'
        features[k]=features.get(k,0)+1
        for j,v in enumerate(attrs): features[k+f'.attr{j}']=features.get(k+f'.attr{j}',0)+float(v)
    return features,tokens


def pack_tokens(rows):
    n=len(rows); width=max(len(r['tokens']) for r in rows)
    kinds=np.zeros((n,width),dtype=np.int64); entities=kinds.copy()
    attrs=np.zeros((n,width,8),dtype=np.float32)
    for i,r in enumerate(rows):
        for j,(kind,entity,a) in enumerate(r['tokens']):
            kinds[i,j]=kind; entities[i,j]=entity; attrs[i,j]=a
    return kinds,entities,attrs
