"""Pure offline #379 metrics; this module never opens a corpus or TEST latch."""
from collections import defaultdict

import numpy as np

from tools.vwin_refresh_evaluation import cluster_mean, clustered_delta, predictive_metrics


def _groups(metadata):
    groups = {'overall': np.arange(len(metadata))}
    for field in ('screen', 'act'):
        for value in sorted({r[field] for r in metadata}, key=str):
            groups[f'{field}:{value}'] = np.array([i for i, r in enumerate(metadata) if r[field] == value])
    return groups


def predictive_report(labels, predictions, metadata, baseline=None, reps=2000):
    y, p = np.asarray(labels), np.asarray(predictions)
    if y.ndim != 1 or len(metadata) != len(y) or p.shape != y.shape or (baseline is not None and np.asarray(baseline).shape != y.shape):
        raise ValueError('unaligned prediction population')
    result = {}
    for name, ids in _groups(metadata).items():
        seeds = np.array([metadata[i]['sourceSeed'] for i in ids])
        yy, pp = y[ids], p[ids]
        metrics = predictive_metrics(yy, pp, seeds)
        clipped = np.clip(pp, 1e-15, 1 - 1e-15)
        metrics['nll_clustered'] = cluster_mean(-(yy * np.log(clipped) + (1 - yy) * np.log1p(-clipped)), seeds, reps, 379)
        metrics['brier_clustered'] = cluster_mean((pp - yy) ** 2, seeds, reps, 379)
        metrics['base_rate_clustered'] = cluster_mean(yy, seeds, reps, 379)
        # Resample complete source clusters for nonlinear AUC/ECE. Repeated
        # source draws retain every row, including branch multiplicity.
        unique = np.unique(seeds)
        grouped = [np.flatnonzero(seeds == source) for source in unique]
        draws = {'ece': [], 'roc_auc': []}
        if len(unique) >= 2:
            rng = np.random.default_rng(379)
            for _ in range(reps):
                sample = np.concatenate([grouped[i] for i in rng.integers(0, len(unique), len(unique))])
                stats = predictive_metrics(yy[sample], pp[sample])
                for metric in draws:
                    if stats[metric] is not None: draws[metric].append(stats[metric])
        for metric, values in draws.items():
            metrics[metric + '_clustered'] = {'ci95': np.quantile(values, [.025, .975]).tolist() if values else None,
                                             'valid_replicates': len(values), 'source_count': len(unique)}
        if baseline is not None:
            metrics['delta_vs_S0'] = clustered_delta(yy, np.asarray(baseline)[ids], pp, seeds, reps, 379)
        result[name] = metrics
    return result


def transition_report(screen_predictions, map_predictions, metadata, reps=2000):
    """Caller must prove matching; no nearest-row or inferred trajectory join."""
    screen, maps = np.asarray(screen_predictions, float), np.asarray(map_predictions, float)
    if screen.shape != maps.shape or screen.ndim != 1 or len(metadata) != len(screen):
        raise ValueError('unaligned matched transitions')
    if not len(screen) or not np.isfinite(screen).all() or not np.isfinite(maps).all():
        raise ValueError('empty or nonfinite matched transitions')
    if np.any((screen < 0) | (screen > 1) | (maps < 0) | (maps > 1)):
        raise ValueError('transition predictions outside probability domain')
    groups = _groups(metadata)
    for act, family in sorted({(r['act'], r['screen']) for r in metadata}):
        groups[f'act:{act}/screen:{family}'] = np.array([i for i, r in enumerate(metadata) if (r['act'], r['screen']) == (act, family)])
    result = {}
    for name, ids in groups.items():
        delta = screen[ids] - maps[ids]
        seeds = np.array([metadata[i]['sourceSeed'] for i in ids])
        bins = np.array_split(np.argsort(screen[ids], kind='stable'), min(10, len(ids)))
        result[name] = {'n': len(ids), 'source_count': len(np.unique(seeds)),
                        'signed_delta': cluster_mean(delta, seeds, reps, 379),
                        'absolute_delta': cluster_mean(np.abs(delta), seeds, reps, 379),
                        'p90_absolute_delta': float(np.quantile(np.abs(delta), .90)),
                        'p95_absolute_delta': float(np.quantile(np.abs(delta), .95)),
                        'reliability_to_X2B': [{'n': len(b), 'screen_mean': float(screen[ids][b].mean()),
                                                'map_mean': float(maps[ids][b].mean())} for b in bins]}
    return result


def calibration_gate(report, frozen_tolerances):
    """Apply an already frozen numeric contract; never derive it from TEST."""
    if set(map(str, frozen_tolerances)) != {'1', '2', '3'}:
        raise ValueError('frozen calibration contract must cover acts 1,2,3')
    if any(set(t) != {'absolute_signed_mean', 'mae', 'p95_absolute_delta', 'minimum_sources'}
           or any(not np.isfinite(v) or v < 0 for v in t.values()) for t in frozen_tolerances.values()):
        raise ValueError('invalid frozen calibration tolerance')
    results = {}
    for act, tolerances in frozen_tolerances.items():
        key = f'act:{act}'
        if key not in report:
            results[key] = {'pass': False, 'reason': 'missing_matched_act'}
            continue
        row = report[key]
        checks = {'absolute_signed_mean': abs(row['signed_delta']['mean']) <= tolerances['absolute_signed_mean'],
                  'mae': row['absolute_delta']['mean'] <= tolerances['mae'],
                  'p95_absolute_delta': row['p95_absolute_delta'] <= tolerances['p95_absolute_delta'],
                  'minimum_sources': row['source_count'] >= tolerances['minimum_sources']}
        results[key] = {'pass': all(checks.values()), 'checks': checks}
    return {'pass': bool(results) and all(r['pass'] for r in results.values()), 'by_act': results}


def qualification(labels, candidate, baseline, metadata, replacement_mask, calibration):
    """Literal #379 point-NLL and calibration rule; never alters coverage."""
    y, c, b = map(np.asarray, (labels, candidate, baseline))
    if y.ndim != 1 or c.shape != y.shape or b.shape != y.shape or len(metadata) != len(y):
        raise ValueError('unaligned qualification inputs')
    if len(set(replacement_mask)) != len(replacement_mask):
        raise ValueError('duplicate replacement family')
    screens = np.array([r['screen'] for r in metadata])
    results = {}
    for family in replacement_mask:
        ids = np.flatnonzero(screens == family)
        if not len(ids):
            results[family] = {'pass': False, 'reason': 'missing_replacement_family'}
            continue
        cm, bm = predictive_metrics(y[ids], c[ids]), predictive_metrics(y[ids], b[ids])
        results[family] = {'candidate_nll': cm['nll'], 'S0_nll': bm['nll'], 'pass': cm['nll'] < bm['nll']}
    passed = bool(results) and all(r['pass'] for r in results.values()) and calibration['pass']
    return {'classification': 'SCREEN_LEAF_OFFLINE_QUALIFIED' if passed else 'SCREEN_LEAF_OFFLINE_NOT_QUALIFIED',
            'by_screen': results, 'calibration': calibration}
