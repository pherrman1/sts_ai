"""analyze.py OUT.json UNIT_DIR... -- Stage 0 campfire price gates from campfire-price-v1 rows (STS_OOC_CAMPFIRE_PRICE).

Each UNIT_DIR holds P-SEED.price.jsonl (prices) and P-SEED.jsonl (the replayed game, for the played choice).
Per rest site with a legal Rest (acts 1-3): class values Rest, Smith (best target), Recall, under two prices:
'actEnd' (rollout to the act's end, calibrated X2-B there; deaths 0) and 'leaf' (the search's own rollout3 leaf).
The best Smith target is picked on even repeats and valued on odd ones (no max bias); Rest is valued on the same
odd repeats, so the Rest - Smith difference is paired (common random numbers).
Gates (PLAN): (a) |Rest - Smith| > 2 SE on most sites; (b) the difference falls with HP fraction (Spearman < 0);
(c) the price's class differs from the played class on >= 10% of sites."""
import glob, gzip, json, math, os, re, sys
from statistics import mean, stdev

EFF = {0: 'smith', 1: 'toke', 17: 'rest', 18: 'recall', 19: 'lift', 20: 'dig'}

def load(path):
    out = []
    with (gzip.open(path, 'rt') if path.endswith('.gz') else open(path)) as f:
        for l in f:
            try: out.append(json.loads(l))
            except json.JSONDecodeError: break   # a game stopped at act 4 may end in a cut line
    return out

def effect(key):
    return EFF.get(int(re.search(r'effect=(\d+)', key).group(1)), 'other')

def played(game_rows):
    """floor -> played class at that rest site, inferred from the next non-campfire state (as in §687)."""
    states = {r['index']: r for r in game_rows if r['type'] == 'state'}
    fo = lambda s: s['record']['obs.fixed_observation']
    ups = lambda s: sum(s['record']['obs.deck.upgrades'])
    out = {}
    for i, s in sorted(states.items()):
        if s.get('screen') != 7 or s['floor'] in out: continue
        for j in range(i + 1, i + 6):
            t = states.get(j)
            if t is None or t.get('screen') in (7, 4): continue
            f, g = fo(s), fo(t)
            out[s['floor']] = 'recall' if g[7] > f[7] else 'smith' if ups(t) > ups(s) else 'rest' if g[0] > f[0] else 'other'
            break
    return out

def values(action, kind, idx):
    v = action.get(kind, [])
    return [v[i]['value'] if 'value' in v[i] else None for i in idx if i < len(v)]

def site(row, played_class):
    acts = row['price']['actions']
    n = row['n']
    even, odd = list(range(0, n, 2)), list(range(1, n, 2))
    res = {k: row[k] for k in ('seed', 'act', 'floor', 'hp', 'maxHp')}
    res['played'] = played_class
    res['nOptions'] = len(acts)
    for kind in ('actEnd', 'leaf'):
        by = {}
        for a in acts:
            e = effect(a['key'])
            ev = values(a, kind, even)
            if None in ev or not ev: return None
            if e not in by or mean(ev) > mean(values(by[e], kind, even)): by[e] = a
        if 'rest' not in by: return None
        cls = {e: mean(values(a, kind, odd)) for e, a in by.items()}
        res[kind] = cls
        res[kind + 'Best'] = max(cls, key=cls.get)
        if 'smith' in by:
            d = [x - y for x, y in zip(values(by['rest'], kind, odd), values(by['smith'], kind, odd))]
            res[kind + 'Diff'] = mean(d)
            res[kind + 'Se'] = stdev(d) / math.sqrt(len(d)) if len(d) > 1 else float('nan')
            res[kind + 'SmithTarget'] = by['smith']['label']
    return res

def spearman(x, y):
    def rank(v):
        o = sorted(range(len(v)), key=v.__getitem__); r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[o[j + 1]] == v[o[i]]: j += 1
            for k in range(i, j + 1): r[o[k]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = rank(x), rank(y); mx, my = mean(rx), mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float('nan')

def spearman_ci(both, kind, reps=2000):
    """Percentile bootstrap over source seeds (sites of one game move together)."""
    import random
    if len(both) < 3: return None
    rng = random.Random(20261026)
    seeds = sorted({s['seed'] for s in both})
    by = {k: [s for s in both if s['seed'] == k] for k in seeds}
    vals = []
    for _ in range(reps):
        sample = [s for k in (rng.choice(seeds) for _ in seeds) for s in by[k]]
        r = spearman([s[kind + 'Diff'] for s in sample], [s['hp'] / s['maxHp'] for s in sample])
        if r == r: vals.append(r)
    vals.sort()
    return [round(vals[int(.025 * len(vals))], 3), round(vals[int(.975 * len(vals)) - 1], 3)] if vals else None

def main(out, dirs):
    sites, errors = [], 0
    for d in dirs:
        for p in glob.glob(os.path.join(d, 'P-*.price.jsonl')):
            game = p.replace('.price.jsonl', '.jsonl')
            game = game if os.path.exists(game) else game + '.gz'
            pl = played(load(game))
            for row in load(p):
                if 'price' not in row or row['act'] > 3: errors += 'priceError' in row; continue
                s = site(row, pl.get(row['floor']))
                if s: sites.append(s)
    report = {'sites': len(sites), 'priceErrors': errors}
    for kind in ('actEnd', 'leaf'):
        both = [s for s in sites if kind + 'Diff' in s]
        sep = [abs(s[kind + 'Diff']) > 2 * s[kind + 'Se'] for s in both if s[kind + 'Se'] == s[kind + 'Se']]
        hpf = [s['hp'] / s['maxHp'] for s in both]
        dis = [s for s in sites if s['played'] in ('rest', 'smith', 'recall')]
        bands = {}
        for lo, hi in ((0, .4), (.4, .6), (.6, .8), (.8, 1.01)):
            b = [s for s in dis if lo <= s['hp'] / s['maxHp'] < hi]
            if b:
                bands[f'{lo:.1f}-{min(hi, 1):.1f}'] = {'n': len(b),
                    'playedRest': round(sum(s['played'] == 'rest' for s in b) / len(b), 3),
                    'priceRest': round(sum(s[kind + 'Best'] == 'rest' for s in b) / len(b), 3),
                    'meanRestMinusSmith': round(mean(s[kind + 'Diff'] for s in b if kind + 'Diff' in s), 4)
                        if any(kind + 'Diff' in s for s in b) else None}
        report[kind] = {
            'sitesWithSmith': len(both),
            'a_separable2se': round(sum(sep) / len(sep), 3) if sep else None,
            'meanAbsDiff': round(mean(abs(s[kind + 'Diff']) for s in both), 4) if both else None,
            'medianSe': round(sorted(s[kind + 'Se'] for s in both)[len(both) // 2], 4) if both else None,
            'b_spearmanDiffVsHpFrac': round(spearman([s[kind + 'Diff'] for s in both], hpf), 3) if len(both) > 2 else None,
            'b_spearmanCi95': spearman_ci(both, kind),
            'c_disagree': round(sum(s[kind + 'Best'] != s['played'] for s in dis) / len(dis), 3) if dis else None,
            'byHpBand': bands}
    json.dump({'report': report, 'sites': sites}, open(out, 'w'), indent=1)
    print(json.dumps(report, indent=1))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
