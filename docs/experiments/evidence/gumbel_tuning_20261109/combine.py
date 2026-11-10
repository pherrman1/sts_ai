#!/usr/bin/env python3
"""Stage-2 arms of the Gumbel tuning experiment (PREREG.md, "Later stages") from the stage-1 analysis.

usage: python3 -I combine.py results/analysis_screen.json [--extra]
Writes arms_combine.tsv (arm id, the 10 levels on the screening's coded scale, token) and sets_combine.arms (ctl
and the stage-2 arm ids, one per line) next to this script.

Rule (PREREG): factors whose main effect is ACTIVE, ordered by |main effect|.
  c1 = every ACTIVE factor at its better level, the others at the control;
  c2 = c1 with the largest one more step in its better direction; c3 = c1 with the two largest one step further;
  c4-c6 = c1-c3 with gnr if GNR_HELPS, otherwise c1-c3 with the next (third-largest) ACTIVE factor one step further.
  One more step = the level x2 or /2 once more (k, c_scale, max backup, UCB, prior weight, tree prior, widening C);
  noise and halving have no further step (such a factor is left at its better level).
--extra adds two arms Philipp chose after stage 1 (the screening's curvature suggested the full steps overshoot):
  x1 = only the two largest ACTIVE factors at their better level; x2 = every ACTIVE factor half way (geometric mean
  of the control and its better level).
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# factor: (part, control value, low, high); None = a level that is no part (the default)
LEVELS = {
    'A': ('gsh', 16, 8, 32), 'B': ('gcs', 1, 0.5, 2), 'C': ('gnz', None, '0', None), 'D': ('ghb', None, None, ''),
    'E': ('mb', 4, 2, 8), 'F': ('ucb', 25, 12.5, 50), 'G': ('pw', 400, 100, 1600), 'H': ('tp', 8, 2, 32),
    'J': ('wet', 3.7028, 1.85, 7.4), 'K': ('wch', 3.7028, 1.85, 7.4)}
INTEGER = {'A', 'E', 'H'}
ORDER = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'J', 'K']   # token order as design.py
CONTROL_CODE = {'C': 1, 'D': -1}


def num(x, integer):
    if integer:
        assert abs(x - round(x)) < 1e-9, x
        return str(int(round(x)))
    s = f'{x:.4f}'.rstrip('0').rstrip('.')
    return s


def token(values, gnr=False):
    """values: factor -> numeric value (A, B, E-K) or 'low'/'high' (C, D); missing = control."""
    parts = []
    for c in ORDER:
        part, ctl = LEVELS[c][0], LEVELS[c][1]
        if c == 'A':
            parts.append('gsh' + num(values.get('A', ctl), True))
            parts.append('flat16000')
            continue
        if c == 'C':
            if values.get('C') == 'low':
                parts.append('gnz0')
            continue
        if c == 'D':
            if values.get('D') == 'high':
                parts.append('ghb')
            continue
        if c == 'E':
            parts.append('mb' + num(values.get('E', ctl), True))
            continue
        if c in values:
            parts.append(part + num(values[c], c in INTEGER))
    if gnr:
        parts.append('gnr')
    return '+'.join(parts)


def coded(values):
    out = {}
    for c in ORDER:
        if c in ('C', 'D'):
            v = values.get(c)
            out[c] = CONTROL_CODE[c] if v is None else (1 if v == 'high' else -1)
            continue
        ctl, lo, hi = LEVELS[c][1:]
        v = values.get(c, ctl)
        end = hi if v >= ctl else lo
        out[c] = round(abs(math.log(v / ctl) / math.log(end / ctl)) * (1 if v >= ctl else -1), 4)
    return out


def main():
    res = json.load(open(sys.argv[1]))['result']
    extra = '--extra' in sys.argv[2:]
    if res['gnr_minus_ctl']['verdict'] == 'NOT_PAIRED':
        raise SystemExit('stage 1 is NOT_PAIRED')
    mains = res['main_effects']
    active = sorted((c for c, m in mains.items() if m['verdict'] in ('HIGH_BETTER', 'LOW_BETTER')),
                    key=lambda c: -abs(mains[c]['high_minus_low']))
    if not active:
        raise SystemExit('no ACTIVE factor: stage 2 has no arm to build')
    better = {c: 'high' if mains[c]['verdict'] == 'HIGH_BETTER' else 'low' for c in active}

    def level(c, steps):
        """Value of factor c at its better level, `steps` further steps (x2 or /2) beyond it."""
        if c in ('C', 'D'):
            return better[c]
        ctl, lo, hi = LEVELS[c][1:]
        v = hi if better[c] == 'high' else lo
        return v * (2 ** steps if better[c] == 'high' else 0.5 ** steps)

    def arm(stepped=(), only=None, gnr=False):
        use = active if only is None else only
        return {c: level(c, 1 if c in stepped else 0) for c in use}, gnr

    arms = [('c1', *arm()), ('c2', *arm(active[:1])), ('c3', *arm(active[:2]))]
    helps = res['gnr_minus_ctl']['verdict'] == 'GNR_HELPS'
    nxt = active[2:3]
    for i, (_, v, _) in enumerate(list(arms)):
        if helps:
            arms.append((f'c{i + 4}', v, True))
        elif nxt:
            stepped = active[:i] + nxt
            arms.append((f'c{i + 4}', *arm(stepped)))
    if extra:
        arms.append(('x1', *arm(only=active[:2])))
        half = {}
        for c in active:
            if c in ('C', 'D'):
                continue   # no half way for a two-valued factor
            half[c] = math.sqrt(LEVELS[c][1] * level(c, 0))
            if c in INTEGER:
                half[c] = float(round(half[c]))
        arms.append(('x2', half, False))
    seen = {}
    rows = []
    for a, values, gnr in arms:
        t = token(values, gnr)
        if t in seen:
            raise SystemExit(f'{a} repeats {seen[t]}: {t}')
        seen[t] = a
        cd = coded(values)
        rows.append(f'{a}\t' + '\t'.join(num(cd[c], False) for c in ORDER) + f'\t{t}\n')
    with open(os.path.join(HERE, 'arms_combine.tsv'), 'w') as f:
        f.write('# stage-2 arms from results/analysis_screen.json (combine.py); levels on the screening\'s coded scale '
                '(log2 steps relative to the half range; C, D: +1/-1)\n')
        f.write('arm\t' + '\t'.join(ORDER) + '\ttoken\n')
        f.writelines(rows)
    with open(os.path.join(HERE, 'sets_combine.arms'), 'w') as f:
        f.write('# stage-2 arms (combine.py): the control and the arms of arms_combine.tsv\n')
        f.write('ctl\n' + ''.join(r.split('\t')[0] + '\n' for r in rows))
    print('active', ' '.join(f'{c}:{better[c]}:{mains[c]["high_minus_low"]}' for c in active))
    for r in rows:
        print(r, end='')


if __name__ == '__main__':
    main()
