"""§426 paired comparison: arm `lizard` (this run) vs §425 `rollout3` and `prod`, on decisions state-verified
in this run that have a heuristic choice. Same metrics and fallback rule as §425 score.py (live pick = MCTS pick
if it is a labeled option, else the gold-run choice; 4 searches per decision weighted equally).
usage: python3 compare.py SCORE_PY_DIR SEARCHES_425_DIR   (gold_all.pkl and out/lizard in ~/g)"""
import sys, os, json, gzip, collections, importlib.util
sys.argv, (score_dir, s425) = [sys.argv[0]], sys.argv[1:3]
G = os.path.expanduser('~/g')
_keep = open(f'{G}/report.json').read() if os.path.exists(f'{G}/report.json') else None
spec = importlib.util.spec_from_file_location('score', os.path.join(score_dir, 'score.py'))
sc = importlib.util.module_from_spec(spec); spec.loader.exec_module(sc)   # prints the §425 baseline lines; it rewrites report.json
if _keep is not None: open(f'{G}/report.json', 'w').write(_keep)
G = os.path.expanduser('~/g')
def picks425(arm):
    p, info = collections.defaultdict(list), collections.defaultdict(list)
    for l in gzip.open(os.path.join(s425, f'searches-{arm}.jsonl.gz'), 'rt'):
        r = json.loads(l); k = (r['seed'], r['decIdx'])
        p[k].append(r['selectedBits'] if r['selected'] else None); info[k].append(r)
    return p, info
arms = {'lizard': sc.load('lizard'), 'rollout3_425': picks425('rollout3'), 'prod_425': picks425('prod')}
valid = sc.valid_targets('lizard')
ks = [k for k in sorted(sc.multi) if k in valid and sc.heur(k) and all(k in a[0] for a in arms.values())]
def live(p):
    return lambda k: [b if (b is not None and b in sc.dec[k]) else sc.heur(k)[0] for b in p[k]]
rep = {'n': len(ks)}
fmt = lambda a: f'{a[0]:+.3f} [{a[1]:+.3f},{a[2]:+.3f}]'
print(f'\n== paired on {len(ks)} decisions verified in this run, searched by all three arms')
for name, (p, info) in arms.items():
    v = [sc.per_decision(k, live(p)(k)) for k in ks]
    n = sum(len(info[k]) for k in ks); ab = collections.Counter(
        (r['abortReason'] or 'boundary') for k in ks for r in info[k] if not r['selected'])
    rep[name] = {'regret': sc.boot([x[2] for x in v]), 'tieshare': sc.boot([x[1] for x in v]),
                 'searches': n, 'noSelection': dict(ab), 'noSelectionRate': sum(ab.values()) / n}
    print(f'{name:14s} regret {fmt(rep[name]["regret"])} tie {fmt(rep[name]["tieshare"])} '
          f'no-selection {sum(ab.values())}/{n} {dict(ab)}')
L = [sc.per_decision(k, live(arms['lizard'][0])(k)) for k in ks]
for other in ('rollout3_425', 'prod_425'):
    O = [sc.per_decision(k, live(arms[other][0])(k)) for k in ks]
    d = {'deltaRegret': sc.boot([a[2] - b[2] for a, b in zip(L, O)]),
         'deltaTieshare': sc.boot([a[1] - b[1] for a, b in zip(L, O)])}
    rep['lizard_minus_' + other] = d
    print(f'lizard - {other:13s} dRegret {fmt(d["deltaRegret"])} dTie {fmt(d["deltaTieshare"])}')
json.dump(rep, open(f'{G}/compare.json', 'w'), indent=1)
