#!/usr/bin/env python3
"""E1 of the learned price head (PREREG.md; written before any E1 row existed).
usage: analyze.py E1_UNITS_DIR PILOT_UNITS_DIR OUT.json
E1_UNITS_DIR holds E1's unit tars (<first seed>.wNN.tar, 16 source seeds each); PILOT_UNITS_DIR the leaf pilot's
(8 source seeds each; read only). A unit counts when result.txt says rc=0 and its JSONL has all source rows; per unit
id the pilot's first tar is used (its own rule) and E1's first tar that counts. Gates G1-G5, the luck regression (beta_luck, M = 1), the CRN slope (beta_CRN, fork
weights eligible/sampled x luck variance of the fight's cell), their ratio with a paired bootstrap over source
seeds (2,000 resamples, seed 20261107) and the pre-registered decision."""
import collections, gzip, io, json, math, os, re, sys, tarfile
import numpy as np

B, SEED, M = 2000, 20261107, 1
ATT = (M + 1) / M                              # luck coefficient scale for y_real - mean of M replays
HP_K = {'hp:-3': 3, 'hp:-8': 8, 'hp:-15': 15}
ROOMS = ('NORMAL', 'ELITE', 'BOSS')
E1_FIRST, E1_LAST = 111780000, 111788191
G1_FIELDS = ('valid', 'won', 'heartKill', 'floor', 'fightEnds', 'eligible', 'ineligible', 'ppo')
MIN_CELL, Z_G5, G4_MAX = 30, 3.5, 0.02


def band(hp):
    return 0 if hp <= 30 else (1 if hp <= 50 else 2)


def load_units(units_dir, prefix, n_source, keep, first_ok=False):
    """{uid: rows} for complete units with uid accepted by keep(uid); bad: {uid: reason}. The first tar per unit id
    is used (the pilot's rule); first_ok=True (E1) uses the first tar that counts, since every attempt of a unit
    replays the same deterministic runs."""
    units, bad = {}, {}
    for name in sorted(os.listdir(units_dir)):
        m = re.fullmatch(r'(\d+)\.w\d+\.tar', name)
        if not m or not keep(int(m.group(1))) or m.group(1) in units or (m.group(1) in bad and not first_ok):
            continue
        uid = m.group(1)
        with tarfile.open(os.path.join(units_dir, name)) as t:
            files = {x.name: x for x in t.getmembers() if x.isfile()}
            res = [n for n in files if n.endswith(f'/{uid}/result.txt')]
            jl = [n for n in files if n.endswith('.jsonl.gz') and f'/{uid}/' in n
                  and os.path.basename(n).startswith(prefix)]
            if len(res) != 1 or len(jl) != 1:
                bad[uid] = 'missing result or jsonl'
                continue
            text = t.extractfile(files[res[0]]).read().decode()
            rc = re.search(r'rc=(\d+)', text)
            if not rc or rc.group(1) != '0':
                bad[uid] = 'rc ' + (rc.group(1) if rc else '?')
                continue
            rows = [json.loads(l) for l in gzip.open(io.BytesIO(t.extractfile(files[jl[0]]).read()), 'rt')]
        if sum(r['kind'] == 'source' for r in rows) != n_source:
            bad[uid] = 'source rows'
            continue
        units[uid] = rows
        bad.pop(uid, None)
    return units, bad


def src_key(r):
    return {**{k: r.get(k) for k in G1_FIELDS}, 'silverSimulations': r['cost']['silverSimulations']}


def ols(X, y, w=None):
    """(weighted) OLS: coefficients, HC1 standard errors (unweighted fit only), residuals."""
    if w is None:
        XtXi = np.linalg.pinv(X.T @ X)
        b = XtXi @ X.T @ y
        e = y - X @ b
        n, p = X.shape
        V = XtXi @ ((X * (e ** 2)[:, None]).T @ X) @ XtXi * n / (n - p)
        return b, np.sqrt(np.maximum(np.diag(V), 0)), e
    Xw = X * w[:, None]
    return np.linalg.pinv(Xw.T @ X) @ (Xw.T @ y), None, None


def main(e1_dir, pilot_dir, out_path):
    in_block = lambda uid: E1_FIRST <= uid <= E1_LAST
    e1_units, e1_bad = load_units(e1_dir, 'le-', 16, in_block, first_ok=True)
    pilot_units, pilot_bad = load_units(pilot_dir, 'fe-', 8, in_block)

    # ---- E1 rows
    e1_src, luck = {}, {}
    for rows in e1_units.values():
        for r in rows:
            if r['kind'] == 'source':
                e1_src[r['seed']] = r
            elif r['kind'] == 'luck':
                luck[(r['seed'], r['fightIndex'])] = r
    # ---- pilot rows (slim)
    p_src, forks = {}, collections.defaultdict(dict)
    for rows in pilot_units.values():
        for r in rows:
            if r['kind'] == 'source':
                p_src[r['seed']] = r
            elif r['kind'] == 'copy':
                forks[(r['seed'], r['fork'])][r['variant']] = {
                    'act': r['act'], 'room': r['room'], 'fightIndex': r['fightIndex'], 'state': r['state'],
                    'valid': r['outcome']['valid'], 'y': float(r['outcome']['heartKill'])}
    both = sorted(set(e1_src) & set(p_src))

    # ---- G1: source identity
    g1_bad = [s for s in both if src_key(e1_src[s]) != src_key(p_src[s])]
    # ---- G2: fork identity (pilot base state == E1 real fight end)
    g2_checked, g2_bad, g2_missing = 0, [], []
    for (seed, fork), vs in forks.items():
        base = vs.get('base')
        if seed not in e1_src or base is None:
            continue
        row = luck.get((seed, base['fightIndex']))
        if row is None:
            g2_missing.append([seed, base['fightIndex']])
            continue
        g2_checked += 1
        if row['real']['state'] != base['state']:
            g2_bad.append([seed, base['fightIndex']])
    # ---- G3: replicate-0 identity
    ident = [r for r in luck.values() if 'identity' in r]
    g3_bad = collections.Counter(r['encounter'] for r in ident if not r['identity'])
    # ---- G4: replay health
    def replay_ok(r):
        x = r['replays'][0]
        return 'error' not in x and x['healthFailures'] == 0
    a123 = [r for r in luck.values() if r['act'] <= 3]
    g4_dropped = sum(not replay_ok(r) for r in a123)
    g4_share = g4_dropped / len(a123) if a123 else float('nan')

    # ---- luck components (counter relics chosen outcome-blind: data differs real vs replay in >= 50 fights)
    vary = collections.Counter()
    for r in luck.values():
        if not replay_ok(r):
            continue
        a, b = r['real']['fields']['relicData'], r['replays'][0]['fields']['relicData']
        for name, x, z in zip(r['relics'], a, b):
            if x != z:
                vary[name] += 1
    counters = sorted(n for n, c in vary.items() if c >= 50)
    comps = ['s', 'h', 'k', 'mhp', 'gold', 'upg', 'misc'] + [f'r:{c}' for c in counters]

    def yvec(end, names):
        s = 1.0 if end['won'] else 0.0
        f = end['fields']
        rel = dict(zip(names, f['relicData']))
        return np.array([s, s * f['hp'], s * f['potionCount'], s * f['maxHp'], s * f['gold'], s * f['upgrades'],
                         s * f['misc']] + [s * rel.get(c, 0) for c in counters], float)

    G = collections.defaultdict(lambda: collections.defaultdict(float))   # per seed: column -> luck sum
    fight_u = []                                         # acts 1-3 N/E/B: (act, room, enc, band, u, seed, fightIndex)
    g5 = collections.defaultdict(list)
    for (seed, fi), r in luck.items():
        if not replay_ok(r):
            continue
        u = yvec(r['real'], r['relics']) - yvec(r['replays'][0], r['relics'])
        act, room = r['act'], r['room']
        if act <= 3:
            g5[(act, room)].append((u[1], u[0]))
            for c, x in zip(comps, u):
                G[seed][f'{c}_c'] += x                      # controls: every act 1-3 fight
            if room in ROOMS:
                fight_u.append((act, room, r['encounter'], band(r['start']['hp']), u, seed, fi))
                for c, x in zip(comps, u):
                    G[seed][f'{c}_a{act}'] += x
                    G[seed][f'{c}_a123'] += x
                    G[seed][f'{c}_a{act}_{room}'] += x
            else:
                for c, x in zip(comps, u):
                    G[seed][f'{c}_ev'] += x
        else:
            grp = 'heart' if r['encounter'] == 'THE_HEART' else 'ss'
            for c, x in zip(comps, u):
                G[seed][f'{c}_{grp}'] += x
    g5_cells = {}
    for (act, room), v in sorted(g5.items()):
        if len(v) < 100:
            continue
        arr = np.array(v)
        zs = [float(arr[:, j].mean() / (arr[:, j].std(ddof=1) / math.sqrt(len(arr)))) if arr[:, j].std() > 0 else 0.0
              for j in (0, 1)]
        g5_cells[f'{act}|{room}'] = {'n': len(arr), 'mean_u_hp': float(arr[:, 0].mean()), 'z_hp': zs[0],
                                     'mean_u_s': float(arr[:, 1].mean()), 'z_s': zs[1]}
    g5_pass = all(abs(c['z_hp']) < Z_G5 and abs(c['z_s']) < Z_G5 for c in g5_cells.values())

    # ---- luck regression
    controls = [f'{c}_c' for c in comps if c not in ('s', 'h', 'k')]
    ev = ['s_ev', 'h_ev', 'k_ev']
    act4 = ['s_ss', 'h_ss', 'k_ss', 's_heart']
    base_cols = ['s_a1', 's_a2', 's_a3', 'k_a1', 'k_a2', 'k_a3']
    models = {'pooled': base_cols + ['h_a123'] + controls + ev + act4,
              'per_act': base_cols + ['h_a1', 'h_a2', 'h_a3'] + controls + ev + act4,
              'per_act_room': base_cols + [f'h_a{a}_{r}' for a in (1, 2, 3) for r in ROOMS] + controls + ev + act4}

    def design(seeds, cols):
        return np.column_stack([np.ones(len(seeds))] + [np.array([G[s].get(c, 0.0) for s in seeds]) for c in cols])

    def luck_fit(seeds, model):
        cols = models[model]
        X = design(seeds, cols)
        y = np.array([float(e1_src[s]['heartKill']) for s in seeds])
        b, se, e = ols(X, y)
        res = {c: (ATT * float(bb), ATT * float(ss)) for c, bb, ss in zip(['const'] + cols, b, se)}
        res['const'] = (float(b[0]), float(se[0]))
        return res, float(e.var(ddof=X.shape[1])), X, y

    # ---- luck weights v for the CRN forks: HP luck net of the fight's other luck, cell means of its square over the
    # other fights of the cell (leave-one-out: the fork's own fight leaves its cell's mean and count)
    resid, own_e2 = {}, {}
    for act in (1, 2, 3):
        rows = [x for x in fight_u if x[0] == act]
        if not rows:
            continue
        U = np.array([x[4] for x in rows])
        Z = np.column_stack([np.ones(len(U)), U[:, 0], U[:, 2], U[:, 3], U[:, 4]])   # s, k, mhp, gold
        coef = np.linalg.lstsq(Z, U[:, 1], rcond=None)[0]
        for x, e in zip(rows, U[:, 1] - Z @ coef):
            resid.setdefault(act, []).append((x[1], x[2], x[3], float(e) ** 2))
            own_e2[(x[5], x[6])] = float(e) ** 2
    cells = collections.defaultdict(lambda: [0.0, 0])                       # key -> [sum of e^2, fights]
    for act, lst in resid.items():
        for room, enc, bd, e2 in lst:
            for key in (('enc', act, enc, bd), ('room_band', act, room, bd), ('room', act, room)):
                cells[key][0] += e2
                cells[key][1] += 1

    def v_of(act, room, enc, bd, own):
        """Cell mean of e^2 without the fork's own fight (own = its e^2, or None when its replay was dropped)."""
        for key in (('enc', act, enc, bd), ('room_band', act, room, bd), ('room', act, room)):
            tot, n = cells.get(key, (0.0, 0))
            if own is not None and n > 0:
                tot, n = tot - own, n - 1
            if n >= MIN_CELL:
                return tot / n, key[0]
        return float('nan'), 'none'

    # ---- CRN forks on S (seeds in both)
    S = [s for s in both if s not in set(g1_bad)]
    s_ix = {s: i for i, s in enumerate(S)}
    fk = []          # (seed index, act, room, theta, pi_inv, v, hp_pairs[(k, -D)], pot_d)
    v_level = collections.Counter()
    for (seed, fork), vs in forks.items():
        base = vs.get('base')
        if seed not in s_ix or base is None or not base['valid'] or base['act'] > 3:
            continue
        pairs = [(k, base['y'] - vs[v]['y']) for v, k in HP_K.items() if v in vs and vs[v]['valid']]
        if not pairs:
            continue
        theta = sum(k * d for k, d in pairs) / sum(k * k for k, _ in pairs)
        lr = luck.get((seed, base['fightIndex']))
        if lr is None:
            continue
        v, lvl = v_of(base['act'], base['room'], lr['encounter'], band(lr['start']['hp']),
                      own_e2.get((seed, base['fightIndex'])))
        v_level[lvl] += 1
        src = p_src[seed]
        pi_inv = src['eligible'] / src['sampled'] if src.get('sampled') else 1.0
        pots = [base['y'] - vs[x]['y'] for x in vs if x.startswith('pot:') and vs[x]['valid']]
        fk.append((s_ix[seed], base['act'], base['room'], theta, pi_inv, v, pairs,
                   float(np.mean(pots)) if pots else None))
    fk = [f for f in fk if np.isfinite(f[5])]

    def crn_sums(sel, weight):
        num, den = np.zeros(len(S)), np.zeros(len(S))
        for f in fk:
            if sel(f):
                w = weight(f)
                num[f[0]] += w * f[3]
                den[f[0]] += w
        return num, den

    def pilot_beta_sums(sel):   # the pilot's own beta: sum pi^-1 k (-D) / sum pi^-1 k^2
        num, den = np.zeros(len(S)), np.zeros(len(S))
        for f in fk:
            if sel(f):
                for k, d in f[6]:
                    num[f[0]] += f[4] * k * d
                    den[f[0]] += f[4] * k * k
        return num, den

    allf = lambda f: True
    lw = lambda f: f[4] * f[5]
    groups = {'pooled': (allf, 'h_a123', 'pooled')}
    for a in (1, 2, 3):
        groups[f'act{a}'] = ((lambda a: lambda f: f[1] == a)(a), f'h_a{a}', 'per_act')
        for room in ROOMS:
            groups[f'act{a}|{room}'] = ((lambda a, room: lambda f: f[1] == a and f[2] == room)(a, room),
                                        f'h_a{a}_{room}', 'per_act_room')

    rng = np.random.default_rng(SEED)
    W = rng.multinomial(len(S), np.full(len(S), 1.0 / len(S)), size=B).astype(float) if S else np.zeros((B, 0))
    fits = {m: luck_fit(S, m) for m in models}
    beta_boot = {m: [] for m in models}
    for b in range(B):
        for m, (_, _, X, y) in fits.items():
            beta_boot[m].append(ATT * ols(X, y, W[b])[0])
    cols_ix = {m: {c: i for i, c in enumerate(['const'] + models[m])} for m in models}

    out_groups = {}
    for name, (sel, col, model) in groups.items():
        num, den = crn_sums(sel, lw)
        pnum, pden = pilot_beta_sums(sel)
        if den.sum() <= 0:
            continue
        crn = num.sum() / den.sum()
        crn_bs = (W @ num) / np.where(W @ den > 0, W @ den, np.nan)
        luck_pt = fits[model][0][col][0]
        luck_bs = np.array([bb[cols_ix[model][col]] for bb in beta_boot[model]])
        ratio_bs = luck_bs / crn_bs
        pil = pnum.sum() / pden.sum() if pden.sum() > 0 else float('nan')
        pil_bs = (W @ pnum) / np.where(W @ pden > 0, W @ pden, np.nan)
        q = lambda a, p: [float(x) for x in np.nanpercentile(a, p)]
        out_groups[name] = {
            'forks': int(sum(1 for f in fk if sel(f))),
            'beta_luck_pp': 100 * luck_pt, 'beta_luck_se_pp': 100 * fits[model][0][col][1],
            'beta_luck_ci95_pp': [100 * x for x in q(luck_bs, [2.5, 97.5])],
            'beta_crn_pp': 100 * crn, 'beta_crn_ci95_pp': [100 * x for x in q(crn_bs, [2.5, 97.5])],
            'crn_nonpositive_share': float(np.mean(~(crn_bs > 0))),
            'ratio': luck_pt / crn if crn else float('nan'),
            'ratio_ci90': q(ratio_bs, [5, 95]), 'ratio_ci95': q(ratio_bs, [2.5, 97.5]),
            'beta_pilot_pp': 100 * pil, 'beta_pilot_ci95_pp': [100 * x for x in q(pil_bs, [2.5, 97.5])],
            'ratio_luck_to_pilot': luck_pt / pil if pil else float('nan')}

    # ---- decision
    p = out_groups.get('pooled')
    if g1_bad or g2_bad or g2_missing or g4_share > G4_MAX:
        decision = 'INVALID'
    elif g3_bad or not g5_pass:
        decision = 'INSTRUMENT_FAIL'
    elif p is None or p['crn_nonpositive_share'] > 0.025:
        decision = 'INCONCLUSIVE (CRN unresolved)'
    elif 0.67 <= p['ratio_ci90'][0] and p['ratio_ci90'][1] <= 1.5:
        decision = 'GO'
    elif p['ratio_ci95'][0] > 1 or p['ratio_ci95'][1] < 1:
        decision = 'FAIL'
    else:
        decision = 'INCONCLUSIVE'

    # ---- descriptive
    per_act, _, _, _ = fits['per_act']
    pots = {}
    for a in (1, 2, 3):
        sel = [f for f in fk if f[1] == a and f[7] is not None]
        wsum = sum(f[4] for f in sel)
        pots[f'act{a}'] = {'luck_pp_per_potion': [100 * per_act[f'k_a{a}'][0], 100 * per_act[f'k_a{a}'][1]],
                           'crn_pp_per_potion': 100 * sum(f[4] * f[7] for f in sel) / wsum if wsum else None,
                           'survival_pp': [100 * per_act[f's_a{a}'][0], 100 * per_act[f's_a{a}'][1]]}
    per_game = collections.defaultdict(lambda: [0.0, 0.0, 0.0])           # (seed, act) -> [hp u^2, pot u^2, fights]
    for (seed, fi), r in luck.items():
        if r['act'] <= 3 and r['room'] in ROOMS and replay_ok(r):
            u = yvec(r['real'], r['relics']) - yvec(r['replays'][0], r['relics'])
            pg = per_game[(seed, r['act'])]
            pg[0] += u[1] ** 2 / 2; pg[1] += u[2] ** 2 / 2; pg[2] += 1
    seeds_all = sorted(e1_src)
    luck_var = {f'act{a}': {'hp2_per_game': float(np.mean([per_game[(s, a)][0] for s in seeds_all])),
                            'pot2_per_game': float(np.mean([per_game[(s, a)][1] for s in seeds_all])),
                            'fights_per_game': float(np.mean([per_game[(s, a)][2] for s in seeds_all]))}
                for a in (1, 2, 3)}
    all_fit, all_resvar, _, _ = luck_fit(seeds_all, 'pooled')
    src_cpu = [(r['cost']['cpuMs'] - r['luck']['cpuMs']) / 1000 for r in e1_src.values()]
    rep_cpu = collections.defaultdict(list)
    for r in luck.values():
        rep_cpu[r['act']].append(r['replays'][0]['cpuMs'] / 1000)
    res = {
        'decision': decision,
        'units': {'e1_ok': len(e1_units), 'e1_bad': e1_bad, 'pilot_ok': len(pilot_units), 'pilot_bad': pilot_bad},
        'seeds': {'e1': len(e1_src), 'pilot': len(p_src), 'both': len(both), 'S': len(S)},
        'gates': {'G1_mismatch_seeds': g1_bad, 'G2_checked': g2_checked, 'G2_mismatch': g2_bad[:50],
                  'G2_mismatch_n': len(g2_bad), 'G2_missing_luck_rows': g2_missing[:50],
                  'G3_identity_fights': len(ident), 'G3_mismatch_by_encounter': dict(g3_bad),
                  'G4_dropped_fights_a123': g4_dropped, 'G4_share': g4_share, 'G5_cells': g5_cells,
                  'G5_pass': g5_pass},
        'counter_relics': counters, 'forks_used': len(fk), 'luck_weight_level': dict(v_level),
        'groups': out_groups,
        'luck_pooled_all_seeds': {'beta_pp': 100 * all_fit['h_a123'][0], 'se_pp': 100 * all_fit['h_a123'][1],
                                  'residual_var': all_resvar},
        'luck_pooled_S': {c: [100 * v[0], 100 * v[1]] for c, v in fits['pooled'][0].items()},
        'residual_var_S': fits['pooled'][1],
        'potions_survival': pots, 'luck_variance': luck_var,
        'heart_rate_e1': float(np.mean([float(e1_src[s]['heartKill']) for s in seeds_all])) if seeds_all else None,
        'cost': {'source_cpu_s_mean': float(np.mean(src_cpu)) if src_cpu else None,
                 'replay_cpu_s_by_act': {a: float(np.mean(v)) for a, v in sorted(rep_cpu.items())},
                 'core_h_total': sum(r['cost']['cpuMs'] for r in e1_src.values()) / 3.6e6,
                 'replay_errors': sum(r['luck']['errors'] for r in e1_src.values()),
                 'replay_health_failures': sum(r['luck']['healthFailures'] for r in e1_src.values())}}
    json.dump(res, open(out_path, 'w'), indent=1, default=float)
    print(json.dumps({'decision': decision, 'seeds': res['seeds'], 'gates': {k: v for k, v in res['gates'].items()
                                                                            if k != 'G5_cells'},
                      'pooled': out_groups.get('pooled'), 'cost': res['cost']}, indent=1, default=float))


if __name__ == '__main__':
    main(*sys.argv[1:4])
