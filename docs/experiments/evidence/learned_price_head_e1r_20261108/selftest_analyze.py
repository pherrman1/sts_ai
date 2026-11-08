#!/usr/bin/env python3
"""Synthetic check of analyze.py: games with the engine's potion-drop rule (chance 40 + c, c += 10 without a drop and
-= 10 with one, reset per act; rolls after normal/elite fights, the act 1-2 boss and act 4's elite) and a known value
V per potion obtained plus W extra for a Fairy. analyze.py must recover V from the boss rolls and W from the type
draw, show the attenuated mid-act coefficient, and say UNRESOLVED when V = W = 0.
usage: selftest_analyze.py [GAMES]"""
import importlib.util, os, sys
import numpy as np

spec = importlib.util.spec_from_file_location('e1r', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'analyze.py'))
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


def synth(n, V, W, qF, seed):
    rng = np.random.default_rng(seed)
    games = {}
    for g in range(n):
        rolls, fi, potions, fairies = [], 0, 0, 0
        last_act = 4 if rng.random() < 0.4 else int(rng.integers(1, 4))
        for act in range(1, last_act + 1):
            c = 0
            k = int(rng.integers(4, 10)) if act < 4 else 0
            rooms = ['NORMAL'] * k + (['BOSS'] if act < 3 else []) + (['ELITE'] if act == 4 else [])
            for room in rooms:
                chance = min(100, max(0, 40 + c))
                dropped = bool(rng.integers(0, 100) < chance)
                c += -10 if dropped else 10
                x = {'fightIndex': fi, 'act': act, 'floor': fi, 'room': room, 'chance': chance, 'dropped': dropped,
                     'potionCount': int(rng.integers(0, 3)), 'potionCapacity': 2, 'sozu': False}
                if dropped:
                    t = 'FAIRY_POTION' if rng.random() < qF else ['BLOCK_POTION', 'FIRE_POTION', 'SWIFT_POTION'][int(rng.integers(0, 3))]
                    x['potion'] = t
                    potions += 1
                    fairies += t == 'FAIRY_POTION'
                rolls.append(x)
                fi += 1
        p = 0.25 + V * (potions - 8) + W * fairies + 0.04 * (last_act - 2.5)
        games[1000 + g] = {'seed': 1000 + g, 'heartKill': bool(rng.random() < min(0.98, max(0.02, p))),
                           'rewards': {'rolls': rolls, 'inconsistent': 0}}
    return games


def main(n):
    games = synth(n, V=0.03, W=0.10, qF=0.06, seed=20261108)
    r = A.analyse(games)
    b, sb = r['primary']['boss_pp']
    f, sf = r['primary']['fairy_minus_other_pp']
    k6, sk6 = r['mid_by_later_rolls']['u_mid_k6+']
    print('signal: boss %.2f +- %.2f pp (true 3.00), fairy-other %.2f +- %.2f (true 10.00), mid 6+ later %.2f +- %.2f, %s'
          % (b, sb, f, sf, k6, sk6, r['decision']))
    assert abs(b - 3.0) < 3 * sb, 'boss level not recovered'
    assert abs(f - 10.0) < 3 * sf, 'Fairy contrast not recovered'
    assert k6 < b - 2 * sk6, 'mid-act coefficient not attenuated'
    assert r['decision'] == 'USABLE', r['decision']
    null = A.analyse(synth(n, V=0.0, W=0.0, qF=0.06, seed=20261109))
    print('null: boss %.2f +- %.2f, fairy %.2f +- %.2f, %s' % (*null['primary']['boss_pp'],
                                                            *null['primary']['fairy_minus_other_pp'], null['decision']))
    assert null['decision'] in ('UNRESOLVED', 'PARTIAL'), null['decision']
    print('selftest_analyze: passed')


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20000)
