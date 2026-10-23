"""Death-rate and HP-loss errors by fight type, predicted - real: python3 -I group_errors.py TOOL.py EVEN.json ODD.json SPEC...
TOOL.py is tools/ctm_calibration.py; EVEN.json and ODD.json the tables fitted on the even and the odd seeds (`fit
--seeds even|odd`). The CTM columns cover all fights; the adjusted columns score each half with the other half's table.
Prints errors_by_fight.md."""
import importlib.util
import json
import sys
from collections import defaultdict

spec = importlib.util.spec_from_file_location('ctm_calibration', sys.argv[1])
cal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal)
EVEN, ODD, SPECS = json.load(open(sys.argv[2])), json.load(open(sys.argv[3])), sys.argv[4:]
ROOM = {'NORMAL': 'hallway', 'ELITE': 'elites', 'BOSS': 'bosses', 'OTHER': 'event fights'}
PRETTY = {'THE_GUARDIAN': 'The Guardian', 'THE_HEART': 'The Heart', 'SHIELD_AND_SPEAR': 'Shield and Spear',
          'DONU_AND_DECA': 'Donu and Deca', 'BOOK_OF_STABBING': 'Book of Stabbing'}


def half(seeds, table):
    agg = defaultdict(lambda: [0, 0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, 0.0])
    for r in (r for s in SPECS for r in cal.load(s, seeds)):
        e = cal.lookup(table, r)
        q = cal.shifted(r['p'], e['deathLogitShift'])
        for k in ['all', r['coarse']] + ([r['fine']] if r['fine'] else []):
            a = agg[k]
            a[0] += 1
            a[1] += r['death']
            a[2] += r['p']
            a[3] += q
            if not r['death']:
                real = r['pre'] - r['post']
                ctm, adjusted = r['pre'] - r['base'], r['pre'] - cal.predicted_hp(r, e['hpLossScale'])
                a[4] += 1
                a[5] += real
                a[6] += ctm - real
                a[7] += adjusted - real
                a[8] += abs(ctm - real)
                a[9] += abs(adjusted - real)
    out = {}
    for k, a in agg.items():
        n, w = a[0], max(a[4], 1)
        out[k] = dict(fights=n, won=a[4], realDeath=a[1] / n, ctmDeath=a[2] / n, calDeath=a[3] / n, realLoss=a[5] / w,
                      ctmLossErr=a[6] / w, calLossErr=a[7] / w, ctmMae=a[8] / w, calMae=a[9] / w)
    return out


o, e = half('odd', EVEN), half('even', ODD)


def name(k):
    if k == 'all':
        return 'all fights'
    act, rest = k.split(':')
    if rest in ROOM:
        return f'Act {act} {ROOM[rest]}'
    return f"{PRETTY.get(rest, rest.replace('_', ' ').title())} (A{act})"


def row(k):
    a, b = o[k], e[k]
    n, w = a['fights'] + b['fights'], a['won'] + b['won']
    real = (a['realDeath'] * a['fights'] + b['realDeath'] * b['fights']) / n
    ctm = (a['ctmDeath'] * a['fights'] + b['ctmDeath'] * b['fights']) / n
    loss = (a['realLoss'] * a['won'] + b['realLoss'] * b['won']) / max(w, 1)
    ctm_loss = (a['ctmLossErr'] * a['won'] + b['ctmLossErr'] * b['won']) / max(w, 1)
    pp, hp = (lambda x: f'{100 * x:+.1f}'), (lambda x: f'{x:+.1f}')
    death = f"{100 * real:.1f}% | {pp(ctm - real)} | {pp(a['calDeath'] - a['realDeath'])} / {pp(b['calDeath'] - b['realDeath'])}"
    hp_cols = ('– | – | –' if k in ('4:THE_HEART', '4:BOSS') else
               f"{loss:.1f} | {hp(ctm_loss)} | {hp(a['calLossErr'])} / {hp(b['calLossErr'])}")
    return f'| {name(k)} | {n:,} | {death} | {hp_cols} |'


encounters = [k for k in o if k in e and k != 'all' and k.split(':')[1] not in ROOM]
spread = max(abs(o[k]['realDeath'] - e[k]['realDeath']) for k in encounters)
head = ('| fights | n | real death rate | CTM error (pp) | adjusted error (pp), odd / even seeds | real HP loss | '
        'CTM error (HP) | adjusted error (HP), odd / even seeds |\n|---|---|---|---|---|---|---|---|')
print('# CTM errors by fight type\n')
print('The 97,561 real fights of the stage-3 A/B (2026-10-23). Errors are predicted minus real.\n')
print('- A positive death error means too many predicted deaths. A positive HP error means too much predicted HP loss.')
print('- HP loss is the mean over won fights, net of Burning Blood and other healing (hence near 0 in hallways). '
      'The Heart ends the run, so it has no HP loss.')
print('- The CTM columns cover all fights: nothing was fitted to them.')
print('- The adjusted columns are out of sample. The odd seeds are scored with the adjustment fitted on the even seeds, '
      'and the even seeds with the one fitted on the odd seeds.')
print(f'- Single encounters are noisy. The real death rate of one encounter differs between the two halves by up to '
      f'{100 * spread:.0f} pp (Hexaghost 6.9% against 12.0%), so an adjusted error of a few pp at one encounter is '
      'noise level.\n')
print('## By act and room\n')
print(head)
for k in ['all'] + [f'{act}:{room}' for act in range(1, 5) for room in ('NORMAL', 'ELITE', 'BOSS', 'OTHER')]:
    if k in o and k in e:
        print(row(k))
print('\n## Elites and bosses with their own correction\n')
print(head)
for k in sorted(encounters, key=lambda k: (k.split(':')[0], k)):
    print(row(k))
print(f"\nPer-fight precision, the mean absolute error of the HP after a won fight over all fights: CTM {o['all']['ctmMae']:.2f} "
      f"HP, adjusted {o['all']['calMae']:.2f} HP (odd seeds); {e['all']['ctmMae']:.2f} → {e['all']['calMae']:.2f} (even seeds).\n")
print('Source: `docs/experiments/evidence/ctm_calibration_20261023/offline/eval_fit_even_on_odd.json` and '
      '`eval_fit_odd_on_even.json`.')
