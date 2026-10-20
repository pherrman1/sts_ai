"""Gen-1b value-leaf A/B analysis: python3 -I analyze.py SHARE_DIR -> JSON (paired B = gen1b value leaf vs A = X2-B leaf)."""
import sys, tarfile, json, gzip, re, glob, math, statistics
def mcnemar_p(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c); p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)
def paired_ci(pairs):
    d = [x - y for x, y in pairs]; n = len(d); m = sum(d) / n
    sd = statistics.pstdev(d) if n > 1 else 0
    h = 1.96 * sd / math.sqrt(n); return m, m - h, m + h
def arm(t, m, a, s):
    def rd(sfx):
        k = [n for n in m if n.endswith(sfx)]; return t.extractfile(m[k[0]]).read() if k else None
    done = (rd(f'{a}-{s}.done') or b'rc=-1 wall=0').decode()
    rc = re.search(r'rc=(-?\d+)', done).group(1); j = rd(f'{a}-{s}.jsonl.gz')
    if rc != '0' or not j: return None, rc
    lines = gzip.decompress(j).splitlines(); foot = json.loads(lines[-1])
    if foot.get('type') != 'outcome' or not foot.get('complete') or not foot.get('integrityPassed'): return None, rc
    d = dict(foot=foot, wall=int(re.search(r'wall=(\d+)', done).group(1)), searched=0, fullBudget=0, aborted=0,
             changed=0, decisions=0)
    for x in lines[1:-1]:
        r = json.loads(x)
        if r.get('type') != 'decision': continue
        d['decisions'] += 1; root = r.get('root')
        if root and not root.get('singleton'):
            d['searched'] += 1; d['fullBudget'] += bool(root.get('fullBudget')); d['aborted'] += bool(root.get('aborted'))
            c = root.get('candidates', [])
            if c and root.get('selectedId') != max(c, key=lambda x: x['prior'])['id']: d['changed'] += 1
    return d, rc
res = dict(seeds=0, valid=0, invalid=[], heart=[], act4=[], act1death=[], floor=[], wall=[], data={'A': {}, 'B': {}})
for path in sorted(glob.glob(sys.argv[1] + '/w*.tar')):
    t = tarfile.open(path); m = {x.name: x for x in t.getmembers() if x.isfile()}
    seeds = sorted({re.search(r'A-(\d+)\.done$', n).group(1) for n in m if re.search(r'/A-\d+\.done$', n)})
    for s in seeds:
        res['seeds'] += 1
        (a, ra), (b, rb) = arm(t, m, 'A', s), arm(t, m, 'B', s)
        if a is None or b is None: res['invalid'].append((s, ra, rb)); continue
        res['valid'] += 1
        res['heart'].append((int(bool(b['foot']['heartKilled'])), int(bool(a['foot']['heartKilled']))))
        res['act4'].append((int(b['foot']['finalAct'] >= 4), int(a['foot']['finalAct'] >= 4)))
        res['act1death'].append((int(b['foot']['finalAct'] == 1), int(a['foot']['finalAct'] == 1)))
        res['floor'].append((b['foot']['finalFloor'], a['foot']['finalFloor'])); res['wall'].append((b['wall'], a['wall']))
        for k, d in (('A', a), ('B', b)):
            for f in ('decisions', 'searched', 'fullBudget', 'aborted', 'changed'):
                res['data'][k][f] = res['data'][k].get(f, 0) + d[f]
out = dict(seeds=res['seeds'], valid=res['valid'], invalid=res['invalid'])
for k in ('heart', 'act4', 'act1death'):
    p = res[k]; bo = sum(1 for x, y in p if x and not y); ao = sum(1 for x, y in p if y and not x)
    mm, lo, hi = paired_ci(p)
    out[k] = dict(B=sum(x for x, _ in p), A=sum(y for _, y in p), B_pct=100 * sum(x for x, _ in p) / len(p),
                  A_pct=100 * sum(y for _, y in p) / len(p), diff_pp=100 * mm, ci95_pp=[100 * lo, 100 * hi],
                  B_only=bo, A_only=ao, mcnemar_p=mcnemar_p(bo, ao))
out['mean_floor'] = dict(B=statistics.mean(x for x, _ in res['floor']), A=statistics.mean(y for _, y in res['floor']))
out['wall_s'] = dict(B_mean=statistics.mean(x for x, _ in res['wall']), A_mean=statistics.mean(y for _, y in res['wall']),
                     B_max=max(x for x, _ in res['wall']), A_max=max(y for _, y in res['wall']))
out['wall_s']['B_over_A'] = out['wall_s']['B_mean'] / out['wall_s']['A_mean']
h = out['heart']; ahead = h['B'] > h['A']; sig = h['mcnemar_p'] < 0.05
out['verdict'] = ('WIN' if out['wall_s']['B_over_A'] <= 1.10 else 'WIN_AT_HIGHER_CPU') if sig and ahead else \
    'WORSE' if sig else 'NOT_SHOWN'
out['data'] = res['data']
print(json.dumps(out, indent=1))
