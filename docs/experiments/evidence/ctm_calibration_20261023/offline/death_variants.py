"""Death calibration variants, fitted on one seed parity and scored on the other, by act x pre-fight HP band.
python3 -I death_variants.py TOOL.py FIT_SEEDS EVAL_SEEDS LAMBDA_SLOPE SPEC [SPEC ...]
TOOL.py is tools/ctm_calibration.py (its loader, groups, penalties and minimum rows). Variants of logit(p_death):
  shift  + a_g                      (the table's form: an intercept per group)
  platt  + a_g + b_g * logit(p)     (a slope change per room group; encounter groups inherit it)
  hp     + a_g + b_g * (HP/max - 0.5)  (an HP-fraction term per room group; encounter groups inherit it)
a_g as in the tool (lambda 2 towards 0, encounter groups towards their room group); b_g has penalty LAMBDA_SLOPE towards 0.
Rows whose CTM death probability is exactly 0 or 1 are left out (no variant moves them)."""
import csv
import importlib.util
import math
import sys
from collections import defaultdict

spec = importlib.util.spec_from_file_location('ctm_calibration', sys.argv[1])
cal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal)
FIT_SEEDS, EVAL_SEEDS, LAMBDA_SLOPE, SPECS = sys.argv[2], sys.argv[3], float(sys.argv[4]), sys.argv[5:]
VARIANTS = ('shift', 'platt', 'hp')
FROZEN = 1e12  # a penalty that keeps a parameter at its prior


def load(seeds):
    out = []
    for s in SPECS:
        with open(s.split(',')[0], newline='') as f:
            maximum = {(int(b['source_seed']), int(b['fight_idx'])): int(b['pre_max_hp']) for b in csv.DictReader(f)}
        for r in cal.load(s, seeds):
            if 0 < r['p'] < 1:
                r['frac'] = r['pre'] / max(maximum[(r['seed'], r['fight'])], 1)
                out.append(r)
    return out


def logit(p):
    return math.log(p / (1 - p))


def feature(variant, r):
    return logit(r['p']) if variant == 'platt' else r['frac'] - 0.5 if variant == 'hp' else 0.0


def newton(rows, variant, prior, lam):
    """penalized logistic fit of logit(p) + a + b * feature: Newton steps on (a, b)"""
    a, b = prior
    for _ in range(60):
        ga = gb = haa = hab = hbb = 0.0
        for r in rows:
            x = feature(variant, r)
            q = cal.sigmoid(logit(r['p']) + a + b * x)
            e, w = q - r['death'], q * (1 - q)
            ga, gb, haa, hab, hbb = ga + e, gb + e * x, haa + w, hab + w * x, hbb + w * x * x
        ga += lam[0] * (a - prior[0])
        gb += lam[1] * (b - prior[1])
        haa += lam[0]
        hbb += lam[1]
        det = haa * hbb - hab * hab
        da, db = (hbb * ga - hab * gb) / det, (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) + abs(db) < 1e-10:
            break
    return a, b


def fit(rows, variant):
    by_room, by_encounter, parent = defaultdict(list), defaultdict(list), {}
    for r in rows:
        by_room[r['coarse']].append(r)
        if r['fine']:
            by_encounter[r['fine']].append(r)
            parent[r['fine']] = r['coarse']
    slope = FROZEN if variant == 'shift' else LAMBDA_SLOPE
    groups = {k: newton(rs, variant, (0.0, 0.0), (cal.LAMBDA, slope))
              for k, rs in by_room.items() if len(rs) >= cal.MIN_COARSE}
    for k, rs in by_encounter.items():
        if len(rs) >= cal.MIN_FINE and parent[k] in groups:
            groups[k] = newton(rs, variant, groups[parent[k]], (cal.LAMBDA_FINE, FROZEN))
    return groups


def band(hp):
    return '<20' if hp < 20 else '20-39' if hp < 40 else '40-59' if hp < 60 else '60+'


train, test = load(FIT_SEEDS), load(EVAL_SEEDS)
fits = {v: fit(train, v) for v in VARIANTS}
agg = defaultdict(lambda: defaultdict(lambda: [0, 0.0, 0.0, 0]))  # variant -> key -> [rows, logloss, p, deaths]
for r in test:
    keys = ('all', f"{r['act']}:{band(r['pre'])}", f"{r['coarse']}:{band(r['pre'])}")
    preds = {'ctm': r['p']}
    for v in VARIANTS:
        g = (fits[v].get(r['fine']) if r['fine'] else None) or fits[v].get(r['coarse']) or (0.0, 0.0)
        preds[v] = cal.sigmoid(logit(r['p']) + g[0] + g[1] * feature(v, r))
    for v, q in preds.items():
        q = min(max(q, 1e-12), 1 - 1e-12)
        for k in keys:
            a = agg[v][k]
            a[0] += 1
            a[1] += -math.log(q if r['death'] else 1 - q)
            a[2] += q
            a[3] += r['death']
print(f'fit on {FIT_SEEDS} seeds, scored on {EVAL_SEEDS}; slope penalty {LAMBDA_SLOPE}; mean prediction and log loss')
print(f"{'group':18s} {'rows':>6s} {'obs':>6s} | {'ctm':>6s} {'LL':>7s} | {'shift':>6s} {'LL':>7s} | "
      f"{'platt':>6s} {'LL':>7s} | {'hp':>6s} {'LL':>7s}")
for k in sorted(agg['ctm'], key=lambda k: (k != 'all', k)):
    b = agg['ctm'][k]
    if b[0] < 60:
        continue
    line = f'{k:18s} {b[0]:6d} {b[3] / b[0]:6.3f}'
    for v in ('ctm',) + VARIANTS:
        a = agg[v][k]
        line += f' | {a[2] / a[0]:6.3f} {a[1] / a[0]:7.4f}'
    print(line)
for v in ('platt', 'hp'):
    print(v, 'room groups (a, b):', {k: (round(a, 3), round(b, 3)) for k, (a, b) in sorted(fits[v].items())
                                    if k.split(':')[1] in cal.ROOMS})
