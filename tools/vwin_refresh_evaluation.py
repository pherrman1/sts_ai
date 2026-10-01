"""Predictor-independent A3 offline metrics, probes and decision rules.

No corpus access: callers supply validated rows, rich features and predictions.
Resource conventions match vwin_terminal_pricing_audit (including its sweep
thresholds and fixed-ten-HP local slope); prediction adapters project by name.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations
import re
import numpy as np


def _vectors(labels, predictions):
    y, p = np.asarray(labels, dtype=float), np.asarray(predictions, dtype=float)
    if y.ndim != 1 or p.shape != y.shape or not len(y):
        raise ValueError('nonempty aligned label/prediction vectors required')
    if not np.all(np.isin(y, [0, 1])) or not np.all(np.isfinite(p)) or np.any((p < 0) | (p > 1)):
        raise ValueError('binary labels and finite probability predictions required')
    return y, p


def predictive_metrics(labels, predictions):
    """Row-weighted metrics, stable equal-mass bins (ties retain input order)."""
    y, p = _vectors(labels, predictions)
    clipped = np.clip(p, 1e-15, 1 - 1e-15)
    reliability = []
    for ids in np.array_split(np.argsort(p, kind='stable'), min(10, len(p))):
        reliability.append({'n': len(ids), 'prediction': float(p[ids].mean()),
                            'observed': float(y[ids].mean())})
    order = np.argsort(p, kind='stable')
    sorted_p, sorted_y = p[order], y[order]
    _, starts, counts = np.unique(sorted_p, return_index=True, return_counts=True)
    positives = np.add.reduceat(sorted_y, starts)
    negatives = counts - positives
    below = np.cumsum(negatives) - negatives
    denom = y.sum() * (len(y) - y.sum())
    auc = float(np.sum(positives * (below + .5 * negatives)) / denom) if denom else None
    return {'n': len(y), 'nll': float(-(y * np.log(clipped) + (1-y)*np.log1p(-clipped)).mean()),
            'brier': float(np.mean((p-y)**2)), 'roc_auc': auc,
            'ece': sum(b['n'] * abs(b['prediction']-b['observed']) for b in reliability)/len(y),
            'reliability': reliability}


def evaluate_predictions(labels, predictions, metadata):
    y, p = _vectors(labels, predictions)
    if len(metadata) != len(y):
        raise ValueError('metadata length mismatch')
    groups = defaultdict(list)
    for i, row in enumerate(metadata):
        groups['act:' + str(row['act'])].append(i)
        groups['trajectory:' + ('source' if row['branchId'] == 'source' else 'branch')].append(i)
        # The dataset adapter supplies the source-verified native transition flag.
        if 'preBoss' in row:
            if str(row['preBoss']) not in ('0', '1'):
                raise ValueError('preBoss must be binary')
            groups['preBoss:' + str(row['preBoss'])].append(i)
    return {'overall': predictive_metrics(y, p),
            'breakdowns': {key: predictive_metrics(y[ids], p[ids]) for key, ids in sorted(groups.items())},
            'preboss_status': 'explicit_metadata' if all('preBoss' in r for r in metadata) else 'not_identifiable_for_all_rows',
            'preboss_rules': sorted({r.get('preBossRule', 'supplied_explicit_flag') for r in metadata if 'preBoss' in r})}


def cluster_mean(values, seeds, reps=2000, seed=0):
    """Resample sources, retaining each source's full row multiplicity."""
    values, seeds = np.asarray(values, dtype=float), np.asarray(seeds)
    if values.ndim != 1 or seeds.shape != values.shape or reps < 1:
        raise ValueError('aligned vectors and positive bootstrap repetitions required')
    valid = np.isfinite(values)
    values, seeds = values[valid], seeds[valid]
    unique, inverse = np.unique(seeds, return_inverse=True)
    n = len(unique)
    result = {'mean': float(values.mean()) if len(values) else None, 'n': len(values),
              'source_seeds': n, 'ci95': None,
              'status': 'ok' if n >= 2 else 'insufficient_independent_seeds'}
    if n >= 2:
        sums = np.bincount(inverse, weights=values)
        counts = np.bincount(inverse)
        rng = np.random.default_rng(seed)
        samples = rng.integers(0, n, size=(reps, n))
        draws = sums[samples].sum(axis=1) / counts[samples].sum(axis=1)
        result['ci95'] = np.quantile(draws, [.025, .975]).tolist()
    return result


def clustered_delta(labels, baseline, candidate, seeds, reps=2000, seed=0):
    y, b = _vectors(labels, baseline)
    _, c = _vectors(labels, candidate)
    def loss(p):
        p = np.clip(p, 1e-15, 1-1e-15)
        return -(y*np.log(p)+(1-y)*np.log1p(-p))
    seeds = np.asarray(seeds)
    if seeds.shape != y.shape:
        raise ValueError('source seed vector mismatch')
    unique, inverse = np.unique(seeds, return_inverse=True)
    result = {'direction': 'candidate_minus_B0',
              'nll': cluster_mean(loss(c)-loss(b), seeds, reps, seed),
              'brier': cluster_mean((c-y)**2-(b-y)**2, seeds, reps, seed)}
    bm, cm = predictive_metrics(y, b), predictive_metrics(y, c)
    # Keep one source multiplicity per draw for every row and both predictors.
    # Integer weighted bins are exactly equivalent to materializing repeated rows.
    prepared = []
    for p in (b, c):
        order = np.argsort(p, kind='stable')
        starts = np.unique(p[order], return_index=True)[1]
        prepared.append((order, starts, p[order], y[order]))
    def weighted_secondary(prep, weights):
        order, starts, p, labels = prep
        w = weights[order]
        positive = np.add.reduceat(w*labels, starts)
        negative = np.add.reduceat(w*(1-labels), starts)
        denom = positive.sum()*negative.sum()
        auc = float(np.sum(positive*(np.cumsum(negative)-negative+.5*negative))/denom) if denom else np.nan
        keep = w > 0
        w, p, labels = w[keep], p[keep], labels[keep]
        n = int(w.sum())
        bins = min(10, n)
        sizes = np.full(bins, n//bins)
        sizes[:n % bins] += 1
        edges = np.r_[0, np.cumsum(sizes)]
        mass = np.r_[0, np.cumsum(w)]
        psum = np.interp(edges, mass, np.r_[0, np.cumsum(w*p)])
        ysum = np.interp(edges, mass, np.r_[0, np.cumsum(w*labels)])
        ece = float(np.abs(np.diff(psum)-np.diff(ysum)).sum()/n)
        return auc, ece
    draws = {'roc_auc': [], 'ece': []}
    if len(unique) >= 2:
        rng = np.random.default_rng(seed)
        for _ in range(reps):
            multiplicity = np.bincount(rng.integers(0, len(unique), len(unique)), minlength=len(unique))
            weights = multiplicity[inverse]
            bv, cv = (weighted_secondary(p, weights) for p in prepared)
            for i, key in enumerate(draws):
                if np.isfinite(bv[i]) and np.isfinite(cv[i]):
                    draws[key].append(cv[i]-bv[i])
    for key, values in draws.items():
        result[key] = {'mean': cm[key]-bm[key] if cm[key] is not None and bm[key] is not None else None,
                       'ci95': np.quantile(values, [.025,.975]).tolist() if values else None,
                       'valid_bootstrap_replicates': len(values), 'source_seeds': len(unique)}
    return result



def resource_probes(predictor, X, feature_names, metadata, kind='MAP', reps=2000, seed=0):
    """Pass full rich state to a predictor adapter, never the TRAIN mask alone."""
    X = np.asarray(X, dtype=np.float32).copy()
    if X.ndim != 2 or X.shape != (len(metadata), len(feature_names)) or not len(X):
        raise ValueError('nonempty aligned rich feature matrix required')
    if len(set(feature_names)) != len(feature_names) or not np.all(np.isfinite(X)):
        raise ValueError('unique features and finite rich states required')
    if kind not in ('MAP', 'WIN_RAW'):
        raise ValueError('kind must be MAP or WIN_RAW')
    idx = {name: i for i, name in enumerate(feature_names)}
    for name in ('curHp', 'maxHp', 'gold', 'potionCount'):
        if name not in idx:
            raise ValueError('missing resource feature ' + name)
    corrected = 0
    if kind == 'WIN_RAW':
        for i, row in enumerate(metadata):
            if str(row.get('actBoss')) not in ('0', '1'):
                raise ValueError('WIN_RAW requires explicit binary actBoss')
            if int(row['actBoss']):
                X[i, idx['curHp']] = float(row['postAfterBattleHp'])
                corrected += 1
    hp, maximum = X[:, idx['curHp']], X[:, idx['maxHp']]
    if not np.all(np.isfinite(hp)) or np.any(hp != np.floor(hp)) or np.any(hp < 1) or np.any(hp > maximum) or np.any(maximum != maximum.astype(int)):
        raise ValueError('invalid living-state HP')
    pots = [name for name in feature_names if re.fullmatch(r'pot\d+', name)]
    counts = X[:, [idx[name] for name in pots]]
    if np.any(counts < 0) or np.any(counts != np.floor(counts)) or not np.array_equal(counts.sum(axis=1), X[:, idx['potionCount']]):
        raise ValueError('rich potion features/count disagree')
    def predict(matrix):
        result = np.asarray(predictor(matrix), dtype=float)
        _vectors(np.zeros(len(matrix)), result)
        return result
    def changed(changes):
        other = X.copy()
        for name, value in changes.items():
            other[:, idx[name]] = value
        return predict(other)
    base = predict(X)
    slopes = (changed({'curHp': np.minimum(maximum, hp+5)}) - changed({'curHp': np.maximum(1, hp-5)}))/10
    monotone, flats = [], []
    # Bound the expanded rich matrix; batch complete sweeps to avoid one tree
    # interpreter call per state. Even an unusually large maxHp is chunked.
    pending, pending_lengths, pending_rows = [], [], 0
    def consume_sweeps():
        if not pending:
            return
        expanded = np.concatenate(pending)
        predictions = np.concatenate([predict(expanded[i:i+8192])
                                      for i in range(0, len(expanded), 8192)])
        offset = 0
        for max_hp in pending_lengths:
            delta = np.diff(predictions[offset:offset+max_hp])
            offset += max_hp
            monotone.append(not np.any(delta < -.005))
            flat = np.abs(delta[:max(0, int(np.ceil(.6*max_hp))-1)]) < 1e-6
            best = current = 0
            for item in flat:
                current = current+1 if item else 0
                best = max(best, current)
            flats.append(best)
    for row, max_hp in zip(X, maximum.astype(int)):
        if pending_rows and pending_rows + max_hp > 8192:
            consume_sweeps()
            pending, pending_lengths, pending_rows = [], [], 0
        sweep = np.repeat(row[None, :], max_hp, axis=0)
        sweep[:, idx['curHp']] = np.arange(1, max_hp+1)
        pending.append(sweep)
        pending_lengths.append(max_hp)
        pending_rows += max_hp
    consume_sweeps()
    potion_sum, potion_n = np.zeros(len(X)), np.zeros(len(X))
    for name in pots:
        held = X[:, idx[name]] > 0
        if np.any(held):
            other = X[held].copy()
            other[:, idx[name]] -= 1
            other[:, idx['potionCount']] -= 1
            potion_sum[held] += base[held] - predict(other)
            potion_n[held] += 1
    potion = np.divide(potion_sum, potion_n, out=np.full(len(X), np.nan), where=potion_n > 0)
    gold = X[:, idx['gold']]
    if np.any(gold < 0):
        raise ValueError('negative gold')
    lo, hi = np.maximum(0, gold-25), gold+25
    gold_delta = (changed({'gold': hi})-changed({'gold': lo}))/(hi-lo)
    feed = changed({'curHp': hp+1, 'maxHp': maximum+1})-base
    max_only = changed({'maxHp': maximum+1})-base
    seeds = np.array([r['sourceSeed'] for r in metadata])
    acts = np.array([int(r['act']) for r in metadata])
    by_act = {}
    for act in sorted(set(acts.tolist()) | {1, 2, 3}):
        mask = acts == act
        by_act[str(act)] = {'hp_slope': cluster_mean(slopes[mask], seeds[mask], reps, seed),
                            'held_potion_delta': cluster_mean(potion[mask], seeds[mask], reps, seed),
                            'gold_per_unit': cluster_mean(gold_delta[mask], seeds[mask], reps, seed),
                            'feed_delta': cluster_mean(feed[mask], seeds[mask], reps, seed),
                            'max_hp_only_delta': cluster_mean(max_only[mask], seeds[mask], reps, seed)}
    positive = lambda s: s['mean'] is not None and s['mean'] > 0 and s['ci95'] is not None and s['ci95'][0] > 0
    share, median_flat = float(np.mean(monotone)), float(np.median(flats))
    gate = share >= .95 and median_flat <= 10 and all(positive(a[key]) for a in by_act.values() for key in ('hp_slope', 'held_potion_delta'))
    return {'kind': kind, 'n': len(X), 'act_boss_hp_corrections': corrected,
            'hp_sweep_monotone_share': share, 'median_longest_flat_run': median_flat,
            'semantics': {'monotone_drop_tolerance': .005, 'flat_tolerance': 1e-6,
                          'flat_hp_fraction': .6, 'local_slope_denominator': 10,
                          'held_potion': 'row mean across distinct held potion IDs'},
            'by_act': by_act, 'resource_gate': bool(gate),
            'gold_per_unit': cluster_mean(gold_delta, seeds, reps, seed),
            'feed_delta': cluster_mean(feed, seeds, reps, seed),
            'max_hp_only_delta': cluster_mean(max_only, seeds, reps, seed)}


def sibling_ranking(map_metadata, predictions, branches, reps=2000, seed=0):
    predictions = np.asarray(predictions, dtype=float)
    if predictions.shape != (len(map_metadata),) or not np.all(np.isfinite(predictions)):
        raise ValueError('aligned finite MAP scores required')
    first, seen_rows = {}, set()
    for row, score in zip(map_metadata, predictions):
        key = int(row['sourceSeed']), row['branchId']
        ordinal = int(row['rowIdx'])
        if (*key, ordinal) in seen_rows:
            raise ValueError('duplicate MAP row identity')
        seen_rows.add((*key, ordinal))
        if key not in first or ordinal < first[key][0]:
            first[key] = ordinal, float(score)
    decisions, seen_branches, types = defaultdict(list), set(), set()
    missing, missing_by_type = 0, defaultdict(int)
    for branch in branches:
        key = int(branch['sourceSeed']), branch['branchId']
        if key in seen_branches:
            raise ValueError('duplicate branch identity')
        seen_branches.add(key)
        typ = str(branch['type'])
        types.add(typ)
        if str(branch['valid']) != '1' or str(branch['won']) not in ('0', '1'):
            raise ValueError('invalid branch outcome')
        if key not in first:
            missing += 1
            missing_by_type[typ] += 1
            continue
        decision = key[0], int(branch['decisionIdx']), typ
        decisions[decision].append((first[key][1], int(branch['won'])))
    credits = {typ: [] for typ in types}
    pooled = []
    for (source, _, typ), options in decisions.items():
        for (a, ya), (b, yb) in combinations(options, 2):
            if ya == yb:
                continue
            credit = .5 if a == b else float((a > b) == (ya > yb))
            credits[typ].append((credit, source))
            pooled.append((credit, source))
    def summary(pairs):
        return cluster_mean([p[0] for p in pairs], [p[1] for p in pairs], reps, seed)
    return {'pooled': summary(pooled), 'by_decision_type': {k: summary(v) for k, v in sorted(credits.items())},
            'branches_without_map': missing, 'branches_without_map_by_type': dict(missing_by_type),
            'total_branches': len(seen_branches), 'join': 'sourceSeed/branchId; minimum recorded rowIdx'}


def offline_verdict(arms):
    """Pure later-execution rule. Never implies terminal-pricing readiness."""
    names = {'X1': 'VWIN_OFFLINE_XGB', 'X2': 'VWIN_OFFLINE_XGB_MONO', 'M1': 'VWIN_OFFLINE_MLP'}
    if set(arms) != set(names):
        raise ValueError('all three frozen candidates are required')
    qualified = []
    for name, result in arms.items():
        ci = result['nll_delta_ci95']
        if not np.isfinite(result['nll']):
            raise ValueError('finite TEST NLL required')
        if ci is not None and len(ci) == 2 and np.all(np.isfinite(ci)) and ci[0] <= ci[1] < 0 and result['map_resource_gate']:
            qualified.append(name)
    tied = []
    provisional_best = min(qualified, key=lambda name: arms[name]['nll']) if qualified else None
    if qualified:
        best = min(arms[name]['nll'] for name in qualified)
        tied = sorted(name for name in qualified if arms[name]['nll'] <= best + .003)
    verdict = 'VWIN_OFFLINE_NO_CANDIDATE' if not tied else names[tied[0]] if len(tied) == 1 else 'VWIN_OFFLINE_TIE_NEEDS_SPEED'
    return {'verdict': verdict, 'qualified': sorted(qualified), 'tied': tied,
            'provisional_best': provisional_best,
            'win_raw_resource_gate': {name: bool(r['win_raw_resource_gate']) for name, r in arms.items()},
            'terminal_pricing_ready': False}
