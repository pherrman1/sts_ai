#!/usr/bin/env python3
"""Part A of PREREG.md: extract per-seed paired outcomes of seven recorded campaigns and replay the SPRT.
usage: replay.py OUT_DIR   (reads docs/experiments/evidence/* and the unit tars on /mnt/project-files)
Writes OUT_DIR/pairs_<sec>.csv (key,a,b or key,d), OUT_DIR/replay.json."""
import csv, glob, gzip, io, json, os, re, sys, tarfile
from collections import defaultdict
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(EV, '..', '..', '..', 'tools'))
import sprt_gate  # noqa: E402

SHARE = '/mnt/project-files'


def units(d):
    return [int(x) for x in open(os.path.join(EV, d, 'units.txt')).read().split()]


def from_perseed(d, arms, idx):
    """result.json perSeed: seed -> arm -> [heart, act4, floor]."""
    ps = json.load(open(os.path.join(EV, d, 'result.json')))['perSeed']
    return {int(s): {a: v[a][idx] for a in arms} for s, v in ps.items()}


def tar_outcomes(share_dir, arms):
    """Unit tars: per arm the last jsonl row must be a complete outcome (integrityPassed where recorded) and the
    arm's own .done (or the unit's .done) must say rc=0. Returns seed -> arm -> outcome row."""
    res = defaultdict(dict)
    for path in sorted(glob.glob(os.path.join(SHARE, share_dir, 'units', '*.tar'))):
        with tarfile.open(path) as t:
            m = {x.name: x for x in t.getmembers() if x.isfile()}
            rd = lambda n: t.extractfile(m[n]).read()
            unit_done = {re.search(r'/(\d+)\.done$', n).group(1): rd(n).decode() for n in m if re.search(r'/\d+\.done$', n)}
            for n in m:
                mm = re.search(r'/([A-Za-z]+)-(\d+)\.jsonl\.gz$', n)
                if not mm or mm.group(1) not in arms:
                    continue
                a, s = mm.groups()
                if a in res[int(s)]:
                    continue  # duplicate unit run (queue race); seed-deterministic, keep the first
                dn = n[:-len('.jsonl.gz')] + '.done'
                done = rd(dn).decode() if dn in m else unit_done.get(s, '')
                if not re.search(r'\brc=0\b', done):
                    continue
                rows = [json.loads(x) for x in gzip.decompress(rd(n)).splitlines() if x.strip()]
                out = [r for r in rows if r.get('type') == 'outcome']
                if not out:
                    continue
                o = out[-1]
                if not o.get('complete') or o.get('integrityPassed') is False:
                    continue
                res[int(s)][a] = o
    return res


def incense_pairs():
    """§724: per S&S state, mean over 4 replicates of (on kill - off kill); validity as its analyze.py (rc 0, 8 rows,
    valid, heartValid when won)."""
    R, ARMS = 4, ('off', 'on')
    rcs, runs = {}, defaultdict(dict)
    for path in sorted(glob.glob(os.path.join(SHARE, 'incense-term-gate', 'units', '*.tar'))):
        with tarfile.open(path) as t:
            for x in t.getmembers():
                if not x.isfile():
                    continue
                b = os.path.basename(x.name)
                m = re.match(r'u(\d+)\.done$', b)
                if m:
                    rcs[int(m.group(1))] = (re.search(r'\brc=(-?\d+)', t.extractfile(x).read().decode()) or [0, 'x'])[1]
                m = re.match(r'u(\d+)-(off|on)-r(\d)\.csv$', b)
                if m:
                    rows = list(csv.DictReader(io.StringIO(t.extractfile(x).read().decode())))
                    if len(rows) == 1 and rows[0]['encounter'] == 'SHIELD_AND_SPEAR':
                        runs[int(m.group(1))][(m.group(2), int(m.group(3)))] = rows[0]
    ok = lambda x: x['valid'] == '1' and (x['won'] != '1' or x['heartValid'] == '1')
    kill = lambda x: float(x['won'] == '1' and x['heartWon'] == '1')
    good = sorted(i for i, f in runs.items() if rcs.get(i) == '0' and len(f) == 2 * R and all(ok(x) for x in f.values()))
    out = {}
    for i in good:
        on = np.mean([kill(runs[i][('on', r)]) for r in range(R)])
        off = np.mean([kill(runs[i][('off', r)]) for r in range(R)])
        out[i] = (off, on)
    return out


CAMPAIGNS = [
    # sec, evidence dir, variant, arms (A, B), metric, recorded class, recorded rates (A, B) in %
    (661, 'value_level_ab_20261023', 'gainer', ('A', 'M'), 'heart', 'positive', 'value-level-ab'),
    (676, 'ctm_calibration_20261023', 'nonregression', ('A', 'C'), 'heart', 'not_worse', 'ctm-calibration-ab'),
    (683, 'ooc_map_only_search_20261024', 'gainer', ('OFF', 'MAP'), 'act4', 'positive', None),
    (691, 'key_rules_ab_20261026', 'gainer', ('R', 'F'), 'heart', 'positive', None),
    (693, 'gumbel_qcap_ab_20261026', 'gainer', ('A', 'B'), 'heart', 'null', 'gumbel-qcap-ab'),
    (724, 'incense_term_gate_20261030', 'gainer', ('off', 'on'), 'heart', 'positive', 'incense-term-gate'),
    (727, 'value_chooser_ab_20261031', 'gainer', ('A', 'B'), 'heart', 'negative', 'value-chooser-ab'),
]


def metric(o, which):
    if which == 'heart':
        return int(bool(o['heartKilled']))
    return int(o['finalAct'] >= 4)


def extract(c):
    sec, d, variant, (A, B), which, cls, share = c
    if sec == 724:
        p = incense_pairs()
        return [(i, p[i][0], p[i][1]) for i in sorted(p)]
    if share is None:
        ps = from_perseed(d, (A, B), 0 if which == 'heart' else 1)
        return [(s, ps[s][A], ps[s][B]) for s in sorted(ps)]
    o = tar_outcomes(share, (A, B))
    seeds = [s for s in units(d) if A in o.get(s, {}) and B in o.get(s, {})]
    return [(s, metric(o[s][A], which), metric(o[s][B], which)) for s in sorted(seeds)]


def flip(cls, accept):
    if accept is None:
        return False
    good = cls in ('positive', 'not_worse')
    return (accept == 'H1') != good


def main(out):
    os.makedirs(out, exist_ok=True)
    rng = np.random.default_rng(20261101)
    rep = {'campaigns': []}
    tot_n = tot_stop = flips = 0
    for c in CAMPAIGNS:
        sec, d, variant, arms, which, cls, _ = c
        pairs = extract(c)
        with open(os.path.join(out, f'pairs_{sec}.csv'), 'w') as f:
            f.write('key,a,b\n')
            for k, a, b in pairs:
                f.write(f'{k},{a},{b}\n')
        a = np.array([p[1] for p in pairs], float); b = np.array([p[2] for p in pairs], float)
        dd = list(b - a)
        r = sprt_gate.run(dd, variant)
        fl = flip(cls, r['accept'])
        flips += fl; tot_n += len(dd); tot_stop += r['n_stop']
        perm = []
        for _ in range(200):
            q = sprt_gate.run(list(rng.permutation(dd)), variant)
            perm.append((q['n_stop'], q['accept']))
        rep['campaigns'].append({
            'sec': sec, 'evidence': d, 'variant': variant, 'arms': arms, 'metric': which, 'recorded_class': cls,
            'n': len(dd), 'rate_A_pct': round(100 * a.mean(), 2), 'rate_B_pct': round(100 * b.mean(), 2),
            'diff_pp': round(100 * (b - a).mean(), 2),
            'sprt': {k: r[k] for k in ('verdict', 'accept', 'n_stop')}, 'llr': round(r['llr'], 3), 'looks': r['looks'],
            'flip': fl, 'saving': round(1 - r['n_stop'] / len(dd), 4),
            'perm200': {'mean_saving': round(1 - np.mean([x[0] for x in perm]) / len(dd), 4),
                        'flip_rate': round(np.mean([flip(cls, x[1]) for x in perm]), 4),
                        'cap_rate': round(np.mean([x[1] is None for x in perm]), 4)}})
    rep['flips'] = int(flips)
    rep['saving_pair_weighted'] = round(1 - tot_stop / tot_n, 4)
    rep['decision'] = 'ADOPT' if flips <= 1 and rep['saving_pair_weighted'] >= 0.10 else 'DO_NOT_ADOPT'
    json.dump(rep, open(os.path.join(out, 'replay.json'), 'w'), indent=1)
    for c in rep['campaigns']:
        print(c['sec'], c['variant'], c['n'], c['rate_A_pct'], c['rate_B_pct'], c['diff_pp'], c['sprt'], 'flip' if c['flip'] else '',
              'saving', c['saving'], 'perm', c['perm200'])
    print('flips', rep['flips'], 'saving', rep['saving_pair_weighted'], rep['decision'])


if __name__ == '__main__':
    main(sys.argv[1])
