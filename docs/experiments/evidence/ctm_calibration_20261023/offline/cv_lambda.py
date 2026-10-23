"""2-fold (even/odd source seed) CV of LAMBDA_FINE, the penalty on an act:ENCOUNTER death shift towards its act:ROOM
group. python3 -I cv_lambda.py TOOLS_DIR SPEC... (TOOLS_DIR holds tools/ctm_calibration.py; SPEC as there)"""
import sys
sys.path.insert(0, sys.argv[1])
import ctm_calibration as c
specs = sys.argv[2:]
folds = {s: [r for spec in specs for r in c.load(spec, s)] for s in ('even', 'odd')}
for lam in (0.5, 2, 5, 10, 20, 50, 1e9):
    tot = n = 0.0
    per = {}
    for train, test in (('even', 'odd'), ('odd', 'even')):
        table = {'groups': c.fit(folds[train], lam)}
        m = c.metrics(folds[test], table)
        tot += sum(x['ll'] for x in m); n += len(m)
        for r, x in zip(folds[test], m):
            if r['fine']:
                per.setdefault(r['coarse'].split(':')[1], []).append(x['ll'])
    print(f"lam_fine {lam:>8} cv logloss {tot / n:.5f}  elite {sum(per['ELITE'])/len(per['ELITE']):.5f} boss {sum(per['BOSS'])/len(per['BOSS']):.5f}")
base = sum(x['ll'] for s in ('even', 'odd') for x in c.metrics(folds[s], None)) / sum(len(folds[s]) for s in folds)
print(f"uncalibrated logloss {base:.5f}")
