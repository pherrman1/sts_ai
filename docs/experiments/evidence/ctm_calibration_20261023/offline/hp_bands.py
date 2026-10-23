"""Death and won-fight HP calibration by pre-fight HP band, out of sample.
python3 -I hp_bands.py TOOL.py TABLE.json SEEDS SPEC [SPEC ...]
TOOL.py is tools/ctm_calibration.py; TABLE.json a table fitted on the other seed parity (`fit --seeds even`); SEEDS
the parity scored (odd). Prints, per act x room (and act x ALL) x band with >= 50 fights: deaths observed, the CTM's and
the calibrated mean prediction, their log loss and the won-fight HP bias (predicted - real)."""
import importlib.util
import json
import math
import sys
from collections import defaultdict

spec = importlib.util.spec_from_file_location('ctm_calibration', sys.argv[1])
cal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal)
table = json.load(open(sys.argv[2]))
rows = [r for s in sys.argv[4:] for r in cal.load(s, sys.argv[3])]
BANDS = ('<20', '20-39', '40-59', '60+')
ORDER = ('NORMAL', 'ELITE', 'BOSS', 'OTHER', 'ALL')


def band(hp):
    return BANDS[0] if hp < 20 else BANDS[1] if hp < 40 else BANDS[2] if hp < 60 else BANDS[3]


def logloss(p, death):
    p = min(max(p, 1e-12), 1 - 1e-12)
    return -math.log(p if death else 1 - p)


agg = defaultdict(lambda: [0, 0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0])
for r in rows:
    e = cal.lookup(table, r)
    q = cal.shifted(r['p'], e['deathLogitShift'])
    for key in ((r['act'], r['coarse'].split(':')[1], band(r['pre'])), (r['act'], 'ALL', band(r['pre']))):
        a = agg[key]
        a[0] += 1
        a[1] += r['death']
        a[2] += r['p']
        a[3] += q
        a[4] += logloss(r['p'], r['death'])
        a[5] += logloss(q, r['death'])
        if not r['death']:
            a[6] += 1
            a[7] += r['base'] - r['post']
            a[8] += cal.predicted_hp(r, e['hpLossScale']) - r['post']
print(f"{'act':>3s} {'room':6s} {'band':6s} {'rows':>6s} {'deaths':>6s} {'obs':>6s} {'ctm':>6s} {'cal':>6s} "
      f"{'LL ctm':>7s} {'LL cal':>7s} {'HP bias ctm':>11s} {'HP bias cal':>11s}")
for key in sorted(agg, key=lambda k: (k[0], ORDER.index(k[1]), BANDS.index(k[2]))):
    a = agg[key]
    if a[0] < 50:
        continue
    won = max(a[6], 1)
    print(f"{key[0]:3d} {key[1]:6s} {key[2]:6s} {a[0]:6d} {a[1]:6d} {a[1] / a[0]:6.3f} {a[2] / a[0]:6.3f} "
          f"{a[3] / a[0]:6.3f} {a[4] / a[0]:7.4f} {a[5] / a[0]:7.4f} {a[7] / won:11.2f} {a[8] / won:11.2f}")
