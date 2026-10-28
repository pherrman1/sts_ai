"""#882 fork analysis: python3 -I analyze.py UNITS_DIR SOURCE_UNITS_DIR [OUT.json]

UNITS_DIR holds the campaign's unit tars (<id>.wWW.tar) or unpacked unit dirs; SOURCE_UNITS_DIR the §683 unit tars
(/mnt/project-files/ooc-map-only-search/units). Reads fork_roots.jsonl next to this file. PREREG.md fixes the rules.
Per game: valid = rc 0, an outcome row, and its states equal the §683 MAP game's states up to the root's state.
Per root r and salt s: d = y(A) - y(B) (A = alternative, B = production), y = Heart kill (primary) or Act 4 reached.
Root effect = mean over its valid salts; pooled effect = mean over roots; CI = two-stage bootstrap (roots, then
salts within each root), 10,000 resamples, RNG 20261028."""
import sys, os, json, gzip, glob, re, tarfile, collections
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT, RNG = 10000, 20261028


def records(read):
    rows = [json.loads(l) for l in read().splitlines() if l.strip()]
    states = [json.dumps(r.get('record'), sort_keys=True) for r in rows if r.get('type') == 'state']
    dec = {r['decisionIndex']: r for r in rows if r.get('type') == 'decision' and 'decisionIndex' in r}
    out = next((r for r in rows if r.get('type') == 'outcome'), None)
    return states, dec, out


def source_states(src_dir, seed):
    t = tarfile.open(glob.glob(os.path.join(src_dir, f'{seed}.w*.tar'))[0])
    m = {x.name: x for x in t.getmembers()}
    n = next(k for k in m if k.endswith(f'MAP-{seed}.jsonl.gz'))
    return records(lambda: gzip.decompress(t.extractfile(m[n]).read()))


def games(units_dir):
    """Yields (tag, reader, done_text) for every game in tars or plain dirs."""
    for path in sorted(glob.glob(os.path.join(units_dir, '*.tar'))):
        t = tarfile.open(path)
        m = {x.name: x for x in t.getmembers() if x.isfile()}
        for n in m:
            mm = re.search(r'/([AB]-\d+-\d+-\d+)\.done$', n)
            if not mm:
                continue
            tag = mm.group(1)
            j = next((k for k in m if k.endswith(f'/{tag}.jsonl.gz')), None)
            yield tag, (lambda j=j, t=t, m=m: gzip.decompress(t.extractfile(m[j]).read()) if j else b''), \
                t.extractfile(m[n]).read().decode()
    for done in sorted(glob.glob(os.path.join(units_dir, '**', '[AB]-*.done'), recursive=True)):
        tag = os.path.basename(done)[:-5]
        j = done[:-5] + '.jsonl.gz'
        yield tag, (lambda j=j: gzip.open(j).read() if os.path.exists(j) else b''), open(done).read()


def boot_two_stage(per_root, rng):
    """per_root: list of arrays of salt differences. Mean over roots of mean over salts; two-stage bootstrap CI."""
    roots = [np.asarray(v, float) for v in per_root if len(v)]
    point = float(np.mean([v.mean() for v in roots]))
    stats = np.empty(BOOT)
    for b in range(BOOT):
        pick = rng.integers(0, len(roots), len(roots))
        stats[b] = np.mean([roots[i][rng.integers(0, len(roots[i]), len(roots[i]))].mean() for i in pick])
    return point, float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5)), len(roots)


def main():
    units, src = sys.argv[1], sys.argv[2]
    roots = [json.loads(l) for l in open(os.path.join(HERE, 'fork_roots.jsonl'))]
    rkey = {(r['seed'], r['decisionIndex']): r for r in roots}
    srcs = {}
    res = collections.defaultdict(dict)    # (seed, index) -> salt -> {'A': (heart, act4), 'B': ...}
    invalid = []
    for tag, read, done in games(units):
        arm, seed, index, salt = tag.split('-')
        seed, index, salt = int(seed), int(index), int(salt)
        rc = re.search(r'rc=(-?\d+)', done).group(1)
        if rc != '0':
            invalid.append([tag, f'rc={rc}']); continue
        states, dec, out = records(read)
        if out is None:
            invalid.append([tag, 'no_outcome']); continue
        if seed not in srcs:
            srcs[seed] = source_states(src, seed)
        s_states, s_dec, _ = srcs[seed]
        root_state = s_dec[index]['stateIndex'] if index in s_dec and 'stateIndex' in s_dec[index] else None
        if root_state is None or states[:root_state + 1] != s_states[:root_state + 1]:
            invalid.append([tag, 'prefix_mismatch']); continue
        if arm == 'A' and dec.get(index, {}).get('by') not in (None, 'forced_decision'):
            invalid.append([tag, 'not_forced']); continue
        res[(seed, index)].setdefault(salt, {})[arm] = (int(bool(out.get('heartKilled'))), int(out.get('finalAct', 0) >= 4))
    rng = np.random.default_rng(RNG)
    per = {}
    for k, r in rkey.items():
        pairs = [v for v in res.get(k, {}).values() if 'A' in v and 'B' in v]
        per[k] = {'heart': [v['A'][0] - v['B'][0] for v in pairs], 'act4': [v['A'][1] - v['B'][1] for v in pairs],
                  'baseHeart': float(np.mean([v['B'][0] for v in pairs])) if pairs else None, 'pairs': len(pairs)}
    groups = {'all': list(rkey), 'search_departs': [k for k in rkey if {'puctChg', 'deepChg'} & set(rkey[k]['why'])],
              'leaf_only': [k for k in rkey if rkey[k]['why'] == ['uniDis']]}
    for sc in sorted({r['screen'] for r in roots}):
        groups[f'screen:{sc}'] = [k for k in rkey if rkey[k]['screen'] == sc]
    out = {'valid_pairs': sum(p['pairs'] for p in per.values()), 'invalid': invalid, 'groups': {}, 'roots': []}
    for g, ks in groups.items():
        row = {}
        for y in ('heart', 'act4'):
            vals = [per[k][y] for k in ks if per[k][y]]
            if vals:
                p, lo, hi, n = boot_two_stage(vals, rng)
                row[y] = {'diff_pp': 100 * p, 'ci95_pp': [100 * lo, 100 * hi], 'roots': n}
        out['groups'][g] = row
    for k in rkey:
        r = rkey[k]
        h = np.asarray(per[k]['heart'], float)
        out['roots'].append({'seed': k[0], 'decisionIndex': k[1], 'screen': r['screen'], 'why': r['why'],
            'base': r['base']['label'], 'alt': r['alt']['label'], 'leafGap': r['leafGap'], 'pairs': per[k]['pairs'],
            'baseHeart': per[k]['baseHeart'],
            'heartDiff': float(h.mean()) if len(h) else None,
            'heartSE': float(h.std(ddof=1) / np.sqrt(len(h))) if len(h) > 1 else None,
            'act4Diff': float(np.mean(per[k]['act4'])) if per[k]['act4'] else None})
    gaps = [(r['leafGap'], r['heartDiff']) for r in out['roots'] if r['heartDiff'] is not None]
    if len(gaps) > 2:
        out['leafGapVsHeartDiff_pearson'] = float(np.corrcoef(*zip(*gaps))[0, 1])
    text = json.dumps(out, indent=1)
    if len(sys.argv) > 3:
        open(sys.argv[3], 'w').write(text)
    for g, row in out['groups'].items():
        print(g, json.dumps(row))
    print('valid pairs', out['valid_pairs'], 'invalid games', len(invalid))


if __name__ == '__main__':
    main()
