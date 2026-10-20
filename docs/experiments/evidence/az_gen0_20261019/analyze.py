"""AZ gen-0 analysis: python3 -I analyze.py SHARE_DIR -> JSON summary (paired search vs off, data counts)."""
import sys, tarfile, json, gzip, io, csv, re, glob, math, statistics
def mcnemar_p(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c); p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)
def paired_ci(pairs):
    d = [a - b for a, b in pairs]; n = len(d); m = sum(d) / n
    sd = statistics.pstdev(d) if n > 1 else 0
    h = 1.96 * sd / math.sqrt(n); return m, m - h, m + h
res = dict(seeds=0, valid=0, invalid=[], heart=[], act4=[], rows_state=0, rows_decision=0, searched=0,
           singleton=0, fullBudget=0, aborted=0, ctm=0, wall_on=[], wall_off=[], floor_on=[], floor_off=[])
for path in sorted(glob.glob(sys.argv[1] + '/w*.tar')):
    t = tarfile.open(path); m = {x.name: x for x in t.getmembers() if x.isfile()}
    def rd(sfx):
        k = [n for n in m if n.endswith(sfx)]; return t.extractfile(m[k[0]]).read() if k else None
    seeds = sorted({re.search(r'on-(\d+)\.done$', n).group(1) for n in m if re.search(r'on-\d+\.done$', n)})
    for s in seeds:
        res['seeds'] += 1
        don, doff = rd(f'on-{s}.done').decode(), (rd(f'off-{s}.done') or b'rc=-1').decode()
        rcs = re.search(r'rc=(-?\d+)', don).group(1), re.search(r'rc=(-?\d+)', doff).group(1)
        j, c = rd(f'on-{s}.jsonl.gz'), rd(f'off-{s}.csv')
        if j:
            lines = gzip.decompress(j).splitlines(); foot = json.loads(lines[-1])
            for x in lines[1:-1]:
                r = json.loads(x); res['rows_' + ('decision' if r.get('type') == 'decision' else 'state')] += 1
                root = r.get('root')
                if root:
                    res['searched'] += 1; res['singleton'] += bool(root.get('singleton'))
                    res['fullBudget'] += bool(root.get('fullBudget')); res['aborted'] += bool(root.get('aborted'))
        cj = rd(f'on-{s}.ctm.jsonl.gz')
        if cj: res['ctm'] += len(gzip.decompress(cj).splitlines())
        ok = rcs == ('0', '0') and j and c and foot.get('complete') and foot.get('integrityPassed')
        if not ok: res['invalid'].append((s, rcs)); continue
        row = list(csv.DictReader(io.StringIO(c.decode())))[0]
        res['valid'] += 1
        res['heart'].append((int(bool(foot['heartKilled'])), int(row['won'] == '1')))
        res['act4'].append((int(foot['finalAct'] >= 4), int(int(row['act']) >= 4)))
        res['floor_on'].append(foot['finalFloor']); res['floor_off'].append(int(row['floor']))
        res['wall_on'].append(int(re.search(r'wall=(\d+)', don).group(1)))
        res['wall_off'].append(int(re.search(r'wall=(\d+)', doff).group(1)))
out = dict(seeds=res['seeds'], valid=res['valid'], invalid=res['invalid'])
for k in ('heart', 'act4'):
    p = res[k]; b = sum(1 for a, o in p if a and not o); cc = sum(1 for a, o in p if o and not a)
    mm, lo, hi = paired_ci(p)
    out[k] = dict(search=sum(a for a, _ in p), off=sum(o for _, o in p), search_pct=100 * sum(a for a, _ in p) / len(p),
                  off_pct=100 * sum(o for _, o in p) / len(p), diff_pp=100 * mm, ci95_pp=[100 * lo, 100 * hi],
                  search_only=b, off_only=cc, mcnemar_p=mcnemar_p(b, cc))
out['mean_floor'] = dict(search=statistics.mean(res['floor_on']), off=statistics.mean(res['floor_off']))
out['wall_s'] = dict(search_mean=statistics.mean(res['wall_on']), search_max=max(res['wall_on']),
                     off_mean=statistics.mean(res['wall_off']), off_max=max(res['wall_off']))
ns = res['searched'] - res['singleton']
out['data'] = dict(rows_state=res['rows_state'], rows_decision=res['rows_decision'], searched_roots=res['searched'],
                   nonsingleton_roots=ns, fullBudget=res['fullBudget'], fullBudget_frac_nonsingleton=res['fullBudget'] / max(ns, 1),
                   aborted=res['aborted'], ctm_rows=res['ctm'])
print(json.dumps(out, indent=1))
