#!/usr/bin/env python3
"""Synthetic check of analyze.py: games with the engine's potion-drop rule (chance 40 + c, c += 10 without a drop and
-= 10 with one, reset per act; rolls after normal/elite fights, the act 1-2 boss and act 4's elite) and a known value
V per potion obtained plus W extra for a Fairy. The boss coefficient is the value of an average drop, V + W*qF
(qF = Fairy share of the drops), and the Fairy contrast is W. analyze.py must recover V + W*qF from the boss rolls
and W from the type draw, show the attenuated mid-act coefficient, and say UNRESOLVED when V = W = 0. It also checks the gates (G3 below
502 units -> INCOMPLETE, a G1 mismatch voids only the HP conversion) and the Sozu split: games that hold Sozu from act
2 on cannot take a dropped potion, so those boss drops are worth 0.
usage: selftest_analyze.py [GAMES]"""
import importlib.util, os, sys
import numpy as np

spec = importlib.util.spec_from_file_location('e1r', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'analyze.py'))
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


def synth(n, V, W, qF, seed, sozu_share=0.0):
    rng = np.random.default_rng(seed)
    games = {}
    for g in range(n):
        rolls, fi, potions, fairies = [], 0, 0, 0
        last_act = 4 if rng.random() < 0.4 else int(rng.integers(1, 4))
        sozu_game = bool(rng.random() < sozu_share) if sozu_share > 0 else False
        for act in range(1, last_act + 1):
            sozu = sozu_game and act >= 2
            c = 0
            k = int(rng.integers(4, 10)) if act < 4 else 0
            rooms = ['NORMAL'] * k + (['BOSS'] if act < 3 else []) + (['ELITE'] if act == 4 else [])
            for room in rooms:
                chance = min(100, max(0, 40 + c))
                dropped = bool(rng.integers(0, 100) < chance)
                c += -10 if dropped else 10
                x = {'fightIndex': fi, 'act': act, 'floor': fi, 'room': room, 'chance': chance, 'dropped': dropped,
                     'potionCount': int(rng.integers(0, 3)), 'potionCapacity': 2, 'sozu': sozu}
                if dropped:
                    t = 'FAIRY_POTION' if rng.random() < qF else ['BLOCK_POTION', 'FIRE_POTION', 'SWIFT_POTION'][int(rng.integers(0, 3))]
                    x['potion'] = t
                    potions += not sozu
                    fairies += t == 'FAIRY_POTION' and not sozu
                rolls.append(x)
                fi += 1
        p = 0.25 + V * (potions - 8) + W * fairies + 0.04 * (last_act - 2.5)
        games[1000 + g] = {'seed': 1000 + g, 'heartKill': bool(rng.random() < min(0.98, max(0.02, p))),
                           'cost': {'silverSimulations': 0}, 'rewards': {'rolls': rolls, 'inconsistent': 0}}
    return games


def main(n):
    V, W, qF = 0.03, 0.10, 0.06
    vb = 100 * (V + W * qF)                     # 3.6 pp: an average drop, Fairy share included
    games = synth(n, V=V, W=W, qF=qF, seed=20261108)
    same = {s: dict(g) for s, g in games.items()}
    r = A.analyse(games, same, n_units=A.N_UNITS)
    b, sb = r['primary']['boss_pp']
    f, sf = r['primary']['fairy_minus_other_pp']
    k6, sk6 = r['mid_by_later_rolls']['u_mid_k6+']
    print('signal: boss %.2f +- %.2f pp (true %.2f), fairy-other %.2f +- %.2f (true %.2f), mid 6+ later %.2f +- %.2f, %s'
          % (b, sb, vb, f, sf, 100 * W, k6, sk6, r['decision']))
    assert abs(b - vb) < 3 * sb, 'boss level not recovered'
    assert abs(f - 100 * W) < 3 * sf, 'Fairy contrast not recovered'
    assert k6 < b - 2 * sk6, 'mid-act coefficient not attenuated'
    assert r['decision'] == 'USABLE', r['decision']
    assert r['G1_seeds'] == n and r['G1_mismatch'] == [] and abs(r['boss_hp_units'] - b / A.BETA_HP_E1) < 1e-9
    flip = {s: dict(g) for s, g in games.items()}
    flip[1007]['heartKill'] = not flip[1007]['heartKill']
    g = A.analyse(games, flip, n_units=A.G3_MIN_UNITS - 1)
    print('gates: %s; decision_ci %s; HP units %s (%s)' % (g['decision'], g['decision_ci'], g['boss_hp_units'],
                                                         g['boss_hp_units_void']))
    assert g['decision'].startswith('INCOMPLETE') and g['decision_ci'] == 'USABLE', g['decision']
    assert g['G1_mismatch'] == [1007] and g['boss_hp_units'] is None
    assert g['primary']['boss_pp'] == r['primary']['boss_pp'], 'G1 must not change the potion estimates'
    assert A.analyse(games, n_units=A.G3_MIN_UNITS)['decision'] == 'USABLE'
    z = A.analyse(synth(n, V=V, W=W, qF=qF, seed=20261110, sozu_share=0.3))
    zn, szn = z['boss_sozu']['u_boss_nosozu']
    zs, szs = z['boss_sozu']['u_boss_sozu']
    print('sozu: %d boss rolls with Sozu; without %.2f +- %.2f (true %.2f), with %.2f +- %.2f (true 0)'
          % (z['boss_sozu_rolls'], zn, szn, vb, zs, szs))
    assert z['boss_sozu_rolls'] > 0 and abs(zn - vb) < 3 * szn and abs(zs) < 3 * szs, 'Sozu split'
    null = A.analyse(synth(n, V=0.0, W=0.0, qF=0.06, seed=20261109))
    print('null: boss %.2f +- %.2f, fairy %.2f +- %.2f, %s' % (*null['primary']['boss_pp'],
                                                            *null['primary']['fairy_minus_other_pp'], null['decision']))
    assert null['decision'] in ('UNRESOLVED', 'PARTIAL'), null['decision']
    print('selftest_analyze: passed')


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20000)
