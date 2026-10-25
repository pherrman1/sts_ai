"""Boss-relic fork pilot (#856): relic table, Stage A futility, cross-fitted override gate. Rules in PREREG.md.

usage: analyze.py UNITS_DIR [--stage A|B] [--out analysis.json] [--boot 10000]
       analyze.py --selftest
UNITS_DIR holds the unit tars (*.tar) or extracted unit directories, searched recursively.
"""
import argparse, collections, glob, gzip, io, json, os, re, sys, tarfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import forks  # noqa: E402

SKIP = 'SKIP'
N_FULL = 1024       # sources in the full design (Stage A + Stage B)
N_STAGE_A = 256
MIN_OBS = 8         # Stage A: keys with at least this many appearances enter the spread estimate
STOP_R = 0.35       # Stage A: STOP when the projected split-half r of the full design is below this
MARGIN = 0.03       # override margin on the shrunk table (P300's relicu margin)
ENDPOINTS = ('heart', 'act4')


# ---------------------------------------------------------------- reading
def unit_files(root):
    """{seed: {basename: bytes}} from unit tars or directories."""
    out = collections.defaultdict(dict)
    pat = re.compile(r'(?:^|/)((?:S|F\d_\d)-(\d+)\.(?:jsonl|trace\.jsonl)(?:\.gz)?|(?:S|F\d_\d)-(\d+)\.(?:done|check))$')

    def add(name, data):
        m = pat.search(name)
        if m:
            out[int(m.group(2) or m.group(3))][m.group(1)] = data
    for p in glob.glob(f'{root}/**/*', recursive=True):
        if p.endswith('.tar'):
            with tarfile.open(p) as t:
                for m in t.getmembers():
                    if m.isfile():
                        add(m.name, t.extractfile(m).read())
        elif os.path.isfile(p):
            add(p, open(p, 'rb').read())
    return out


def jsonl(data, name):
    if name.endswith('.gz'):
        data = gzip.decompress(data)
    return [json.loads(l) for l in io.StringIO(data.decode()) if l.strip()]


def get(files, stem):
    for name in (stem, stem + '.gz'):
        if name in files:
            return jsonl(files[name], name)
    return None


def game(files, tag, seed):
    """Outcome of one game, or None when it is missing or failed."""
    done = files.get(f'{tag}-{seed}.done', b'').decode()
    if ' rc=0 ' not in done:
        return None
    rows = get(files, f'{tag}-{seed}.jsonl')
    trace = get(files, f'{tag}-{seed}.trace.jsonl')
    if not rows or rows[-1].get('type') != 'outcome' or not rows[-1].get('complete') or trace is None:
        return None
    o = rows[-1]
    heart_hp = next((r['pre']['hp'] for r in trace if r.get('kind') == 'battle' and r['pre']['act'] == 4
                     and r['pre']['room'] == 'BOSS'), None)
    wall = int(re.search(r'wall=(\d+)', done).group(1))
    return {'heart': int(o['heartKilled']), 'act4': int(o['finalAct'] >= 4), 'floor': o['finalFloor'],
            'heartHp': heart_hp, 'wall': wall, 'trace': trace}


def load(root):
    """Roots: one dict per act-1/2 boss-relic root of a valid source, with every option's outcome."""
    roots, problems, walls, valid = [], collections.Counter(), [], set()
    for seed, files in sorted(unit_files(root).items()):
        src = game(files, 'S', seed)
        if src is None:
            problems['source_failed'] += 1
            continue
        walls.append(src['wall'])
        valid.add(seed)
        for r in forks.roots(src['trace']):
            options = list(r['offered']) + [SKIP]
            out = {r['taken']: src}
            for choice in range(len(options)):
                if choice == r['taken']:
                    continue
                g = game(files, f"F{r['act']}_{choice}", seed)
                if g is not None:
                    walls.append(g['wall'])
                    forks.check(src['trace'], g['trace'], f"{r['act']}:{choice}")  # raises on a broken fork
                    out[choice] = g
            if len(out) != len(options):
                problems['root_incomplete'] += 1   # PREREG: the whole root is dropped
                continue
            roots.append({'seed': seed, 'act': r['act'], 'keys': options, 'prior': r['taken'], 'by': r['by'],
                          'y': {e: [out[c][e] for c in range(len(options))] for e in ENDPOINTS},
                          'heartHp': [out[c]['heartHp'] for c in range(len(options))]})
    return roots, problems, walls, valid


# ---------------------------------------------------------------- table
def fit(roots, endpoint):
    """Root fixed-effects OLS: y_rj = a_r + u_key + e, u_SKIP = 0. Returns {key: u}, {key: appearances}."""
    keys = sorted({k for r in roots for k in r['keys'] if k != SKIP})
    col = {k: i for i, k in enumerate(keys)}
    X, Y = [], []
    for r in roots:
        x = np.zeros((len(r['keys']), len(keys)))
        for j, k in enumerate(r['keys']):
            if k != SKIP:
                x[j, col[k]] = 1
        y = np.array(r['y'][endpoint], float)
        X.append(x - x.mean(0)); Y.append(y - y.mean())
    if not keys:
        return {SKIP: 0.0}, {}
    u = np.linalg.lstsq(np.vstack(X), np.concatenate(Y), rcond=None)[0]
    n = collections.Counter(k for r in roots for k in r['keys'] if k != SKIP)
    return {SKIP: 0.0, **{k: float(u[col[k]]) for k in keys}}, dict(n)


def boot_sources(roots, rng, boot):
    by = collections.defaultdict(list)
    for r in roots:
        by[r['seed']].append(r)
    seeds = sorted(by)
    for _ in range(boot):
        yield [r for s in rng.choice(seeds, len(seeds)) for r in by[s]]


def spread(roots, endpoint, rng, boot, n_sources):
    """Method-of-moments spread of true key effects and the projected split-half r of the full design."""
    u, n = fit(roots, endpoint)
    keys = [k for k in n if n[k] >= MIN_OBS]
    draws = collections.defaultdict(list)
    for b in boot_sources(roots, rng, boot):
        ub, _ = fit(b, endpoint)
        for k in keys:
            if k in ub:
                draws[k].append(ub[k])
    se2 = np.array([np.var(draws[k], ddof=1) for k in keys])
    est = np.array([u[k] for k in keys])
    tau2 = float(max(0.0, np.var(est, ddof=1) - se2.mean())) if len(keys) > 2 else 0.0
    half_se2 = float(se2.mean() * n_sources / (N_FULL / 2))
    r_proj = tau2 / (tau2 + half_se2) if tau2 + half_se2 > 0 else 0.0
    return {'keys': len(keys), 'tau': tau2 ** 0.5, 'meanSE': float(np.sqrt(se2.mean())) if keys else None,
            'projectedSplitHalfR': r_proj, 'table': {k: [u[k], float(np.sqrt(np.var(draws[k], ddof=1))), n[k]]
                                                     for k in keys}}, tau2, dict(zip(keys, se2))


def shrunk(u, n, tau2, noise_var):
    """Empirical-Bayes shrinkage toward 0 (= skip); noise variance per appearance from the training fold."""
    if tau2 <= 0:
        return {k: 0.0 for k in u}  # no spread: every key shrinks to skip, so the override never fires
    return {k: (v if k == SKIP else v * tau2 / (tau2 + noise_var / max(1, n.get(k, 0)))) for k, v in u.items()}


def noise_per_obs(roots, endpoint):
    """Residual variance of y_rj - ybar_r after the key fit, scaled to one appearance."""
    u, _ = fit(roots, endpoint)
    res = []
    for r in roots:
        y = np.array(r['y'][endpoint], float)
        m = np.array([u.get(k, 0.0) for k in r['keys']])
        e = (y - y.mean()) - (m - m.mean())
        res.extend(e * np.sqrt(len(e) / (len(e) - 1)))
    return float(np.var(res)) * 4 / 3 if res else 0.0


def override_gain(train, test, endpoint, rng, boot):
    """Per-root gain of the table override over the prior pick on held-out roots (both decided by `endpoint`'s
    training table); returns {(seed, act): (pick, gain_heart, gain_act4)}."""
    u, n = fit(train, endpoint)
    _, tau2, _ = spread(train, endpoint, rng, boot, len({r['seed'] for r in train}))
    t = shrunk(u, n, tau2, noise_per_obs(train, endpoint))
    out = {}
    for r in test:
        vals = [t.get(k, 0.0) if k != SKIP else 0.0 for k in r['keys']]
        best = int(np.argmax(vals))
        pick = best if vals[best] - vals[r['prior']] > MARGIN else r['prior']
        out[(r['seed'], r['act'])] = (pick, *(r['y'][e][pick] - r['y'][e][r['prior']] for e in ENDPOINTS))
    return out


def ci(per_source, rng, boot):
    v = np.array(list(per_source.values()), float)
    m = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(boot)]
    return float(v.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


# ---------------------------------------------------------------- report
def describe(roots):
    d = {'roots': len(roots), 'byAct': dict(collections.Counter(r['act'] for r in roots)),
         'priorBy': dict(collections.Counter(r['by'] for r in roots)),
         'priorSkips': sum(r['keys'][r['prior']] == SKIP for r in roots)}
    for e in ENDPOINTS:
        prior = np.array([r['y'][e][r['prior']] for r in roots], float)
        alts = np.array([np.mean([y for j, y in enumerate(r['y'][e]) if j != r['prior']]) for r in roots])
        skip = np.array([r['y'][e][-1] for r in roots], float)
        d[e] = {'prior': prior.mean(), 'meanAlternative': alts.mean(), 'skip': skip.mean(),
                'priorMinusAlternatives': float((prior - alts).mean())}
        pairs = [(r['y'][e][i], r['y'][e][j]) for r in roots for i in range(4) for j in range(i + 1, 4)]
        a = np.array(pairs, float)
        d[e]['crnCorrelation'] = float(np.corrcoef(a[:, 0], a[:, 1])[0, 1]) if len(a) > 2 else None
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('units', nargs='?')
    ap.add_argument('--stage', default='B', choices='AB')
    ap.add_argument('--out', default='analysis.json')
    ap.add_argument('--boot', type=int, default=10000)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    roots, problems, walls, valid = load(a.units)
    n_sources = len(valid)
    rng = np.random.default_rng(20261025)
    # The projection scales by valid sources, rooted or not (a source without a root is part of the design too).
    res = {'stage': a.stage, 'problems': dict(problems), 'validSources': n_sources,
           'sourcesWithRoots': len({r['seed'] for r in roots}),
           'coreHours': sum(walls) / 3600, 'gamesValid': len(walls), 'describe': describe(roots)}
    for e in ENDPOINTS:
        res[f'spread_{e}'] = spread(roots, e, rng, min(a.boot, 2000), n_sources)[0]
    r = res['spread_heart']['projectedSplitHalfR']
    if a.stage == 'A':
        res['verdict'] = 'STOP' if r < STOP_R else 'ASK_STAGE_B'
    else:
        folds = [[x for x in roots if x['seed'] % 2 == f] for f in (0, 1)]
        for e in ENDPOINTS:
            per_root = {}
            for f in (0, 1):
                per_root.update(override_gain(folds[1 - f], folds[f], e, rng, min(a.boot, 2000)))
            per_source = collections.defaultdict(lambda: [0.0, 0.0])
            for seed in valid:
                per_source[seed]  # every valid source counts, with gain 0 where nothing fires or it has no root
            for (seed, _), (_, gh, g4) in per_root.items():
                per_source[seed][0] += gh; per_source[seed][1] += g4
            fired = sum(p != x['prior'] for x in roots for (s, act), (p, *_) in per_root.items()
                        if (s, act) == (x['seed'], x['act']))
            res[f'override_{e}'] = {'overrideRate': fired / max(1, len(roots)),
                                    'gainHeart': ci({s: v[0] for s, v in per_source.items()}, rng, a.boot),
                                    'gainAct4': ci({s: v[1] for s, v in per_source.items()}, rng, a.boot)}
        m, lo, hi = res['override_heart']['gainHeart']
        res['verdict'] = 'PASS' if lo > 0 else 'FAIL' if m <= 0 else 'INCONCLUSIVE'
    json.dump(res, open(a.out, 'w'), indent=1, default=float)
    print(json.dumps({k: res[k] for k in res if k.startswith(('verdict', 'override', 'problems', 'sources'))},
                     default=float))


def selftest():
    """Synthetic roots: a planted relic effect is recovered and the override gains; no effects -> no spread."""
    rng = np.random.default_rng(1)
    relics = [f'R{i}' for i in range(20)]
    for planted, want in ((0.15, True), (0.0, False)):
        eff = {k: (planted if i < 5 else -planted if i < 10 else 0.0) for i, k in enumerate(relics)}
        roots = []
        for seed in range(N_FULL):
            for act in (1, 2):
                offer = list(rng.choice(relics, 3, replace=False))
                keys = offer + [SKIP]
                base = rng.random() < 0.25
                y = {}
                for e in ENDPOINTS:
                    p = [np.clip(0.25 + eff.get(k, 0.0), 0, 1) for k in keys]
                    y[e] = [int(base if rng.random() < 0.4 else rng.random() < pj) for pj in p]
                roots.append({'seed': seed, 'act': act, 'keys': keys, 'prior': int(rng.integers(0, 3)),
                              'by': 'heart1_screen', 'y': y, 'heartHp': [None] * 4})
        s, _, _ = spread(roots, 'heart', rng, 200, N_FULL)
        folds = [[x for x in roots if x['seed'] % 2 == f] for f in (0, 1)]
        g = {}
        for f in (0, 1):
            g.update(override_gain(folds[1 - f], folds[f], 'heart', rng, 200))
        mean_gain = np.mean([v[1] for v in g.values()])
        ok = (s['projectedSplitHalfR'] > 0.6 and mean_gain > 0.02) if want else \
            (s['projectedSplitHalfR'] < STOP_R and abs(mean_gain) < 0.02)
        print(f"planted={planted} splitHalfR={s['projectedSplitHalfR']:.2f} tau={s['tau']:.3f} gain/root={mean_gain:+.3f}")
        if not ok:
            raise SystemExit('selftest failed')
    print('boss relic fork analysis selftest passed')


if __name__ == '__main__':
    main()
