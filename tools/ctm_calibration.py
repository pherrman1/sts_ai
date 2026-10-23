#!/usr/bin/env python3
"""Per-fight calibration of the A20 CTM against real combats (STS_CTM_CALIBRATION, research, default off).

  zero    OUT.json                                  every act:ROOM group at hpLossScale 0 (all HP losses removed)
  fit     OUT.json SPEC [SPEC ...] [--seeds S] [--note TEXT]   fit the table from scored real combats
  eval    TABLE.json SPEC [SPEC ...] [--seeds S] [--json OUT]   calibration with and without the table, by group
  compare BASE.csv CALIBRATED.csv [...] [--json OUT]  two scorings of the same rows (e.g. the C++ calibration)
  fixture TABLE.json ROWS.jsonl SPEC OUT.jsonl      rows for `one_combat ctmcalibrationtest`
  parity  TABLE.json SPEC CALIBRATED.csv [ROWS.jsonl]   the C++ calibrated scores against this tool's prediction
                                                    (ROWS: leave out rows with an active Lizard Tail)

SPEC is BASE.csv,ZERO.csv: `one_combat ctmscorerows` of the same combat_transition_row_v2 rows with the calibration off
(BASE) and with the `zero` table (ZERO). For a won fight in a group with loss scale s, calibrateHpLoss in
apps/one_combat/combat_transition_runtime.cpp makes the mean HP ZERO - s * (ZERO - BASE); that is exact apart from
the clamp at 1 HP when s > 1, which can only raise it, by at most (s - 1) * (pre HP - 1). The group's death shift
moves logit(p_death) of BASE; under an active Lizard Tail the runtime shifts the composition's two survival terms
instead, so those rows differ. Groups mirror CtmCalibration there: "<act>:<ENCOUNTER>" for elite and boss rooms when
the table has it, else "<act>:<ROOM>". --seeds even|odd|all picks rows by source seed parity (default all).
"""
import csv
import hashlib
import json
import math
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = 'pathb-a20'
ROOMS = ('NORMAL', 'ELITE', 'BOSS', 'OTHER')
LAMBDA = 2.0        # L2 penalty on an act:ROOM death shift, towards 0 (in units of the rows' Fisher information)
LAMBDA_FINE = 2.0   # L2 penalty on an act:ENCOUNTER death shift, towards its act:ROOM group's shift
MIN_FINE = 400      # rows an act:ENCOUNTER group needs to get its own entry
MIN_COARSE = 100    # rows an act:ROOM group needs
BOOTSTRAP = 1000


def enum_names(header, array):
    text = (ROOT / header).read_text()
    body = re.search(array + r'\[\]\s*(?:=\s*)?\{(.*?)\};', text, re.S).group(1)
    return [n.strip().strip('"') for n in body.split(',') if n.strip()]


ENCOUNTERS = enum_names('include/constants/MonsterEncounters.h', 'monsterEncounterEnumNames')
LIZARD_TAIL = enum_names('include/constants/Relics.h', 'relicEnumNames').index('LIZARD_TAIL')
ENTROPIC_BREW = enum_names('include/constants/Potions.h', 'potionEnumNames').index('ENTROPIC_BREW')


def keys(act, room, encounter):
    return (f'{act}:{ENCOUNTERS[encounter]}' if room in ('ELITE', 'BOSS') else None), f'{act}:{room}'


def lookup(table, r):
    groups = table['groups'] if table else {}
    entry = groups.get(r['fine']) if r['fine'] else None
    return entry or groups.get(r['coarse']) or {'deathLogitShift': 0.0, 'hpLossScale': 1.0}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(spec, seeds='all'):
    """SPEC is BASE.csv,ZERO.csv, or one scoring (no ZERO: only loss scale 1 can be evaluated)"""
    base_path, zero_path = spec.split(',') if ',' in spec else (spec, spec)
    rows = []
    with open(base_path, newline='') as fb, open(zero_path, newline='') as fz:
        for b, z in zip(csv.DictReader(fb), csv.DictReader(fz), strict=True):
            assert (b['source_seed'], b['fight_idx']) == (z['source_seed'], z['fight_idx']), 'BASE and ZERO rows differ'
            if b['scored'] != '1' or b['combat_outcome'] not in ('1', '2'):
                continue
            assert z['scored'] == '1' and z['p_death'] == b['p_death'], 'the zero table must not move deaths'
            if zero_path == base_path:
                z = {'expected_win_hp': 'nan'}
            seed = int(b['source_seed'])
            if seeds != 'all' and seed % 2 != (seeds == 'odd'):
                continue
            act, room, encounter = int(b['act']), b['room_class'], int(b['encounter'])
            assert room in ROOMS, room
            fine, coarse = keys(act, room, encounter)
            rows.append({'seed': seed, 'fight': int(b['fight_idx']), 'act': act, 'fine': fine, 'coarse': coarse,
                         'death': b['combat_outcome'] == '2', 'p': float(b['p_death']),
                         'pre': int(b['pre_hp']), 'post': int(b['post_hp']),
                         'base': float(b['expected_win_hp']), 'zero': float(z['expected_win_hp'])})
    return rows


def sigmoid(x):
    return 1 / (1 + math.exp(-x)) if x >= 0 else math.exp(x) / (1 + math.exp(x))


def shifted(p, shift):
    """calibrated death probability: CombatTransitionRuntime::survival leaves 0 and 1 alone"""
    if shift == 0 or not 0 < p < 1:
        return p
    return sigmoid(math.log(p / (1 - p)) + shift)


def predicted_hp(r, scale):
    return r['base'] if scale == 1 else r['zero'] - scale * (r['zero'] - r['base'])


def fit_shift(rows, lam, prior=0.0):
    live = [r for r in rows if 0 < r['p'] < 1]
    z = [math.log(r['p'] / (1 - r['p'])) for r in live]
    d = prior
    for _ in range(50):
        q = [sigmoid(x + d) for x in z]
        g = sum(qi - r['death'] for qi, r in zip(q, live)) + lam * (d - prior)
        h = sum(qi * (1 - qi) for qi in q) + lam
        d -= g / h
    return d


def fit_scale(rows):
    """least squares of the real loss on s * A - B over won fights (A the mean loss part, B the mean gain part)"""
    num = den = 0.0
    for r in rows:
        if r['death']:
            continue
        a, b = r['zero'] - r['base'], r['zero'] - r['pre']
        num += a * (r['pre'] - r['post'] + b)
        den += a * a
    return num / den if den > 0 else 1.0


def fit(rows, lam_fine=LAMBDA_FINE):
    by_fine, by_coarse, parent = defaultdict(list), defaultdict(list), {}
    for r in rows:
        by_coarse[r['coarse']].append(r)
        if r['fine']:
            by_fine[r['fine']].append(r)
            parent[r['fine']] = r['coarse']
    groups = {}
    for key, rs in sorted(by_coarse.items()):
        if len(rs) >= MIN_COARSE:
            groups[key] = {'deathLogitShift': round(fit_shift(rs, LAMBDA), 6), 'hpLossScale': round(fit_scale(rs), 6),
                           'rows': len(rs), 'deaths': sum(r['death'] for r in rs)}
    for key, rs in sorted(by_fine.items()):
        if len(rs) >= MIN_FINE:
            prior = groups.get(parent[key], {}).get('deathLogitShift', 0.0)
            groups[key] = {'deathLogitShift': round(fit_shift(rs, lam_fine, prior), 6),
                           'hpLossScale': round(fit_scale(rs), 6), 'rows': len(rs), 'deaths': sum(r['death'] for r in rs)}
    return groups


def table_json(groups, provenance):
    return {'schema': 'ctm_calibration_v1', 'candidateId': CANDIDATE, 'groups': groups, 'provenance': provenance}


def metrics(rows, table):
    """per row: log loss, squared error, won-fight HP error, with and without the table"""
    out = []
    for r in rows:
        entry = lookup(table, r)
        p = min(max(shifted(r['p'], entry['deathLogitShift']), 1e-12), 1 - 1e-12)
        m = {'ll': -math.log(p if r['death'] else 1 - p), 'brier': (p - r['death']) ** 2, 'p': p}
        if not r['death']:
            m['err'] = predicted_hp(r, entry['hpLossScale']) - r['post']
        out.append(m)
    return out


def summarize(rows, base, cal):
    n = len(rows)
    won = [i for i, r in enumerate(rows) if not r['death']]
    line = {'rows': n, 'deaths': sum(r['death'] for r in rows), 'observedDeath': sum(r['death'] for r in rows) / n}
    for name, m in (('base', base), ('cal', cal)):
        line[name] = {'predictedDeath': sum(x['p'] for x in m) / n, 'logLoss': sum(x['ll'] for x in m) / n,
                      'brier': sum(x['brier'] for x in m) / n}
        if won:
            line[name]['winHpMae'] = sum(abs(m[i]['err']) for i in won) / len(won)
            line[name]['winHpBias'] = sum(m[i]['err'] for i in won) / len(won)
    return line


def bootstrap(rows, base, cal):
    """95% seed-bootstrap intervals of the change in log loss and in won-fight HP MAE (calibrated - base)"""
    per = defaultdict(lambda: [0.0, 0, 0.0, 0])
    for r, b, c in zip(rows, base, cal):
        s = per[r['seed']]
        s[0] += c['ll'] - b['ll']
        s[1] += 1
        if 'err' in b:
            s[2] += abs(c['err']) - abs(b['err'])
            s[3] += 1
    seeds = sorted(per)
    rng = random.Random(20261023)
    draws = []
    for _ in range(BOOTSTRAP):
        pick = [per[rng.choice(seeds)] for _ in seeds]
        n, w = sum(x[1] for x in pick), sum(x[3] for x in pick)
        draws.append((sum(x[0] for x in pick) / n, sum(x[2] for x in pick) / max(w, 1)))
    out = {}
    for i, name in enumerate(('logLossChange', 'winHpMaeChange')):
        values = sorted(d[i] for d in draws)
        out[name] = [values[int(0.025 * BOOTSTRAP)], values[int(0.975 * BOOTSTRAP) - 1]]
    return out


def evaluate(rows, base, cal):
    result = {'all': summarize(rows, base, cal)}
    result['all']['bootstrap95'] = bootstrap(rows, base, cal)
    for field in ('coarse', 'fine'):
        groups = defaultdict(list)
        for i, r in enumerate(rows):
            if r[field]:
                groups[r[field]].append(i)
        for key, idx in sorted(groups.items()):
            if key in result:
                continue
            result[key] = summarize([rows[i] for i in idx], [base[i] for i in idx], [cal[i] for i in idx])
    return result


def print_eval(result):
    print(f"{'group':22s} {'rows':>6s} {'obs':>6s} {'pred base/cal':>13s} {'logloss base/cal':>17s} "
          f"{'winHP MAE base/cal':>18s} {'bias base/cal':>13s}")
    for key, v in result.items():
        b, c = v['base'], v['cal']
        hp = (f"{b['winHpMae']:8.2f}/{c['winHpMae']:<8.2f} {b['winHpBias']:6.2f}/{c['winHpBias']:<6.2f}"
              if 'winHpMae' in b else '')
        print(f"{key:22s} {v['rows']:6d} {v['observedDeath']:6.3f} {b['predictedDeath']:6.3f}/{c['predictedDeath']:<6.3f} "
              f"{b['logLoss']:8.4f}/{c['logLoss']:<8.4f} {hp}")
    print('bootstrap95', json.dumps(result['all']['bootstrap95']))


def options(args):
    seeds, out, note, rest = 'all', None, None, []
    it = iter(args)
    for a in it:
        if a == '--seeds':
            seeds = next(it)
            assert seeds in ('even', 'odd', 'all'), seeds
        elif a == '--json':
            out = next(it)
        elif a == '--note':
            note = next(it)
        else:
            rest.append(a)
    return seeds, out, note, rest


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    command, args = argv[1], argv[2:]
    if command == 'zero':
        groups = {f'{act}:{room}': {'deathLogitShift': 0.0, 'hpLossScale': 0.0} for act in range(1, 5) for room in ROOMS}
        Path(args[0]).write_text(json.dumps(table_json(groups, {'purpose': 'every HP loss removed (fit input)'}),
                                            indent=1) + '\n')
    elif command == 'fit':
        seeds, _, note, rest = options(args)
        out, specs = rest[0], rest[1:]
        rows = [r for spec in specs for r in load(spec, seeds)]
        provenance = {'tool': 'tools/ctm_calibration.py', 'note': note, 'seeds': seeds, 'rows': len(rows),
                      'inputs': {f'{Path(p).parent.name}/{Path(p).name}': sha256(p)
                                 for spec in specs for p in spec.split(',')},
                      'lambda': LAMBDA, 'lambdaFine': LAMBDA_FINE, 'minFineRows': MIN_FINE, 'minCoarseRows': MIN_COARSE}
        Path(out).write_text(json.dumps(table_json(fit(rows), provenance), indent=1) + '\n')
        print(f'fit {len(rows)} rows -> {out}')
    elif command == 'eval':
        seeds, out, _, rest = options(args)
        table = json.loads(Path(rest[0]).read_text())
        rows = [r for spec in rest[1:] for r in load(spec, seeds)]
        result = evaluate(rows, metrics(rows, None), metrics(rows, table))
        print_eval(result)
        if out:
            Path(out).write_text(json.dumps(result, indent=1) + '\n')
    elif command == 'compare':
        seeds, out, _, rest = options(args)
        assert rest and len(rest) % 2 == 0, 'compare takes BASE.csv CALIBRATED.csv pairs'
        rows, calibrated = [], []
        for base_path, cal_path in zip(rest[::2], rest[1::2]):
            b, c = load(base_path, seeds), load(cal_path, seeds)
            assert [(r['seed'], r['fight'], r['death']) for r in b] == [(r['seed'], r['fight'], r['death']) for r in c]
            rows += b
            calibrated += c
        result = evaluate(rows, metrics(rows, None), metrics(calibrated, None))
        print_eval(result)
        if out:
            Path(out).write_text(json.dumps(result, indent=1) + '\n')
    elif command == 'fixture':
        table_path, rows_path, spec, out = args
        table = json.loads(Path(table_path).read_text())
        scored = {(r['seed'], r['fight']): r for r in load(spec)}
        picked, seen = [], defaultdict(int)
        with open(rows_path) as f:
            for line in f:
                row = json.loads(line)
                r = scored.get((row['sourceSeed'], row['fightIdx']))
                inp = row['predictorInput']
                if r is None or any(x['relicId'] == LIZARD_TAIL and x['data'] == 1 for x in inp['relics']):
                    continue  # the active-Lizard composition shifts its two survivals, not the composed death
                # one row per group, and one with Entropic Brew (scored by the standard fallback runtime)
                brew = any(q['potionId'] == ENTROPIC_BREW for q in inp['potions'])
                key = 'brew' if brew else (r['fine'] if r['fine'] in table['groups'] else r['coarse'])
                if seen[key] >= 1:
                    continue
                seen[key] += 1
                entry = lookup(table, r)
                picked.append({'sourceSeed': r['seed'], 'fightIdx': r['fight'],
                               'group': r['fine'] if r['fine'] in table['groups'] else r['coarse'], 'brew': brew,
                               'predictorInput': inp, 'pre': row['transition']['pre'],
                               'base': {'pDeath': r['p'], 'expectedWinHp': r['base']},
                               'calibrated': {'pDeath': shifted(r['p'], entry['deathLogitShift']),
                                              'expectedWinHp': predicted_hp(r, entry['hpLossScale'])},
                               'hpLossScale': entry['hpLossScale']})
        with open(out, 'w') as f:
            for p in picked:
                f.write(json.dumps(p, separators=(',', ':')) + '\n')
        print(f'fixture {len(picked)} rows -> {out}')
    elif command == 'parity':
        table_path, spec, calibrated = args[:3]
        table = json.loads(Path(table_path).read_text())
        rows = {(r['seed'], r['fight']): r for r in load(spec)}
        lizard = set()
        if len(args) > 3:
            with open(args[3]) as f:
                for line in f:
                    row = json.loads(line)
                    if any(x['relicId'] == LIZARD_TAIL and x['data'] == 1 for x in row['predictorInput']['relics']):
                        lizard.add((row['sourceSeed'], row['fightIdx']))
        worst_p = worst_hp = 0.0
        over = n = skipped = 0
        with open(calibrated, newline='') as f:
            for c in csv.DictReader(f):
                key = (int(c['source_seed']), int(c['fight_idx']))
                r = rows.get(key)
                if r is None:
                    continue
                if key in lizard:
                    skipped += 1
                    continue
                entry = lookup(table, r)
                scale = entry['hpLossScale']
                dp = abs(float(c['p_death']) - shifted(r['p'], entry['deathLogitShift']))
                dh = float(c['expected_win_hp']) - predicted_hp(r, scale)
                slack = (scale - 1) * (r['pre'] - 1) if scale > 1 else 0.0  # the clamp at 1 HP only raises the mean
                miss = -dh if dh < 0 else max(0.0, dh - slack)
                worst_p, worst_hp, n = max(worst_p, dp), max(worst_hp, miss), n + 1
                over += dp > 1e-5 or miss > 1e-3
        print(f'parity rows={n} activeLizardLeftOut={skipped} maxAbsPDeath={worst_p:.3g} maxWinHpMiss={worst_hp:.3g} '
              f'rowsOverTolerance={over}')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv)
