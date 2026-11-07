#!/usr/bin/env python3
"""Stage-2 leaf pilot analysis (PREREG.md; written before any campaign row was read).
usage: analyze.py UNITS_DIR OUT.json [--first-seeds units.txt]
UNITS_DIR holds the uploaded unit tars (<first seed>.wNN.tar; the first tar per unit id is used). A unit counts when
its result.txt says rc=0 and its JSONL has one source row per source seed (8; 1 for smoke seeds 111789990-999). Pairs: (fork,
variant) with a valid base and a valid variant row; D = y_variant - y_base for y = heartKill (primary) and
finalFloor (secondary). CIs: percentile bootstrap over source seeds, 2,000 resamples, seed 20261107.
Deviation 1 (PREREG.md, 2026-11-07, before the stop): every fork of a source run is weighted by w = eligible / sampled of
that run (inverse inclusion probability of the uniform reservoir of up to 4 fight ends). Without the weight, forks of
short (lost) runs are over-sampled and the base copy, which replays the source run, is biased towards a loss. The
weighted analysis is primary; the unweighted one is reported under 'unweighted'."""
import collections, gzip, io, json, math, os, re, sys, tarfile
import numpy as np

FAMILIES = ['hp:-3', 'hp:-8', 'hp:-15', 'pot', 'maxhp:-5', 'gold:-50']
HP = {'hp:-3': 3, 'hp:-8': 8, 'hp:-15': 15}
SIGN_FAMILIES = ['hp:-15', 'pot', 'maxhp:-5']
B, SEED, Z, BUDGET_CORE_H = 2000, 20261107, 3.0, 20000.0


def family(v):
    return 'pot' if v.startswith('pot:') else v


def load_units(units_dir):
    units, bad = {}, {}
    for name in sorted(os.listdir(units_dir)):
        m = re.fullmatch(r'(\d+)\.w\d+\.tar', name)
        if not m or m.group(1) in units or m.group(1) in bad:
            continue
        uid = m.group(1)
        with tarfile.open(os.path.join(units_dir, name)) as t:
            files = {x.name: x for x in t.getmembers() if x.isfile()}
            res = [n for n in files if n.endswith(f'/{uid}/result.txt')]
            jl = [n for n in files if n.endswith('.jsonl.gz') and f'/{uid}/' in n]
            if len(res) != 1 or len(jl) != 1:
                bad[uid] = 'missing result or jsonl'
                continue
            text = t.extractfile(files[res[0]]).read().decode()
            rc = re.search(r'rc=(\d+)', text)
            if not rc or rc.group(1) != '0':
                bad[uid] = 'rc ' + (rc.group(1) if rc else '?')
                continue
            rows = [json.loads(l) for l in gzip.open(io.BytesIO(t.extractfile(files[jl[0]]).read()), 'rt')]
        n_source = 1 if 111789990 <= int(uid) <= 111789999 else 8
        if sum(r['kind'] == 'source' for r in rows) != n_source:
            bad[uid] = 'source rows'
            continue
        units[uid] = rows
    return units, bad


def compute(units, bad, weighted):
    seeds, src = [], []
    forks = collections.defaultdict(dict)          # (seed, fork) -> {variant: row}
    skips = collections.Counter()
    for rows in units.values():
        for r in rows:
            if r['kind'] == 'source':
                src.append(r); seeds.append(r['seed'])
            elif r['kind'] == 'skip':
                skips[f"{r['variant']}:{r['reason']}"] += 1
            elif r['kind'] == 'copy':
                forks[(r['seed'], r['fork'])][r['variant']] = r
    wseed = {r['seed']: (r['eligible'] / r['sampled'] if weighted and r.get('sampled') else 1.0) for r in src}
    seed_ix = {s: i for i, s in enumerate(sorted(set(seeds)))}
    ns = len(seed_ix)
    # Cells: (act, family) for acts 1-4 and 'all'; per seed w-weighted sums of D, D^2, y_v, y_b and their squares,
    # plus pair counts and the w^2 sums the projection needs (w = 1 when unweighted).
    cells = [(a, f) for a in (1, 2, 3, 4, 'all') for f in FAMILIES]
    cix = {c: i for i, c in enumerate(cells)}
    K = len(cells)
    S = {k: np.zeros((ns, K)) for k in ('n', 'd', 'd2', 'yv', 'yv2', 'yb', 'yb2', 'disc', 'fd', 'fd2', 'cnt', 'w2',
                                        'w2d', 'w2d2')}
    slope_num, slope_den = np.zeros(ns), np.zeros(ns)       # acts 1-3, HP families: sum h*(-D), sum h^2
    room_cells = collections.defaultdict(list)               # (act, room, family) -> (D, w) list (descriptive)
    pot_type = collections.defaultdict(list)                 # potion -> (D, w) list (acts 1-4)
    n_forks = n_copies = 0
    cpu = collections.defaultdict(list)                      # act -> cpu s per continuation
    ppo = collections.Counter()
    base_heart = []
    for (seed, fork), vs in forks.items():
        base = vs.get('base')
        for r in vs.values():
            cpu[r['act']].append(r['cost']['cpuMs'] / 1000.0)
            for k in ('decisions', 'single', 'fallbacks'):
                ppo[k] += r.get('ppo', {}).get(k, 0)
        if not base or not base['outcome']['valid']:
            continue
        n_forks += 1; n_copies += len(vs)
        i = seed_ix[seed]; act = base['act']; w = wseed[seed]
        yb, fb = float(base['outcome']['heartKill']), float(base['outcome']['finalFloor'])
        base_heart.append((yb, w))
        for v, r in vs.items():
            if v == 'base' or not r['outcome']['valid']:
                continue
            f = family(v)
            yv, fv = float(r['outcome']['heartKill']), float(r['outcome']['finalFloor'])
            d, fd = yv - yb, fv - fb
            for a in (act, 'all'):
                j = cix[(a, f)]
                for k, x in (('n', w), ('d', w * d), ('d2', w * d * d), ('yv', w * yv), ('yv2', w * yv * yv),
                             ('yb', w * yb), ('yb2', w * yb * yb), ('disc', w * float(yv != yb)), ('fd', w * fd),
                             ('fd2', w * fd * fd), ('cnt', 1.0), ('w2', w * w), ('w2d', w * w * d),
                             ('w2d2', w * w * d * d)):
                    S[k][i, j] += x
            if f in HP and act in (1, 2, 3):
                slope_num[i] += w * HP[f] * (-d); slope_den[i] += w * HP[f] ** 2
            room_cells[(act, base['room'], f)].append((d, w))
            if f == 'pot':
                pot_type[v[4:]].append((d, w))
    rng = np.random.default_rng(SEED)
    W = rng.multinomial(ns, np.full(ns, 1.0 / ns), size=B).astype(float) if ns else np.zeros((B, 0))

    def boot(num, den):  # num, den: per-seed arrays -> (point, lo, hi) of sum(num)/sum(den)
        pt = num.sum() / den.sum() if den.sum() else float('nan')
        bs = (W @ num) / np.where(W @ den > 0, W @ den, np.nan)
        lo, hi = np.nanpercentile(bs, [2.5, 97.5]) if ns else (float('nan'), float('nan'))
        return pt, float(lo), float(hi), bs

    table = {}
    for (a, f), j in cix.items():
        n = S['n'][:, j]
        if n.sum() == 0:
            continue
        pt, lo, hi, _ = boot(S['d'][:, j], n)
        N = n.sum(); md = S['d'][:, j].sum() / N
        var_d = S['d2'][:, j].sum() / N - md ** 2
        var_v = S['yv2'][:, j].sum() / N - (S['yv'][:, j].sum() / N) ** 2
        var_b = S['yb2'][:, j].sum() / N - (S['yb'][:, j].sum() / N) ** 2
        fpt, flo, fhi, _ = boot(S['fd'][:, j], n)
        cnt, w2 = S['cnt'][:, j].sum(), S['w2'][:, j].sum()
        table[f'{a}|{f}'] = {
            'pairs': int(cnt), 'weight_sum': N, 'n_eff': N * N / w2 if w2 else float('nan'),
            'delta_pp': 100 * pt, 'ci_pp': [100 * lo, 100 * hi],
            'discordance': S['disc'][:, j].sum() / N, 'var_d': var_d,
            'rho': 1 - var_d / (var_v + var_b) if var_v + var_b > 0 else float('nan'),
            'heart_base': S['yb'][:, j].sum() / N, 'floor_delta': fpt, 'floor_ci': [flo, fhi]}
    beta, blo, bhi, beta_bs = boot(slope_num, slope_den)
    t_cont = float(np.mean([x for v in cpu.values() for x in v])) if cpu else float('nan')
    c_fork = n_copies / n_forks if n_forks else float('nan')

    def projection(beta_v, var_by_act):
        if not beta_v > 0:
            return math.inf
        n_forks_needed = sum(v * (Z / (8 * beta_v)) ** 2 for v in var_by_act)
        return n_forks_needed * c_fork * t_cont / 3600.0

    def var_hp8(a, wb=None):
        """Per-fork variance equivalent of the (weighted) hp:-8 mean: pairs x Var(mean); = Var(D) when w = 1."""
        j = cix[(a, 'hp:-8')]
        agg = {k: (wb @ S[k][:, j] if wb is not None else S[k][:, j].sum())
               for k in ('n', 'd', 'cnt', 'w2', 'w2d', 'w2d2')}
        if not agg['n']:
            return math.nan
        mu = agg['d'] / agg['n']
        var_mean = (agg['w2d2'] - 2 * mu * agg['w2d'] + mu * mu * agg['w2']) / agg['n'] ** 2
        return agg['cnt'] * var_mean

    cost = projection(beta, [var_hp8(a) for a in (1, 2, 3)])
    cost_bs = [projection(beta_bs[b], [var_hp8(a, W[b]) for a in (1, 2, 3)]) for b in range(B)] if ns else []
    cost_ci = [float(np.percentile(cost_bs, 2.5)), float(np.percentile(cost_bs, 97.5))] if cost_bs else None
    sign = {f: table.get(f'all|{f}') for f in SIGN_FAMILIES}
    s_pass = all(v is None or v['ci_pp'][0] <= 0 for v in sign.values())
    p_pass = beta > 0 and cost <= BUDGET_CORE_H
    per_act_z = {}
    for a in (1, 2, 3):
        cell = table.get(f'{a}|hp:-8')
        if cell:
            se = (cell['ci_pp'][1] - cell['ci_pp'][0]) / (2 * 1.96)
            per_act_z[a] = abs(cell['delta_pp']) / se if se > 0 else float('nan')
    hp_price = (lambda d_pp, k: (-d_pp / 100) / (k * beta) if beta > 0 else float('nan'))
    wmean = (lambda dw: float(sum(d * w for d, w in dw) / sum(w for _, w in dw)))
    prices = {'potion_hp': hp_price(table['all|pot']['delta_pp'], 1) if 'all|pot' in table else None,
              'maxhp_hp_per_point': hp_price(table['all|maxhp:-5']['delta_pp'], 5) if 'all|maxhp:-5' in table else None,
              'gold_hp_per_gold': hp_price(table['all|gold:-50']['delta_pp'], 50) if 'all|gold:-50' in table else None,
              'per_potion_type_hp': {p: hp_price(100 * wmean(dw), 1) for p, dw in sorted(pot_type.items())
                                     if len(dw) >= 50}}
    decisions = ppo['decisions'] + ppo['single'] + ppo['fallbacks']
    src_heart = [float(r.get('heartKill', False)) for r in src]
    res = {
        'units_ok': len(units), 'units_bad': bad, 'source_runs': len(src), 'forks': n_forks,
        'copies_per_fork': c_fork, 'cpu_s_per_continuation': t_cont,
        'cpu_s_by_act': {a: float(np.mean(v)) for a, v in sorted(cpu.items())},
        'core_h_played': sum(x for v in cpu.values() for x in v) / 3600.0,
        'source_heart_rate': float(np.mean(src_heart)) if src else None,
        'source_rate_flag': bool(src) and not 0.20 <= float(np.mean(src_heart)) <= 0.31,
        'base_heart_rate': wmean(base_heart) if base_heart else None,
        'base_heart_rate_unweighted': float(np.mean([y for y, _ in base_heart])) if base_heart else None,
        'weights': {'mean_per_fork': float(np.mean([w for _, w in base_heart])) if base_heart else None,
                    'max': float(max(w for _, w in base_heart)) if base_heart else None},
        'ppo_fallback_share': ppo['fallbacks'] / decisions if decisions else None,
        'skips': dict(skips), 'cells': table,
        'beta_pp_per_hp': 100 * beta, 'beta_ci': [100 * blo, 100 * bhi],
        'projection_core_h': cost, 'projection_ci': cost_ci, 'hp8_z_by_act': per_act_z,
        'sign_check_pass': s_pass, 'price_check_pass': p_pass,
        'decision': 'GO' if s_pass and p_pass else 'NO-GO',
        'pilot_resolves_hp8_all_acts': bool(per_act_z) and all(z >= Z for z in per_act_z.values()),
        'prices': prices,
        'room_cells_pp': {f'{a}|{r}|{f}': [len(dw), 100 * wmean(dw)] for (a, r, f), dw in sorted(
            room_cells.items(), key=lambda kv: str(kv[0]))}}
    return res


def main(units_dir, out_path):
    units, bad = load_units(units_dir)
    res = compute(units, bad, weighted=True)
    res['weighting'] = 'IPW: w = eligible / sampled per source run (PREREG.md, deviation 1)'
    unw = compute(units, bad, weighted=False)
    res['unweighted'] = {k: unw[k] for k in ('cells', 'beta_pp_per_hp', 'beta_ci', 'projection_core_h',
                                             'projection_ci', 'hp8_z_by_act', 'sign_check_pass', 'price_check_pass',
                                             'decision', 'base_heart_rate', 'prices', 'room_cells_pp')}
    json.dump(res, open(out_path, 'w'), indent=1, default=float)
    print(json.dumps({k: res[k] for k in ('units_ok', 'source_runs', 'forks', 'cpu_s_per_continuation',
                                          'source_heart_rate', 'base_heart_rate', 'ppo_fallback_share',
                                          'beta_pp_per_hp', 'beta_ci', 'projection_core_h', 'projection_ci',
                                          'sign_check_pass', 'price_check_pass', 'decision')}, indent=1,
                     default=float))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
