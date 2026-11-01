#!/usr/bin/env python3
"""Heart-entry perturbation labels, stage A checks (PREREG.md; written before any campaign data was read).
usage: analyze.py EXTRACT_DIR VARIANTS.jsonl OUT_DIR
EXTRACT_DIR holds the units' files (any depth): u<I>-v<k>.csv (one row each) and u<I>.done. VARIANTS.jsonl =
variants.tar's variants.jsonl. A base counts only if its unit ended with rc=0 and all 16 fights are valid.
Writes OUT_DIR/labels.csv (one row per base and variant) and OUT_DIR/analysis.json.
95% CIs: bootstrap over source seeds (10,000, seed 20261031)."""
import sys, os, re, glob, csv, json, collections
import numpy as np
K = 16
def seed_of(i, k): return (111382000 if k == 1 else 111384000) + i
EXPECT = {'hp_up': '+', 'hp_down': '-', 'potion_add': '+', 'potion_remove': '-', 'card_upgrade': '+', 'max_hp_up': '+'}
INCENSE_PP = [-1.75, 1.90, -8.25, 5.71, 10.16, -7.78]   # §723

def main(ext, variants, outdir):
    meta = [json.loads(l) for l in open(variants)]
    rcs, rows, bad = {}, collections.defaultdict(dict), []
    for p in glob.glob(os.path.join(ext, '**', 'u*.done'), recursive=True):
        m = re.match(r'u(\d+)\.done$', os.path.basename(p))
        if m: rcs[int(m.group(1))] = (re.search(r'\brc=(-?\d+)', open(p).read()) or [None, 'missing'])[1]
    for p in glob.glob(os.path.join(ext, '**', 'u*-v*.csv'), recursive=True):
        m = re.match(r'u(\d+)-v(\d+)\.csv$', os.path.basename(p))
        if not m: continue
        i, k = map(int, m.groups()); x = list(csv.DictReader(open(p)))
        if (len(x) != 1 or x[0]['encounter'] != 'THE_HEART' or x[0]['budget'] != 'learned'
                or int(x[0]['battleSeed']) != seed_of(i, k) or x[0]['id'] != meta[i]['game'] or k in rows[i]):
            bad.append(os.path.basename(p)); continue
        rows[i][k] = x[0]
    good = sorted(i for i in rows if rcs.get(i) == '0' and len(rows[i]) == K
                  and all(x['valid'] == '1' for x in rows[i].values()))
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, 'labels.csv'), 'w') as f:
        f.write('base,source_seed,variant,op,battle_seed,won,hp_left,turns,cpu_seconds\n')
        for i in good:
            for k in range(K):
                x = rows[i][k]
                f.write(f"{i},{meta[i]['seed']},{k},{meta[i]['variants'][k]['op']},{seed_of(i, k)},{x['won']},{x['curHp']},{x['turns']},{x['cpuSeconds']}\n")
    W = np.array([[float(rows[i][k]['won']) for k in range(K)] for i in good])   # base x k
    seeds = np.array([meta[i]['seed'] for i in good])
    us = np.unique(seeds); idx = {s: np.where(seeds == s)[0] for s in us}; rng = np.random.default_rng(20261031)
    boots = [rng.integers(0, len(us), len(us)) for _ in range(10000)]
    def cluster_stat(base_idx, vals):
        """Mean of vals (one per item) with items grouped by the source seed of base_idx; bootstrap over seeds."""
        base_idx, vals = np.asarray(base_idx), np.asarray(vals, float)
        if len(vals) == 0: return {'n': 0, 'mean': None, 'ci': None}
        by = collections.defaultdict(list)
        for b, v in zip(base_idx, vals): by[seeds[b]].append(v)
        sums = np.array([sum(by.get(s, [])) for s in us]); cnts = np.array([len(by.get(s, [])) for s in us])
        bs = [sums[b].sum() / max(cnts[b].sum(), 1) for b in boots]
        return {'n': int(len(vals)), 'mean': float(vals.mean()), 'ci': [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]}
    # Noise: outcome differs from the control after only reseeding (k = 1) vs after one state change (k >= 2).
    flip_reseed = cluster_stat(range(len(good)), W[:, 1] != W[:, 0]) if len(good) else None
    flip_pert = cluster_stat([b for b in range(len(good)) for k in range(2, K)],
                             [W[b, k] != W[b, 0] for b in range(len(good)) for k in range(2, K)]) if len(good) else None
    # Paired effect per operator: kill(variant) - kill(control), same base and battle seed.
    by_op = collections.defaultdict(lambda: ([], []))
    for bi, i in enumerate(good):
        for k in range(2, K):
            op = meta[i]['variants'][k]['op']
            by_op[op][0].append(bi); by_op[op][1].append(W[bi, k] - W[bi, 0])
    ops = {op: cluster_stat(*v) for op, v in sorted(by_op.items())}
    signs = {}
    for op, e in EXPECT.items():
        s = ops.get(op)
        if not s or s['n'] == 0: signs[op] = 'no data'; continue
        lo, hi = s['ci']
        ok = lo > 0 if e == '+' else hi < 0
        wrong = hi < 0 if e == '+' else lo > 0
        signs[op] = 'consistent' if ok else 'INCONSISTENT' if wrong else 'unresolved'
    # Incense counter changes vs §723's per-counter table.
    xs, ys, bis = [], [], []
    for bi, i in enumerate(good):
        for k in range(2, K):
            v = meta[i]['variants'][k]
            if v['op'] == 'relic_counter' and v['change']['relic'] == 'INCENSE_BURNER':
                a, b = v['change']['counter']; xs.append((INCENSE_PP[b] - INCENSE_PP[a]) / 100)
                ys.append(W[bi, k] - W[bi, 0]); bis.append(bi)
    inc = {'n': len(xs)}
    if len(xs) >= 3:
        xs, ys = np.array(xs), np.array(ys); inc['slope_obs_on_723'] = float(np.polyfit(xs, ys, 1)[0])
        inc['corr'] = float(np.corrcoef(xs, ys)[0, 1])
    all_pert = [(bi, W[bi, k] - W[bi, 0]) for bi in range(len(good)) for k in range(2, K)]
    res = {'bases_valid': len(good), 'bases_seen': len(rows), 'unit_rc_counts': dict(collections.Counter(rcs.values())),
           'bad_rows': bad[:20], 'n_bad': len(bad), 'source_seeds': int(len(us)),
           'outcome_flip_reseed_only': flip_reseed, 'outcome_flip_one_change': flip_pert,
           'control_kill': cluster_stat(range(len(good)), W[:, 0]) if len(good) else None,
           'reseed_minus_control_kill': cluster_stat(range(len(good)), W[:, 1] - W[:, 0]) if len(good) else None,
           'mean_perturbation_effect': cluster_stat(*zip(*all_pert)) if all_pert else None,
           'effect_by_operator': ops, 'sign_checks': signs, 'incense_vs_723': inc,
           'cpu_seconds_total': float(sum(float(x['cpuSeconds']) for i in good for x in rows[i].values()))}
    res['labels_usable'] = 'INCONSISTENT' not in signs.values()
    json.dump(res, open(os.path.join(outdir, 'analysis.json'), 'w'), indent=1); print(json.dumps(res, indent=1))

if __name__ == '__main__':
    main(*sys.argv[1:4])
