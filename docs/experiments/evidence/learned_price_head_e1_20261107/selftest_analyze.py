#!/usr/bin/env python3
"""Synthetic check of analyze.py (no campaign data): builds E1 and pilot unit tars in a temporary directory from a
model with a known HP price and checks that the gates pass, that beta_luck and beta_CRN recover the price, and that
the decision follows the ratio.
usage: selftest_analyze.py [SEEDS=6400]"""
import gzip, io, json, os, random, sys, tarfile, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze  # noqa: E402

ROOMS = (('NORMAL', 0.7, 6.0), ('ELITE', 0.2, 10.0), ('BOSS', 0.1, 14.0))


def add(t, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    t.addfile(info, io.BytesIO(data))


def write_unit(d, uid, prefix, rows):
    path = os.path.join(d, f'{uid}.w01.tar')
    with tarfile.open(path, 'w') as t:
        body = gzip.compress(''.join(json.dumps(r) + '\n' for r in rows).encode())
        add(t, f'out/units/{uid}/{prefix}-{uid}.jsonl.gz', body)
        add(t, f'out/units/{uid}/result.txt', f'tag={uid} rc=0 start=x wall=1\n'.encode())


def scenario(root, seeds, theta, theta_crn, rng):
    e1_dir, pilot_dir = os.path.join(root, 'e1'), os.path.join(root, 'pilot')
    os.makedirs(e1_dir), os.makedirs(pilot_dir)
    e1_rows, pilot_rows = {}, {}
    for i in range(seeds):
        seed = 111780000 + i
        k = rng.randint(6, 30)
        fights, total = [], 0.0
        for f in range(k):
            act = 1 + (3 * f) // k
            room, sd = rng.choices([(r, s) for r, _, s in ROOMS], [w for _, w, _ in ROOMS])[0]
            h0 = rng.randint(15, 80)
            mean_loss = 8 if room == 'NORMAL' else 15
            e_real, e_rep = rng.gauss(0, sd), rng.gauss(0, sd)
            hp_real = max(1, round(h0 - mean_loss + e_real))
            hp_rep = max(1, round(h0 - mean_loss + e_rep))
            total += hp_real - (h0 - mean_loss)
            fights.append((f, act, room, h0, hp_real, hp_rep))
        p = min(0.95, max(0.02, 0.25 + theta * total))
        u = rng.random()
        heart = u < p
        relics = ['BURNING_BLOOD', 'PEN_NIB']
        state = lambda hp: {'hp': hp, 'maxHp': 80, 'potions': [], 'potionCapacity': 2, 'deck': [], 'deckMisc': [],
                            'relics': relics, 'relicData': [0, 0], 'gold': 99}
        fields = lambda hp: {'hp': hp, 'maxHp': 80, 'potionCount': 0, 'potions': [], 'gold': 99, 'deckSize': 10,
                             'upgrades': 0, 'misc': 0, 'relicData': [0, 0]}
        src = {'kind': 'source', 'seed': seed, 'valid': True, 'won': float(heart), 'heartKill': heart,
               'floor': 56.0 if heart else 20.0, 'fightEnds': k, 'eligible': k, 'ineligible': {},
               'ppo': {'decisions': 50, 'single': 10, 'fallbacks': 0, 'autoGold': 5},
               'cost': {'cpuMs': 1000.0, 'wallMs': 1000.0, 'silverSimulations': 1000}}
        unit = 111780000 + 16 * (i // 16)
        ident = (i % 16) == 0
        luck_rows = []
        for f, act, room, h0, hp_real, hp_rep in fights:
            row = {'kind': 'luck', 'seed': seed, 'fightIndex': f, 'act': act, 'floor': f + 1, 'room': room,
                   'encounter': f'{room}_{act}', 'budget': 1000, 'relics': relics, 'start': fields(h0),
                   'real': {'won': True, 'alive': True, 'fields': fields(hp_real), 'state': state(hp_real)},
                   'replays': [{'r': 1, 'battleSeed': 1, 'won': True, 'alive': True, 'combatOutcome': 1, 'turns': 3,
                                'cpuMs': 10.0, 'simulations': 1000, 'healthFailures': 0, 'fields': fields(hp_rep)}]}
            if ident:
                row['identity'] = True
            luck_rows.append(row)
        e1_src = dict(src, sampled=0, luck={'replicates': 1, 'identitySeed': ident, 'fights': k,
                                            'replays': k * (2 if ident else 1), 'errors': 0, 'healthFailures': 0,
                                            'identityChecked': k if ident else 0, 'identityMismatches': 0,
                                            'cpuMs': 10.0 * k})
        e1_rows.setdefault(unit, []).extend(luck_rows + [e1_src])
        sample = rng.sample(fights, min(4, k))
        p_rows = [dict(src, sampled=len(sample))]
        for fork, (f, act, room, h0, hp_real, hp_rep) in enumerate(sorted(sample)):
            base = {'kind': 'copy', 'seed': seed, 'fork': fork, 'fightIndex': f, 'act': act, 'room': room,
                    'state': state(hp_real)}
            p_rows.append(dict(base, variant='base', outcome={'valid': True, 'heartKill': heart}))
            for kk in (3, 8, 15):
                if hp_real - kk < 1:
                    continue
                y = u < p - theta_crn * kk
                p_rows.append(dict(base, variant=f'hp:-{kk}', outcome={'valid': True, 'heartKill': y}))
        pilot_rows.setdefault(111780000 + 8 * (i // 8), []).extend(p_rows)
    for uid, rows in e1_rows.items():
        write_unit(e1_dir, uid, 'le', rows)
    for uid, rows in pilot_rows.items():
        write_unit(pilot_dir, uid, 'fe', rows)
    out = os.path.join(root, 'out.json')
    analyze.main(e1_dir, pilot_dir, out)
    return json.load(open(out))


def main():
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 6400
    rng = random.Random(7)
    with tempfile.TemporaryDirectory() as root:
        same = scenario(os.path.join(root, 'same'), seeds, 0.004, 0.004, rng)
        half = scenario(os.path.join(root, 'half'), seeds, 0.004, 0.002, rng)
    for name, res, crn in (('same', same, 0.4), ('half', half, 0.2)):
        g = res['groups']['pooled']
        print(name, res['decision'], 'luck', round(g['beta_luck_pp'], 3), g['beta_luck_ci95_pp'], 'crn',
              round(g['beta_crn_pp'], 3), g['beta_crn_ci95_pp'], 'ratio', round(g['ratio'], 2), g['ratio_ci90'])
        assert not res['gates']['G1_mismatch_seeds'] and res['gates']['G2_mismatch_n'] == 0, 'identity gates'
        assert res['gates']['G5_pass'], 'exchangeability gate'
        assert g['beta_luck_ci95_pp'][0] < 0.4 < g['beta_luck_ci95_pp'][1], 'luck CI misses the true price'
        assert g['beta_crn_ci95_pp'][0] < crn < g['beta_crn_ci95_pp'][1], 'CRN CI misses the true price'
    assert same['groups']['pooled']['ratio_ci95'][0] < 1 < same['groups']['pooled']['ratio_ci95'][1], 'same: ratio'
    assert half['decision'] == 'FAIL', 'half: decision'
    print('selftest_analyze: passed')


if __name__ == '__main__':
    main()
