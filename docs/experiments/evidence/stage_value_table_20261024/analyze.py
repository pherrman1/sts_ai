"""Stage-value table pilot (Heart stage): table, Stage A futility, gates (a)-(c). Rules in PREREG.md.

usage: analyze.py UNITS_DIR [--stage A|B] [--roots D_TRACE_GLOB] [--out analysis.json] [--boot 2000]
UNITS_DIR holds the unit tars (deck-N.wWW.tar) or their extracted CSVs (deck-N.vXX.csv), searched recursively.
--roots: #854 arm-D decision traces (D-*.jsonl.gz) for the descriptive gate (c).
"""
import argparse, collections, csv, glob, gzip, io, json, math, os, random, re, statistics as st, tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('units')
ap.add_argument('--stage', default='B')
ap.add_argument('--roots')
ap.add_argument('--out', default='analysis.json')
ap.add_argument('--boot', type=int, default=2000)
a = ap.parse_args()
rng = random.Random(855)

lines = [json.loads(l) for l in gzip.open(f'{HERE}/variants.jsonl.gz')]
meta = {(l['deckIndex'], l['variantIndex']): l for l in lines}
N_DECKS = 96 if a.stage == 'A' else 392


def csv_texts():
    for p in glob.glob(f'{a.units}/**/*', recursive=True):
        name = os.path.basename(p)
        if name.endswith('.tar'):
            with tarfile.open(p) as t:
                for m in t.getmembers():
                    if re.search(r'deck-\d+\.v\d\d\.csv$', m.name):
                        yield m.name, t.extractfile(m).read().decode()
        elif re.fullmatch(r'deck-\d+\.v\d\d\.csv', name):
            yield p, open(p).read()


won = {}  # (deck, variant, replicate) -> 0/1; invalid fights and errors are absent
cpu, invalid, errors, seen = [], 0, 0, set()
for name, text in csv_texts():
    d, v = map(int, re.search(r'deck-(\d+)\.v(\d\d)\.csv', name).groups())
    if (d, v) in seen:
        continue  # a unit delivered twice
    seen.add((d, v))
    for r in csv.DictReader(io.StringIO(text)):
        if r['encounter'] == 'ERROR':
            errors += 1
            continue
        assert r['id'] == meta[(d, v)]['state']['id'], (name, r['id'])
        if r['valid'] != '1':
            invalid += 1
            continue
        won[(d, v, int(r['replicate']))] = int(r['won'])
        cpu.append(float(r['cpuSeconds']))

# Per (deck, key): mean over copies of won(variant) - won(base), on copies where both are valid.
obs = collections.defaultdict(dict)  # key -> {deck: delta}
crn_pairs, base_won = [], collections.defaultdict(list)
decks = sorted({d for d, _, _ in won if d < N_DECKS})
for d in decks:
    for r in range(4):
        if (d, 0, r) in won:
            base_won[d].append(won[(d, 0, r)])
    for v in range(1, 25):
        ds = [won[(d, v, r)] - won[(d, 0, r)] for r in range(4) if (d, v, r) in won and (d, 0, r) in won]
        crn_pairs += [(won[(d, 0, r)], won[(d, v, r)]) for r in range(4) if (d, v, r) in won and (d, 0, r) in won]
        if ds:
            obs[meta[(d, v)]['key']][d] = sum(ds) / len(ds)
half = {d: meta[(d, 0)]['half'] for d in decks}
seed_of = {d: meta[(d, 0)]['sourceSeed'] for d in decks}
deck_keys = [k for k in obs if not k.startswith('hp:')]


def table(ds):
    """Key means over the decks in ds."""
    out = {}
    for k in deck_keys:
        x = [obs[k][d] for d in ds if d in obs[k]]
        if x:
            out[k] = (sum(x) / len(x), len(x), st.variance(x) if len(x) > 1 else 0.0)
    return out


def pearson(x, y):
    return st.correlation(x, y) if len(x) > 2 and len(set(x)) > 1 and len(set(y)) > 1 else float('nan')


def spearman(x, y):
    def ranks(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
                j += 1
            for t in range(i, j + 1):
                rk[o[t]] = (i + j) / 2
            i = j + 1
        return rk
    return pearson(ranks(x), ranks(y))


def gate_a(ds):
    h = [[d for d in ds if half[d] == s] for s in (0, 1)]
    t0, t1 = table(h[0]), table(h[1])
    ks = [k for k in deck_keys if k in t0 and k in t1 and t0[k][1] >= 20 and t1[k][1] >= 20]
    return pearson([t0[k][0] for k in ks], [t1[k][0] for k in ks]), len(ks)


def per_deck_spearman(train, test):
    t = table(train)
    out = {}
    for d in test:
        pairs = [(t[k][0] if k in t else 0.0, obs[k][d]) for k in deck_keys if d in obs[k]]
        if len(pairs) >= 3:
            s = spearman([p for p, _ in pairs], [o for _, o in pairs])
            if not math.isnan(s):
                out[d] = s
    return out


def gate_b(ds):
    h = [[d for d in ds if half[d] == s] for s in (0, 1)]
    out = per_deck_spearman(h[0], h[1])
    out.update(per_deck_spearman(h[1], h[0]))
    return out


def boot_mean_over_seeds(per_deck):
    """95% percentile CI of the mean of per-deck values, resampling source seeds (an A/C pair stays together).
    The tables stay fitted on the original halves; only the held-out decks are resampled."""
    by = collections.defaultdict(list)
    for d, x in per_deck.items():
        by[seed_of[d]].append(x)
    seeds = sorted(by)
    vals = sorted(st.mean([x for s in (rng.choice(seeds) for _ in seeds) for x in by[s]]) for _ in range(a.boot))
    return [vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]] if vals else [None, None]


res = {'stage': a.stage, 'decks': len(decks), 'fights': len(won), 'invalid': invalid, 'errors': errors,
       'cpuSecondsMean': st.mean(cpu) if cpu else None}
# CRN correlation of base and variant outcomes (same copy), and base fidelity vs the observed entry outcome.
res['crnCorrelation'] = pearson([b for b, _ in crn_pairs], [v for _, v in crn_pairs])
res['baseWinRate'] = st.mean([w for d in decks for w in base_won[d]]) if decks else None
res['observedWinRate'] = st.mean([meta[(d, 0)]['observedWon'] for d in decks]) if decks else None
full = table(decks)
for k in ('hp:-8', 'hp:-16'):
    x = list(obs[k].values())
    res[k] = {'mean': st.mean(x), 'se': st.pstdev(x) / math.sqrt(len(x)), 'n': len(x)} if x else None

# Futility projection (Stage A rule). Spread of true key effects by DerSimonian-Laird over add/up/rm keys with
# >= 8 decks, using the pooled per-deck variance of delta (more stable than per-key variances at small n). The
# projected half-SE^2 of the 392-deck design scales each key's deck count by 392 / decks so far.
ks8 = [k for k, (m, n, v) in full.items() if n >= 8]
if len(ks8) > 2:
    s2 = sum(full[k][2] * (full[k][1] - 1) for k in ks8) / sum(full[k][1] - 1 for k in ks8)
    w = [full[k][1] / s2 for k in ks8]
    m = [full[k][0] for k in ks8]
    mbar = sum(wi * mi for wi, mi in zip(w, m)) / sum(w)
    q = sum(wi * (mi - mbar) ** 2 for wi, mi in zip(w, m))
    tau2 = max(0.0, (q - (len(ks8) - 1)) / (sum(w) - sum(wi * wi for wi in w) / sum(w)))
    scale = 392 / max(1, len(decks))
    half_se2 = [s2 / (full[k][1] * scale / 2) for k in ks8 if full[k][1] * scale / 2 >= 20]
    proj = tau2 / (tau2 + st.mean(half_se2)) if half_se2 and tau2 > 0 else 0.0
    res['futility'] = {'keys': len(ks8), 'sigmaKeys': math.sqrt(tau2), 'perDeckSD': math.sqrt(s2),
                       'projectedSplitHalfR': proj, 'projectedKeys': len(half_se2),
                       'rule': 'STOP' if proj < 0.35 else 'CONTINUE'}

r_a, n_a = gate_a(decks)
res['gateA'] = {'r': r_a, 'keys': n_a, 'pass': (r_a >= 0.6) if not math.isnan(r_a) else False}
sp = gate_b(decks)
mean_sp = st.mean(sp.values()) if sp else float('nan')
ci = boot_mean_over_seeds(sp) if sp else [None, None]
res['gateB'] = {'meanSpearman': mean_sp, 'ci95': ci, 'decks': len(sp), 'pass': bool(ci[0] is not None and ci[0] > 0)}
if a.stage == 'B':
    res['verdict'] = 'PASS' if res['gateA']['pass'] and res['gateB']['pass'] else 'FAIL'
ranked = sorted(((k, m, math.sqrt(v / n) if n > 1 else None, n) for k, (m, n, v) in full.items() if n >= 20),
                key=lambda x: x[1])
res['bottom15'], res['top15'] = ranked[:15], ranked[-15:][::-1]
res['spreadByKind'] = {kind: st.pstdev([m for k, (m, n, v) in full.items() if k.startswith(kind) and n >= 20] or [0])
                       for kind in ('add', 'up', 'rm')}

# Gate (c), descriptive: card-reward roots of the #854 arm-D traces.
if a.roots:
    import re as _re
    names = [x.strip().strip('"') for x in _re.search(r'\bcardNames\[\]\s*=?\s*\{(.*?)\};', open(
        f'{HERE}/../../../../include/constants/Cards.h').read(), _re.S).group(1).split(',') if x.strip()]
    roots = disagree = 0
    for f in glob.glob(a.roots):
        for line in gzip.open(f):
            r = json.loads(line)
            if r.get('type') != 'decision' or r.get('screen') != 2 or not r.get('root'):
                continue
            cands = r['root'].get('candidates') or []
            opts = []
            for c in cands:
                m = _re.search(r'reward=card,(\d+),', c['key'])
                if 'reward=none' in c['key']:
                    opts.append((c['prior'], 0.0, 0.0))
                elif m and f"add:{names[int(m.group(1))]}" in full:
                    mm, n, v = full[f"add:{names[int(m.group(1))]}"]
                    opts.append((c['prior'], mm, v / n if n > 1 else 0.0))
            if len(opts) != len(cands) or len(opts) < 2:
                continue
            roots += 1
            p = max(opts, key=lambda o: o[0])
            b = max(opts, key=lambda o: o[1])
            if b is not p and b[1] - p[1] > 2 * math.sqrt(b[2] + p[2]):
                disagree += 1
    res['gateC'] = {'roots': roots, 'disagreeShare': disagree / roots if roots else None}

json.dump(res, open(a.out, 'w'), indent=1)
print(json.dumps({k: v for k, v in res.items() if k not in ('top15', 'bottom15')}, indent=1))
