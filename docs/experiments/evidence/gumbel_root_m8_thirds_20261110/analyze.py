#!/usr/bin/env python3
"""Offline: would a Gumbel root with m=8 candidates, or thirds instead of halving, change G16 + mb4's picks?

Reads the 1,024 traced G16 + mb4 runs of gumbel_stop_data_20261110 (STS_SILVER_GUMBEL_STOP_TRACE, one row per
sequential-halving boundary) and writes per-bucket statistics. No games are played.
Usage: analyze.py UNITS_DIR OUT_JSON   (UNITS_DIR = the campaign's units/ with <seed>.wNN.tar)
"""
import collections, csv, glob, io, json, lzma, math, random, sys, tarfile
from multiprocessing import Pool


def roots_of(path):
    out = []
    with tarfile.open(path) as t:
        for m in t.getmembers():
            if not m.name.endswith('.csv.xz'):
                continue
            cur = None
            for r in csv.DictReader(io.StringIO(lzma.decompress(t.extractfile(m).read()).decode())):
                key = (r['seed'], r['combat'], r['decision'])
                if cur is None or cur['key'] != key:
                    if cur:
                        out.append(cur)
                    cur = dict(key=key, legal=int(r['legal_actions']), cpu=float(r['root_cpu_seconds']),
                               phases=int(r['phases']), final=int(r['final_edge']), b=[])
                cur['b'].append(dict(boundary=int(r['boundary']), leader=int(r['leader_edge']),
                                     runner=int(r['runner_up_edge']), lq=float(r['leader_q']),
                                     rq=float(r['runner_up_q']), qv=int(r['q_valid']),
                                     lprior=float(r['leader_prior'])))
            if cur:
                out.append(cur)
    return [r for r in out if r['b']]


def bucket(n):
    for hi, name in ((2, '2'), (4, '3-4'), (8, '5-8'), (12, '9-12'), (16, '13-16'), (24, '17-24')):
        if n <= hi:
            return name
    return '25+'


def p_in_top8(pf, n, rng, draws=50):
    """Gumbel-top-8 inclusion of an edge with prior pf when the other n-1 edges share 1-pf equally (pessimistic)."""
    if n <= 8:
        return 1.0
    lw = [math.log(max(pf, 1e-12))] + [math.log(max((1 - pf) / (n - 1), 1e-12))] * (n - 1)
    hit = 0
    for _ in range(draws):
        keys = [w - math.log(-math.log(rng.random() + 1e-300)) for w in lw]
        hit += sum(k > keys[0] for k in keys[1:]) < 8
    return hit / draws


def main():
    files = sorted(glob.glob(sys.argv[1].rstrip('/') + '/*.tar'))
    with Pool(8) as p:
        roots = [r for part in p.map(roots_of, files, chunksize=8) for r in part]
    total, cpu = len(roots), sum(r['cpu'] for r in roots)
    rng = random.Random(1)
    agg = collections.defaultdict(lambda: collections.Counter())
    for i, r in enumerate(roots):
        a = agg[bucket(r['legal'])]
        a['roots'] += 1
        a['cpu'] += r['cpu']
        a['final_is_b0_leader'] += r['b'][0]['leader'] == r['final']
        last = r['b'][-1]
        a['final_prior_sum'] += last['lprior']
        if i % 20 == 0:
            a['top8_n'] += 1
            a['top8_sum'] += p_in_top8(last['lprior'], r['legal'], rng)
        if last['qv'] and r['legal'] > 2:
            a['last_qvalid'] += 1
            d = last['lq'] - last['rq']
            a['last_tie'] += abs(d) < 1e-9
            a['last_real_flip'] += d <= -1e-9
    by_n = collections.defaultdict(collections.Counter)
    for r in roots:
        if len(r['b']) >= 3:
            c = by_n[min(r['legal'], 16)]
            c['roots'] += 1
            c['final_leader_b1'] += r['b'][1]['leader'] == r['final']
            c['final_top2_b1'] += r['final'] in (r['b'][1]['leader'], r['b'][1]['runner'])
    ns = sorted(r['legal'] for r in roots)
    res = dict(roots=total, root_cpu_hours=cpu / 3600,
               legal=dict(median=ns[total // 2], p90=ns[int(.9 * total)], p99=ns[int(.99 * total)], max=ns[-1],
                          share_le8=sum(n <= 8 for n in ns) / total, share_gt16=sum(n > 16 for n in ns) / total),
               buckets={}, boundary1_by_n={})
    for k, a in agg.items():
        res['buckets'][k] = dict(
            root_share=a['roots'] / total, cpu_share=a['cpu'] / cpu,
            final_is_b0_leader=a['final_is_b0_leader'] / a['roots'],
            mean_final_prior=a['final_prior_sum'] / a['roots'],
            est_final_in_prior_top8=a['top8_sum'] / max(a['top8_n'], 1),
            last_boundary_exact_tie=a['last_tie'] / max(a['last_qvalid'], 1),
            last_boundary_real_q_flip=a['last_real_flip'] / max(a['last_qvalid'], 1))
    for n, c in sorted(by_n.items()):
        res['boundary1_by_n'][str(n)] = dict(roots=c['roots'], final_leader=c['final_leader_b1'] / c['roots'],
                                             final_top2=c['final_top2_b1'] / c['roots'])
    json.dump(res, open(sys.argv[2], 'w'), indent=1, sort_keys=True)


if __name__ == '__main__':
    main()
