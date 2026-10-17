#!/usr/bin/env python3
"""Native gold closure enriched with remaining eligible non-HoG kills."""
from functools import lru_cache
import itertools
from tools import combat_transition_gold as g


@lru_cache(maxsize=8192)
def profiles(gold,name,ascension,mode,escaped=False):
    # Validate against the existing native gold domain before enrichment.
    g.native_posts(gold,name,ascension,mode)
    cap=g.CAPS.get(name,1);payouts=tuple(v for bit,v in ((1,20),(2,25)) if mode&bit)
    counts=(0,1) if name=='EXORDIUM_THUGS' else ((2,) if name=='TWO_THIEVES' else (int(name=='LOOTER'),))
    amount=20 if ascension>=17 else 15;result=set()
    for thieves in counts:
        if not thieves:
            budget=max(0,cap-1) if escaped else cap
            for kills,gain in g._gain_sums(budget,payouts):
                if gold+gain<=32767:result.add((gold+gain,0,kills,budget-kills))
            continue
        other_cap=cap-thieves
        states={(gold,(0,)*thieves,('A',)*thieves,0,0)}
        for turn in range(1,7):
            player=set()
            for current,stolen,status,others,hogs in states:
                options=[tuple([('keep',0),('O',0)]+[('H',p) for p in payouts]) if s not in ('O','H','E') else (('keep',0),) for s in status]
                for choices in itertools.product(*options):
                    updated=tuple(s if change=='keep' else change for s,(change,_) in zip(status,choices))
                    thief_hogs=sum(change=='H' for change,_ in choices)
                    for added,gain in g._gain_sums(other_cap-others,payouts):
                        purse=current+sum(p for _,p in choices)+gain
                        if purse<=32767:player.add((purse,stolen,updated,others+added,hogs+thief_hogs+added))
            states=set()
            for current,stolen,status,others,hogs in player:
                if escaped:
                    # RAW exit checks next escape intent, not actual death:
                    # active A/L and killed O/H contribute stolenGold; B has
                    # already rolled escape intent and E has escaped. Smoke
                    # continuation skips the resulting reward regardless.
                    alive_thief=any(s in ('A','L','B') for s in status)
                    possible_other_alive=other_cap-others>0
                    if alive_thief or possible_other_alive:
                        ordinary=other_cap-others+status.count('O')-int(not alive_thief)
                        result.add((current,sum(x for x,s in zip(stolen,status) if s in ('A','L','O','H')),hogs,ordinary))
                elif all(s in ('O','H','E') for s in status):
                    result.add((current,sum(x for x,s in zip(stolen,status) if s in ('O','H')),hogs,other_cap-others+status.count('O')))
                for lunges in itertools.product(*[(False,True) if turn==3 and s=='A' else (False,) for s in status]):
                    purse=current;taken=list(stolen);updated=list(status)
                    for i,s in enumerate(status):
                        if (turn in (1,2) and s=='A') or (turn==3 and s=='A' and lunges[i]):
                            paid=min(purse,amount);purse-=paid;taken[i]+=paid
                        if turn==3 and s=='A':updated[i]='L' if lunges[i] else 'B'
                        elif turn==4 and s=='L':updated[i]='B'
                        elif turn in (4,5) and s=='B':updated[i]='E'
                    states.add((purse,tuple(taken),tuple(updated),others,hogs))
    if not escaped and {p[:2] for p in result}!=set(g.native_posts(gold,name,ascension,mode)):
        raise ValueError('proc enrichment changed native gold closure')
    return tuple(sorted(result))


def dagger_minimum_procs(pre,pi,mask,deltas,consumed_potions=None,escaped=False):
    mode,features=g.mechanics(pi,pre,int(mask),consumed_potions);upgrade=bool(features[g.MECHANICAL_FIELDS.index('upgradeRoute')])
    cap=g.CAPS.get(g.encounter_name(pi['globals']['encounter']),1)
    if escaped:cap=max(0,cap-1)
    daggers=[c for c in pre['deck'] if c['id']==g.b._CARD_IDS['RITUAL_DAGGER']]
    if len(deltas)!=len(daggers):raise ValueError('Dagger identity mismatch')
    minimum=0
    for card,delta in zip(daggers,deltas):
        payouts=(5,) if card['upgraded'] else ((3,5) if upgrade else (3,))
        choices=[count for count,gain in g._gain_sums(cap,payouts) if gain==delta]
        if not choices:raise ValueError('non-native Dagger increment')
        minimum+=min(choices)
    return minimum


def joint_gold_posts(pre,pi,mask,dagger_deltas,consumed_potions=None,escaped=False):
    mode,_=g.mechanics(pi,pre,int(mask),consumed_potions);name=g.encounter_name(pi['globals']['encounter'])
    minimum=dagger_minimum_procs(pre,pi,mask,dagger_deltas,consumed_potions,escaped)
    return tuple(sorted({p[:2] for p in profiles(pre['gold'],name,pi['globals']['ascension'],mode,escaped) if p[3]>=minimum}))
