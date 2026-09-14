#!/usr/bin/env python3
"""Native combat-limited Brew generation from an explicitly supplied RNG origin.

This module does not choose that origin. Using historical potionRng is exact
known-RNG replay; an independent hypothetical origin is a different contract.
"""
import math
import re
from pathlib import Path
from tools import combat_transition_rng_audit as rng
from tools import combat_transition_surrogate as base


def native_pool():
    header=Path(__file__).resolve().parents[1]/'include/constants/Potions.h'
    text=header.read_text()
    rarity=re.findall(r'PotionRarity::([A-Z_]+)',re.search(r'potionRarities\[\]\s*=\s*\{(.*?)\};',text,re.S).group(1))
    names=re.findall(r'Potion::([A-Z_]+)',re.search(r'potionPool\[4\]\[33\]\s*\{\s*\{(.*?)\}',text,re.S).group(1))
    pool=tuple(base._POTION_IDS[n] for n in names)
    if len(pool)!=33 or len(set(pool))!=33:raise ValueError('native Ironclad pool changed')
    return pool,rarity


POOL,RARITY=native_pool()
FRUIT=base._POTION_IDS['FRUIT_JUICE']
RARITY_MASS={'COMMON':.65,'UNCOMMON':.25,'RARE':.10}
PROBABILITY={p:RARITY_MASS[RARITY[p]]/sum(RARITY[q]==RARITY[p] and q!=FRUIT for q in POOL) for p in POOL if p!=FRUIT}
if not math.isclose(sum(PROBABILITY.values()),1.,abs_tol=1e-12):raise ValueError('native potion law does not normalize')


def draw_native(state):
    def bounded(bound):
        state['counter']+=1
        return rng.bounded_long(state,bound)
    roll=bounded(100)
    rarity='COMMON' if roll<65 else ('UNCOMMON' if roll<90 else 'RARE')
    # Game::returnRandomPotion(limited=true) discards this first candidate.
    bounded(33)
    while True:
        candidate=POOL[bounded(33)]
        if RARITY[candidate]==rarity and candidate!=FRUIT:return candidate


def generate(origin,capacity):
    if not 1<=capacity<=5:raise ValueError('invalid native potion capacity')
    state=dict(origin)
    generated=tuple(draw_native(state) for _ in range(capacity))
    return generated,state


def obtain(inventory,generated,sozu=False,capacity=None):
    result=list(inventory)
    capacity=len(result) if capacity is None else capacity
    if not 1<=capacity<=len(result):raise ValueError('invalid native capacity')
    if not sozu:
        for potion in generated:
            try:slot=result.index(base._POTION_IDS['EMPTY_POTION_SLOT'],0,capacity)
            except ValueError:continue
            result[slot]=potion
    return result
