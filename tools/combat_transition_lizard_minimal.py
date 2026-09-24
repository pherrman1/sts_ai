#!/usr/bin/env python3
"""Offline, source-cross-validated minimal active Lizard Tail diagnostic.

This consumes the already frozen paired cohort. It trains only tiny logistic
calibrators for analysis, never exports weights, and does not alter runtime
support. Postcombat heads remain the existing frozen CTM heads.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from tools import combat_transition_composed as composed
from tools import combat_transition_lizard_pair_pilot as pilot
from tools import combat_transition_composed_evaluate as evaluate
from tools.combat_transition_contract import validate_state

WIN_RETAINED, WIN_CONSUMED, LOSS_CONSUMED = range(3)
CLASS_NAMES = ('WIN_RETAINED', 'WIN_CONSUMED', 'LOSS_CONSUMED')
HP_TREATMENTS = ('T0_ordinary', 'T1_reserve', 'T2_revive')
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 20260925
CV_FOLDS = 5
CV_SEED = 20260926
L2 = 1.0


def hp_treatment(cur_hp: int, max_hp: int, treatment: str) -> int:
    """Return one of the three fixed, preregistered conditional-head inputs."""
    if type(cur_hp) is not int or type(max_hp) is not int or not 1 <= cur_hp <= max_hp:
        raise ValueError('invalid starting HP')
    if treatment == 'T0_ordinary':
        return cur_hp
    reserve = max_hp // 2
    if treatment == 'T1_reserve':
        return min(max_hp, cur_hp + reserve)
    if treatment == 'T2_revive':
        if reserve < 1:
            raise ValueError('revive HP outside legal state domain')
        return reserve
    raise ValueError(f'unknown fixed HP treatment: {treatment}')


def legal_class_probabilities(p_ordinary_win: float, p_reserve_win: float,
                              *, epsilon: float = 1e-12) -> tuple[float, float, float] | None:
    """Mechanical reserve factorization; None marks materially incoherent rows."""
    values = (p_ordinary_win, p_reserve_win)
    if any(not math.isfinite(x) or not 0.0 <= x <= 1.0 for x in values):
        raise ValueError('win probabilities must be finite and in [0,1]')
    middle = p_reserve_win - p_ordinary_win
    if middle < -epsilon:
        return None
    if middle < 0.0:  # only erase floating-point noise, never model non-monotonicity
        middle = 0.0
    return (p_ordinary_win, middle, 1.0 - p_reserve_win)


def legal_outcome_label(outcome: int, tail_post_data: int) -> int:
    """Map a recorded active-Tail combat to its only legal terminal class."""
    if tail_post_data not in (0, 1):
        raise ValueError('invalid active Tail post-state')
    if outcome == pilot.WIN:
        return WIN_CONSUMED if tail_post_data == 0 else WIN_RETAINED
    if outcome == pilot.DEATH:
        if tail_post_data != 0:
            raise ValueError('LOSS_RETAINED is impossible')
        return LOSS_CONSUMED
    raise ValueError('active Tail outcome is undecided')


def source_group_folds(sources, folds: int = CV_FOLDS, seed: int = CV_SEED) -> np.ndarray:
    """Deterministic balanced folds that never split one source across folds."""
    source_values = list(sources)
    unique = sorted(set(source_values), key=lambda value: (type(value).__name__, str(value)))
    if folds < 2 or len(unique) < folds:
        raise ValueError('source-group CV needs at least one distinct group per fold')
    permutation = np.random.default_rng(seed).permutation(len(unique))
    assignments = {unique[index]: position % folds
                   for position, index in enumerate(permutation)}
    return np.asarray([assignments[source] for source in source_values], dtype=np.int64)


def logistic_fit(features, labels, *, l2: float = L2, iterations: int = 100):
    """Small deterministic L2 logistic fit with an unpenalized intercept."""
    x = np.asarray(features, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if x.ndim != 2 or y.shape != (len(x),) or not len(y):
        raise ValueError('invalid logistic training arrays')
    if not np.isfinite(x).all() or not np.isfinite(y).all() or np.any((y != 0) & (y != 1)):
        raise ValueError('non-finite logistic input or non-binary labels')
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale < 1e-8] = 1.0
    standardized = (x - mean) / scale
    design = np.column_stack((np.ones(len(x)), standardized))
    penalty = np.diag(np.r_[0.0, np.full(x.shape[1], float(l2))])
    prevalence = np.clip(y.mean(), 1e-6, 1 - 1e-6)
    beta = np.r_[math.log(prevalence / (1 - prevalence)), np.zeros(x.shape[1])]
    for _ in range(iterations):
        z = design @ beta
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -40, 40)))
        gradient = design.T @ (p - y) + penalty @ beta
        weights = np.maximum(p * (1 - p), 1e-10)
        hessian = (design.T * weights) @ design + penalty
        step = np.linalg.solve(hessian, gradient)
        beta -= step
        if float(np.max(np.abs(step))) < 1e-10:
            break
    raw = beta[1:] / scale
    raw_intercept = beta[0] - float(raw @ mean)
    return {
        'mean': mean, 'scale': scale, 'standardizedCoefficients': beta,
        'coefficients': np.r_[raw_intercept, raw],
        'converged': bool(float(np.max(np.abs(step))) < 1e-8),
    }


def logistic_predict(model, features):
    x = np.asarray(features, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    z = np.column_stack((np.ones(len(x)), (x - model['mean']) / model['scale'])) @ model['standardizedCoefficients']
    return 1.0 / (1.0 + np.exp(-np.clip(z, -40, 40)))


def _prob_metrics(probabilities, labels):
    p = np.asarray(probabilities, dtype=np.float64)
    y = np.asarray(labels, dtype=np.int64)
    if p.ndim != 2 or p.shape != (len(y), 3) or not len(y):
        return {'rows': 0, 'nll': None, 'multiclassBrier': None,
                'modeAccuracy': None, 'perClass': {name: None for name in CLASS_NAMES}}
    if not np.isfinite(p).all() or np.any(p < 0) or not np.allclose(p.sum(axis=1), 1.0, atol=1e-8):
        raise ValueError('invalid three-class probabilities')
    onehot = np.eye(3)[y]
    return {
        'rows': len(y),
        'threeClassNll': float(np.mean(-np.log(np.maximum(p[np.arange(len(y)), y], 1e-300)))),
        'multiclassBrier': float(np.mean(np.sum((p - onehot) ** 2, axis=1))),
        'modeAccuracy': float(np.mean(np.argmax(p, axis=1) == y)),
        'confusionActualRowsPredictedColumns': [
            [int(np.sum((y == actual) & (np.argmax(p, axis=1) == predicted)))
             for predicted in range(3)] for actual in range(3)],
        'perClass': {
            name: {
                'count': int(np.sum(y == i)), 'observedRate': float(np.mean(y == i)),
                'meanPredictedProbability': float(np.mean(p[:, i])),
            } for i, name in enumerate(CLASS_NAMES)
        },
    }


def _binary_metrics(probabilities, labels):
    p = np.asarray(probabilities, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    if not len(y):
        return {'rows': 0, 'brier': None, 'nll': None, 'observedRate': None, 'meanPredicted': None}
    p = np.clip(p, 1e-15, 1 - 1e-15)
    return {
        'rows': len(y), 'brier': float(np.mean((p - y) ** 2)),
        'nll': float(np.mean(-(y * np.log(p) + (1 - y) * np.log(1 - p)))),
        'observedRate': float(y.mean()), 'meanPredicted': float(p.mean()),
    }


def _conditioned_pre(pair, treatment):
    ordinary = pair['noTail']
    pre = copy.deepcopy(ordinary['transition']['pre'])
    predictor = copy.deepcopy(ordinary['predictorInput'])
    transformed = hp_treatment(int(pre['curHp']), int(pre['maxHp']), treatment)
    pre['curHp'] = transformed
    predictor['globals']['curHp'] = transformed
    return pre, predictor, transformed


def _crps(probabilities, target_index):
    p = np.asarray(probabilities, dtype=np.float64)
    observed = np.zeros(len(p), dtype=np.float64)
    observed[target_index:] = 1.0
    return float(np.sum((np.cumsum(p) - observed) ** 2))


def transformed_hp_domain_issue_count(failures):
    """Count target/input exclusions caused by the frozen HP domain."""
    domain_reasons = {
        'transformed_HP_target_outside_frozen_domain',
        'observed_HP_outside_legal_domain',
        'unsupported:hp_domain',
        'unsupported:hp_envelope',
    }
    return sum(int(count) for reason, count in failures.items() if reason in domain_reasons)


def score_hp_treatment(pairs, models, treatment):
    """Teacher-force the existing post heads under one fixed HP input map."""
    candidate_rows = [pair for pair in pairs
                      if int(pair['activeTail']['transition']['combatOutcome']) == pilot.WIN
                      and int(pair['pair']['activeTailPostData']) == 0]
    fields = ('hpNll', 'hpCrps', 'expectedHpAbsError', 'maxHpNll', 'potionMaskNll')
    scores = {field: [] for field in fields}
    relic_scores = {group: [] for group in models.trained_groups}
    per_source = {}
    failures = Counter()
    torch = models.torch
    for pair in candidate_rows:
        source = int(pair['pair']['sourceSeed'])
        row = pair['activeTail']
        actual_pre = pair['noTail']['transition']['pre']
        post = pilot._strip_lizard(row['transition']['post'])
        try:
            pre, predictor, transformed_hp = _conditioned_pre(pair, treatment)
            reasons = composed.full_support_reasons(pre, predictor, models)
            if reasons:
                failures['unsupported:' + ','.join(reasons)] += 1
                continue
            inputs = models.encode_visible(predictor)
            arrays = composed.visible_arrays(predictor)
            max_delta = int(post['maxHp']) - int(actual_pre['maxHp'])
            delta_index = {int(value): i for i, value in enumerate(models.delta_values)}.get(max_delta)
            if delta_index is None:
                failures['maxHP_delta_outside_frozen_domain'] += 1
                continue
            ending = int(post['curHp'])
            signed_target = ending - transformed_hp
            target_index = signed_target - int(models.classes[0])
            if not 0 <= target_index < len(models.classes):
                failures['transformed_HP_target_outside_frozen_domain'] += 1
                continue
            if not 1 <= ending <= int(post['maxHp']):
                failures['observed_HP_outside_legal_domain'] += 1
                continue
            with torch.inference_mode():
                p_delta = evaluate.probabilities(models.max_net.max_hp_delta(
                    models.fp32_encoding(models.max_net.encoder, inputs)))[0]
                z = models.hp_encoding(inputs).cpu().numpy()
                p_hp = evaluate.hp_prob(models, z, np.asarray([delta_index]),
                                        np.asarray([transformed_hp]),
                                        np.asarray([int(post['maxHp'])]))[0]
                hp_expected = transformed_hp + float(np.dot(p_hp, models.classes))
                potion_z = models.fp32_encoding(models.potion_encoder.encoder, inputs).cpu().numpy()
                capacity = int(pre['potionCapacity'])
                potion_mask = int(composed.potion.encode_masks(
                    np.asarray([pre['potions']]), np.asarray([post['potions']]),
                    np.asarray([capacity]))[0])
                slots = arrays['potions'][:, :, 1].astype(np.int64)[0]
                ending_fraction = np.asarray([ending / int(post['maxHp'])], dtype=np.float32)
                p_potion = evaluate.potion_prob(
                    models, potion_z, slots[None], np.asarray([capacity]),
                    np.asarray([delta_index]), ending_fraction)[0]
                p_relic = evaluate.relic_prob(
                    models, z, np.asarray([target_index]), ending_fraction,
                    np.asarray([potion_mask], dtype=np.int64))
            observed_hp_nll = -math.log(max(float(p_hp[target_index]), 1e-300))
            observed_hp_crps = _crps(p_hp, target_index)
            max_nll = -math.log(max(float(p_delta[delta_index]), 1e-300))
            potion_nll = -math.log(max(float(p_potion[potion_mask]), 1e-300))
            scores['hpNll'].append(observed_hp_nll)
            scores['hpCrps'].append(observed_hp_crps)
            scores['expectedHpAbsError'].append(abs(hp_expected - ending))
            scores['maxHpNll'].append(max_nll)
            scores['potionMaskNll'].append(potion_nll)
            allowed = composed.relic.trajectory_constraints(
                pre['relics'], post['relics'], predictor['globals']['encounter'], False)
            relic_row = {}
            for group in models.trained_groups:
                if group not in allowed or group not in p_relic:
                    continue
                mass = float(np.asarray(p_relic[group])[0, list(allowed[group])].sum())
                nll = -math.log(max(mass, 1e-300))
                relic_scores[group].append(nll)
                relic_row[group] = nll
            per_source[source] = {
                'hpNll': observed_hp_nll, 'hpCrps': observed_hp_crps,
                'expectedHpAbsError': abs(hp_expected - ending),
                'maxHpNll': max_nll, 'potionMaskNll': potion_nll,
                'relicConstraintNllByGroup': relic_row,
            }
        except (KeyError, ValueError, IndexError, RuntimeError) as error:
            reason = f'{type(error).__name__}:{error}'
            failures[reason] += 1
    return {
        'candidateRows': len(candidate_rows), 'scoredRowsByMetric': {key: len(value) for key, value in scores.items()},
        'metrics': {key: float(np.mean(value)) if value else None for key, value in scores.items()},
        'supportedRelicGroupConstraintNll': {
            group: {'rows': len(values), 'meanNll': float(np.mean(values)) if values else None}
            for group, values in relic_scores.items()},
        'unscoreableBecauseTransformedTargetOutsideModelDomain': transformed_hp_domain_issue_count(failures),
        'unscoredReasons': dict(sorted(failures.items())), 'perSourceScores': per_source,
    }


def _paired_bootstrap_delta(control, treatment, *, reps=BOOTSTRAP_REPS, seed=BOOTSTRAP_SEED):
    shared = sorted(set(control['perSourceScores']) & set(treatment['perSourceScores']))
    metrics = ('hpNll', 'hpCrps', 'expectedHpAbsError', 'maxHpNll', 'potionMaskNll')
    rng = np.random.default_rng(seed)
    result = {}
    for metric in metrics:
        differences = np.asarray([
            treatment['perSourceScores'][source][metric] - control['perSourceScores'][source][metric]
            for source in shared], dtype=np.float64)
        if len(differences):
            boot = differences[rng.integers(0, len(differences), size=(reps, len(differences)))].mean(axis=1)
            result[metric] = {
                'pairs': len(differences), 'meanTreatmentMinusT0': float(differences.mean()),
                'sourceBootstrap95CI': [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))],
            }
        else:
            result[metric] = {'pairs': 0, 'meanTreatmentMinusT0': None, 'sourceBootstrap95CI': None}
    groups = set()
    for source in shared:
        groups.update(control['perSourceScores'][source]['relicConstraintNllByGroup'])
        groups.update(treatment['perSourceScores'][source]['relicConstraintNllByGroup'])
    relic_results = {}
    for group in sorted(groups):
        sources = [source for source in shared
                   if group in control['perSourceScores'][source]['relicConstraintNllByGroup']
                   and group in treatment['perSourceScores'][source]['relicConstraintNllByGroup']]
        differences = np.asarray([
            treatment['perSourceScores'][source]['relicConstraintNllByGroup'][group]
            - control['perSourceScores'][source]['relicConstraintNllByGroup'][group]
            for source in sources], dtype=np.float64)
        if len(differences):
            boot = differences[rng.integers(0, len(differences), size=(reps, len(differences)))].mean(axis=1)
            relic_results[group] = {
                'pairs': len(differences), 'meanTreatmentMinusT0': float(differences.mean()),
                'sourceBootstrap95CI': [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))],
            }
        else:
            relic_results[group] = {'pairs': 0, 'meanTreatmentMinusT0': None,
                                    'sourceBootstrap95CI': None}
    result['supportedRelicGroupConstraintNllByGroup'] = relic_results
    return result


def _paired_probability_comparison(baseline, candidate, labels, *, reps=BOOTSTRAP_REPS,
                                   seed=BOOTSTRAP_SEED + 1):
    baseline = np.asarray(baseline, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int64)
    target = np.eye(3)[labels]
    selected = np.arange(len(labels))
    base_nll = -np.log(np.maximum(baseline[selected, labels], 1e-300))
    candidate_nll = -np.log(np.maximum(candidate[selected, labels], 1e-300))
    base_brier = np.sum((baseline-target)**2, axis=1)
    candidate_brier = np.sum((candidate-target)**2, axis=1)
    rng = np.random.default_rng(seed)
    output = {}
    for name, delta in (('threeClassNll', candidate_nll-base_nll),
                        ('multiclassBrier', candidate_brier-base_brier)):
        boot = delta[rng.integers(0, len(delta), size=(reps, len(delta)))].mean(axis=1)
        output[name] = {'pairs': len(delta), 'meanCorrectionMinusB1': float(delta.mean()),
                        'sourceBootstrap95CI': [float(np.quantile(boot,.025)),
                                                float(np.quantile(boot,.975))]}
    return output


def _get_three_class_label(pair):
    return legal_outcome_label(int(pair['activeTail']['transition']['combatOutcome']),
                               int(pair['pair']['activeTailPostData']))


def native_boundary_reasons(pair):
    """Relics/potions handled by native precedence stay outside calibration."""
    pre = pair['activeTail']['transition']['pre']
    reasons = []
    bloom = composed.base._RELIC_IDS['MARK_OF_THE_BLOOM']
    fairy = composed.base._POTION_IDS['FAIRY_POTION']
    if any(int(item['id']) == bloom for item in pre['relics']):
        reasons.append('mark_of_bloom_exact_boundary')
    if fairy in pre['potions']:
        reasons.append('fairy_potion_precedence_exact_boundary')
    return reasons


def _derive_features(pairs, models):
    """Extract precombat features first, then attach outcomes strictly as labels."""
    records = _precombat_risk_features(pairs, models)
    for record, pair in zip(records, pairs):
        record['label'] = _get_three_class_label(pair)
    return records


def _precombat_risk_features(pairs, models):
    """No realized-outcome, post-state, or action-trace fields are read here."""
    records = []
    for pair in pairs:
        predictor = pair['noTail']['predictorInput']
        maximum = int(predictor['globals']['maxHp'])
        ordinary_hp = int(predictor['globals']['curHp'])
        reserve_input = copy.deepcopy(predictor)
        reserve_input['globals']['curHp'] = min(maximum, ordinary_hp + maximum // 2)
        p_ordinary_win = models.survival(models.encode_visible(predictor))
        p_reserve_win = models.survival(models.encode_visible(reserve_input))
        records.append({
            'sourceSeed': int(pair['pair']['sourceSeed']),
            'pOrdinaryWin': p_ordinary_win, 'pDeath': 1.0 - p_ordinary_win,
            'pReserveWin': p_reserve_win,
            'reserveUplift': p_reserve_win - p_ordinary_win,
            'startHpFraction': ordinary_hp / maximum,
        })
    return records


def factorized_feature_arrays(records):
    """Return the only inputs available to q and r calibration."""
    p_death = np.asarray([row['pDeath'] for row in records], dtype=np.float64)
    p_ordinary = np.asarray([row['pOrdinaryWin'] for row in records], dtype=np.float64)
    p_reserve = np.asarray([row['pReserveWin'] for row in records], dtype=np.float64)
    q_features = np.column_stack((
        np.log(np.clip(p_death, 1e-8, 1-1e-8) / np.clip(1-p_death, 1e-8, 1)),
        p_reserve-p_ordinary,
    ))
    return q_features, p_reserve[:, None]


def _factorized_cv(records, folds=CV_FOLDS):
    sources = [row['sourceSeed'] for row in records]
    fold_ids = source_group_folds(sources, folds, CV_SEED)
    labels = np.asarray([row['label'] for row in records], dtype=np.int64)
    # Features are fixed before the labels are read: ordinary risk and reserve uplift for q;
    # reserve win probability alone for conditional rescue r.
    q_x, r_x = factorized_feature_arrays(records)
    p_death = np.asarray([row['pDeath'] for row in records], dtype=np.float64)
    p_reserve = np.asarray([row['pReserveWin'] for row in records], dtype=np.float64)
    q_oof = np.full(len(records), np.nan)
    r_oof = np.full(len(records), np.nan)
    b0_oof = np.full((len(records), 3), np.nan)
    fold_results = []
    coefficients = []
    q_y = np.isin(labels, (WIN_CONSUMED, LOSS_CONSUMED)).astype(np.int64)
    consumed_ids = np.flatnonzero(q_y == 1)
    r_y = (labels[consumed_ids] == WIN_CONSUMED).astype(np.int64)
    for fold in range(folds):
        test = np.flatnonzero(fold_ids == fold)
        train = np.flatnonzero(fold_ids != fold)
        train_counts = np.bincount(labels[train], minlength=3).astype(np.float64)
        b0_probs = np.tile(train_counts / train_counts.sum(), (len(test), 1))
        b0_oof[test] = b0_probs
        q_model = logistic_fit(q_x[train], q_y[train])
        q_oof[test] = logistic_predict(q_model, q_x[test])
        train_consumed = train[q_y[train] == 1]
        if not len(train_consumed):
            raise ValueError(f'fold {fold} has no consumed-tail training rows')
        r_model = logistic_fit(r_x[train_consumed], (labels[train_consumed] == WIN_CONSUMED).astype(np.int64))
        r_oof[test] = logistic_predict(r_model, r_x[test])
        raw = q_model['coefficients'].tolist() + r_model['coefficients'].tolist()
        coefficients.append({'fold': fold, 'q': q_model['coefficients'].tolist(),
                             'r': r_model['coefficients'].tolist(),
                             'qConverged': q_model['converged'], 'rConverged': r_model['converged']})
        fold_class_probs = np.column_stack((1-q_oof[test], q_oof[test]*r_oof[test], q_oof[test]*(1-r_oof[test])))
        b0_fold_metrics = _prob_metrics(b0_probs, labels[test])
        correction_metrics = _prob_metrics(fold_class_probs, labels[test])
        fold_consumed_test = test[q_y[test] == 1]
        fold_results.append({
            'fold': fold, 'trainRows': len(train), 'testRows': len(test),
            'trainClassCounts': {name: int(train_counts[i]) for i, name in enumerate(CLASS_NAMES)},
            'b0ClassFrequency': b0_fold_metrics,
            'correction': correction_metrics,
            'q': _binary_metrics(q_oof[test], q_y[test]),
            'r': _binary_metrics(r_oof[fold_consumed_test],
                                 (labels[fold_consumed_test] == WIN_CONSUMED).astype(np.int64)),
        })
    correction_oof = np.column_stack((1-q_oof, q_oof*r_oof, q_oof*(1-r_oof)))
    mechanical_rows = [legal_class_probabilities(row['pOrdinaryWin'], row['pReserveWin']) for row in records]
    coherent = np.asarray([value is not None for value in mechanical_rows], dtype=bool)
    mechanical = np.full((len(records), 3), np.nan)
    for i, value in enumerate(mechanical_rows):
        if value is not None:
            mechanical[i] = value
    q_metrics = _binary_metrics(q_oof, q_y)
    r_metrics = _binary_metrics(r_oof[consumed_ids], (labels[consumed_ids] == WIN_CONSUMED).astype(np.int64))
    return {
        'sourceGroupedFolds': fold_ids.tolist(),
        'mechanicalReserve': {
            'coherentRows': int(coherent.sum()), 'incoherentRows': int((~coherent).sum()),
            'incoherentSources': [records[i]['sourceSeed'] for i in np.flatnonzero(~coherent)],
            'classMetricsOnCoherentRows': _prob_metrics(mechanical[coherent], labels[coherent]),
            'probabilitiesBySource': [
                {'sourceSeed': records[i]['sourceSeed'], 'rawClassProbabilities':
                 [records[i]['pOrdinaryWin'], records[i]['pReserveWin'] - records[i]['pOrdinaryWin'],
                  1-records[i]['pReserveWin']], 'coherent': bool(coherent[i])}
                for i in range(len(records))],
        },
        'b0TrainOnlyClassFrequency': _prob_metrics(b0_oof, labels),
        'correction': {
            'features': {'q': ['logit(pDeath)', 'pReserveWin - pOrdinaryWin'],
                         'r': ['pReserveWin']},
            'l2': L2, 'folds': folds, 'foldSeed': CV_SEED,
            'classMetrics': _prob_metrics(correction_oof, labels),
            'foldByFold': fold_results, 'foldCoefficients': coefficients,
            'coefficientRanges': {
                'q': [[float(min(row['q'][i] for row in coefficients)),
                       float(max(row['q'][i] for row in coefficients))] for i in range(3)],
                'r': [[float(min(row['r'][i] for row in coefficients)),
                       float(max(row['r'][i] for row in coefficients))] for i in range(2)],
            },
            'outOfFoldProbabilitiesBySource': [
                {'sourceSeed': records[i]['sourceSeed'], 'qConsumed': float(q_oof[i]),
                 'rWinGivenConsumed': float(r_oof[i]),
                 'classProbabilities': correction_oof[i].tolist()}
                for i in range(len(records))],
        },
        'correctionVersusMechanicalReservePairedSourceBootstrap': _paired_probability_comparison(
            mechanical[coherent], correction_oof[coherent], labels[coherent]),
        'qConsumption': q_metrics, 'rConditionalRescue': r_metrics,
        'labelsBySource': [{'sourceSeed': row['sourceSeed'], 'class': CLASS_NAMES[row['label']]}
                           for row in records],
    }


def _lizard_post_data(state):
    rid = composed.base._RELIC_IDS['LIZARD_TAIL']
    matches = [item['data'] for item in state['relics'] if int(item['id']) == rid]
    if len(matches) != 1:
        raise ValueError('sampled state must contain exactly one Lizard Tail')
    return int(matches[0])


def _set_lizard_data(state, value, *, template=None, index=None):
    rid = composed.base._RELIC_IDS['LIZARD_TAIL']
    new_state = copy.deepcopy(state)
    matches = [item for item in new_state['relics'] if int(item['id']) == rid]
    if len(matches) > 1 or value not in (0, 1):
        raise ValueError('invalid Lizard Tail state update')
    if matches:
        matches[0]['data'] = int(value)
    else:
        if template is None or int(template['id']) != rid:
            raise ValueError('missing Lizard Tail template for reinsertion')
        relic = {'id': rid, 'data': int(value)}
        at = len(new_state['relics']) if index is None else max(0, min(int(index), len(new_state['relics'])))
        new_state['relics'].insert(at, relic)
    word, bit = divmod(rid, 64)
    new_state['relicBits'][word] = int(new_state['relicBits'][word]) | (1 << bit)
    return new_state


def _sample_ordinary_victory(models, pre, predictor, rng, *, hp_input_treatment='T0_ordinary'):
    """Reuse the frozen ordinary conditional heads after legal support checks."""
    transformed_pre = copy.deepcopy(pre)
    transformed_input = copy.deepcopy(predictor)
    transformed_hp = hp_treatment(int(pre['curHp']), int(pre['maxHp']), hp_input_treatment)
    transformed_pre['curHp'] = transformed_hp
    transformed_input['globals']['curHp'] = transformed_hp
    reasons = composed.full_support_reasons(transformed_pre, transformed_input, models)
    if reasons:
        return None, reasons
    with models.torch.inference_mode():
        inputs = models.encode_visible(transformed_input)
        delta_idx = composed.categorical(models.max_hp(inputs), rng)
        maximum = int(pre['maxHp']) + int(models.delta_values[delta_idx])
        z = models.hp_encoding(inputs)
        signed_class = composed.categorical(models.hp_distribution(z, delta_idx, transformed_hp, maximum), rng)
        ending_hp = transformed_hp + int(models.classes[signed_class])
        if not 1 <= ending_hp <= maximum:
            raise ValueError('sampled HP violates the model legal support')
        fraction = ending_hp / maximum
        mask = composed.categorical(models.potion_distribution(inputs, transformed_pre, delta_idx, fraction), rng)
        residues = {group: composed.categorical(prob, rng)
                    for group, prob in models.relic_distribution(z, signed_class, fraction, mask).items()}
        post = composed.assemble_victory(transformed_pre, transformed_input, maximum, ending_hp,
                                         mask, residues, models.encounter_names)
    # Keep native persistent state from the real starting state. Model-input HP is
    # a conditional-head treatment, not a change to other precombat variables.
    post['curHp'] = int(ending_hp)
    return post, []


def ancestral_diagnostic(pairs, models, class_probabilities, *, draws=32, seed=20260927,
                         consumed_hp_treatment='T0_ordinary'):
    """Diagnostic sampler; unsupported/native-boundary rows fail closed."""
    if len(class_probabilities) != len(pairs):
        raise ValueError('out-of-fold class probabilities do not align with pairs')
    import torch
    rng = np.random.default_rng(seed)
    counts = Counter()
    class_counts = Counter()
    support_reasons = Counter()
    sample_digest = hashlib.sha256()
    sampled_sources = 0
    lizard = composed.base._RELIC_IDS['LIZARD_TAIL']
    fairy = composed.base._POTION_IDS['FAIRY_POTION']
    bloom = composed.base._RELIC_IDS['MARK_OF_THE_BLOOM']
    for index, pair in enumerate(pairs):
        raw_pre = pair['activeTail']['transition']['pre']
        raw_input = pair['activeTail']['predictorInput']
        # The trained ordinary model cannot see active Tail. Strip it for CTM
        # conditional heads, then restore the sampled terminal Tail state below.
        pre = pilot._strip_lizard(raw_pre)
        predictor = pilot._strip_lizard_input(raw_input)
        reasons = composed.full_support_reasons(pre, predictor, models)
        if any(int(item['id']) == bloom for item in raw_pre['relics']):
            reasons = list(reasons) + ['mark_of_bloom_exact_boundary']
        if fairy in raw_pre['potions']:
            reasons = list(reasons) + ['fairy_potion_precedence_exact_boundary']
        if reasons:
            for reason in reasons:
                support_reasons[reason] += 1
            counts['fallbackRows'] += 1
            continue
        sampled_sources += 1
        for _ in range(draws):
            class_id = composed.categorical(class_probabilities[index], rng)
            class_counts[CLASS_NAMES[class_id]] += 1
            expected_data = 1 if class_id == WIN_RETAINED else 0
            if class_id == LOSS_CONSUMED:
                counts['terminalLossConsumed'] += 1
                # Death ends before conditional postcombat heads are sampled.
                # Validate a terminal snapshot with Tail spent and HP at zero.
                terminal = copy.deepcopy(raw_pre)
                terminal['curHp'] = 0
                terminal = _set_lizard_data(terminal, 0)
                validate_state(terminal, 'sampled.activeTail.lossConsumed')
                if _lizard_post_data(terminal) != 0 or terminal['relicBits'] != raw_pre['relicBits']:
                    counts['tailStateMismatch'] += 1
                else:
                    counts['terminalLossStateLegal'] += 1
                counts['legalPotionCount'] += int(
                    terminal['potionCount'] == sum(value > 1 for value in terminal['potions']))
                counts['legalPersistentState'] += int(terminal['relicBits'] == raw_pre['relicBits'])
                sample_digest.update(f'{pair["pair"]["sourceSeed"]}:LOSS_CONSUMED;'.encode())
                counts['tailStateChecks'] += 1
                if expected_data != 0:
                    counts['tailStateMismatch'] += 1
                else:
                    counts['tailStateMatches'] += 1
                continue
            use_treatment = 'T0_ordinary' if class_id == WIN_RETAINED else consumed_hp_treatment
            post, head_reasons = _sample_ordinary_victory(models, pre, predictor, rng,
                                                          hp_input_treatment=use_treatment)
            if head_reasons:
                counts['conditionalHeadFallback'] += 1
                for reason in head_reasons:
                    support_reasons['conditional:' + reason] += 1
                continue
            lizard_template = next(item for item in raw_pre['relics'] if int(item['id']) == lizard)
            lizard_index = next(i for i, item in enumerate(raw_pre['relics']) if int(item['id']) == lizard)
            post = _set_lizard_data(post, expected_data, template=lizard_template, index=lizard_index)
            # Composed post-state uses OOC continuation RNG fields in place of
            # the raw six-stream state schema. assemble_victory has already run
            # its native legality and RNG validators; assert the added relic and
            # persistent-state invariants directly here.
            if post['relicBits'] != raw_pre['relicBits']:
                raise ValueError('sampled Tail state changed persistent relic membership bits')
            counts['terminalWinRetained' if class_id == WIN_RETAINED else 'terminalWinConsumed'] += 1
            counts['legalHp'] += int(1 <= post['curHp'] <= post['maxHp'])
            counts['legalPotionCount'] += int(post['potionCount'] == sum(value > 1 for value in post['potions']))
            counts['legalPersistentState'] += int(post['relicBits'] == raw_pre['relicBits'])
            counts['tailStateChecks'] += 1
            if _lizard_post_data(post) == expected_data:
                counts['tailStateMatches'] += 1
            else:
                counts['tailStateMismatch'] += 1
            sample_digest.update((json.dumps({
                'source': pair['pair']['sourceSeed'], 'class': CLASS_NAMES[class_id],
                'post': post,
            }, sort_keys=True, separators=(',', ':')) + '\n').encode())
    return {
        'drawsPerSupportedSource': draws, 'requestedRows': len(pairs),
        'supportedSources': sampled_sources, 'fallbackRows': int(counts['fallbackRows']),
        'conditionalHeadFallbackDraws': int(counts['conditionalHeadFallback']),
        'classDraws': int(sum(class_counts.values())), 'classDrawCounts': dict(class_counts),
        'terminalCounts': {key: int(value) for key, value in counts.items()},
        'supportAndFallbackReasons': dict(sorted(support_reasons.items())),
        'impossibleLossRetainedDraws': 0,
        'spentToActiveTransitions': 0,
        'tailDataTransitionMismatches': int(counts['tailStateMismatch']),
        'tailStateChecks': int(counts['tailStateChecks']),
        'tailStateMatches': int(counts['tailStateMatches']),
        'sampleDigestSha256': sample_digest.hexdigest(), 'seed': seed,
        'conditionalHeadsUse': consumed_hp_treatment,
        'productionIntegration': False,
    }


def analyze(manifest_path: Path, output_path: Path, *, draws=32):
    manifest, pairs = pilot.validate_pair_corpus(manifest_path)
    import torch
    torch.set_num_threads(4)
    models = composed.FrozenModels('cuda' if torch.cuda.is_available() else 'cpu')
    hp_scores = {treatment: score_hp_treatment(pairs, models, treatment) for treatment in HP_TREATMENTS}
    hp_bootstrap = {
        treatment: _paired_bootstrap_delta(hp_scores['T0_ordinary'], hp_scores[treatment])
        for treatment in HP_TREATMENTS[1:]}
    treatment_assessment = {}
    for treatment in HP_TREATMENTS[1:]:
        deltas = hp_bootstrap[treatment]
        hp_nll, hp_crps, mae = (deltas[name] for name in
                                ('hpNll', 'hpCrps', 'expectedHpAbsError'))
        domain_issues = hp_scores[treatment]['unscoreableBecauseTransformedTargetOutsideModelDomain']
        maxhp_or_potion_clear_degradation = any(
            deltas[name]['sourceBootstrap95CI'] is not None
            and deltas[name]['sourceBootstrap95CI'][0] > 0
            for name in ('maxHpNll', 'potionMaskNll'))
        relic_clear_degradation = any(
            result['sourceBootstrap95CI'] is not None
            and result['sourceBootstrap95CI'][0] > 0
            for result in deltas['supportedRelicGroupConstraintNllByGroup'].values())
        treatment_assessment[treatment] = {
            'hpNllImprovedWithBootstrapUpperBelowZero': bool(
                hp_nll['sourceBootstrap95CI'] is not None and hp_nll['sourceBootstrap95CI'][1] < 0),
            'hpCrpsPointImproved': bool(hp_crps['meanTreatmentMinusT0'] is not None
                                         and hp_crps['meanTreatmentMinusT0'] < 0),
            'expectedHpMaeMateriallyWorse': bool(mae['meanTreatmentMinusT0'] is not None
                                                 and mae['meanTreatmentMinusT0'] > 0),
            'clearMaxHpOrPotionDegradation': maxhp_or_potion_clear_degradation,
            'clearSupportedRelicGroupDegradation': relic_clear_degradation,
            'transformedTargetDomainIssues': int(domain_issues),
        }
    eligible_pairs = [pair for pair in pairs if not native_boundary_reasons(pair)]
    boundary_pairs = [pair for pair in pairs if native_boundary_reasons(pair)]
    records = _derive_features(eligible_pairs, models)
    outcome_model = _factorized_cv(records)
    oof_by_source = {row['sourceSeed']: row['classProbabilities']
                     for row in outcome_model['correction']['outOfFoldProbabilitiesBySource']}
    probs = [oof_by_source.get(int(pair['pair']['sourceSeed']), [1.0, 0.0, 0.0]) for pair in pairs]
    # Keep T0 unless another fixed candidate satisfies the complete preregistered
    # directional screen; uncertainty still prevents qualification.
    treatment_choice = 'T0_ordinary'
    for treatment in HP_TREATMENTS[1:]:
        assessment = treatment_assessment[treatment]
        if (assessment['hpNllImprovedWithBootstrapUpperBelowZero']
                and assessment['hpCrpsPointImproved']
                and not assessment['expectedHpMaeMateriallyWorse']
                and not assessment['clearMaxHpOrPotionDegradation']
                and not assessment['clearSupportedRelicGroupDegradation']
                and assessment['transformedTargetDomainIssues'] == 0):
            treatment_choice = treatment
            break
    ancestral = ancestral_diagnostic(pairs, models, probs, draws=draws,
                                     consumed_hp_treatment=treatment_choice)
    summary = {
        'schema': 'active_lizard_minimal_correction_diagnostic_v1',
        'baselineHeadSha': manifest['baselineGitSha'],
        'analysisImplementationSha': __import__('subprocess').check_output(
            ['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'cohort': {
            'pairs': len(pairs), 'sourceSeeds': [int(row['pair']['sourceSeed']) for row in pairs],
            'pairedJsonlSha256': manifest['jsonl']['sha256'],
            'pairedManifestSha256': pilot.sha256(manifest_path),
            'targetSelectionSha256': manifest['targetSelection']['sha256'],
            'frozenModelHashes': models.hashes, 'teacherId': manifest['combatTeacher']['teacher_id'],
        },
        'phaseA': {
            'question': 'fixed conditional HP-input transforms on Tail-consumed wins; teacher-forced descriptive only',
            'candidateRows': 27, 'treatments': hp_scores, 'pairedSourceBootstrapVersusT0': hp_bootstrap,
            'treatmentAssessment': treatment_assessment,
            'selectedTreatment': treatment_choice,
            'classification': 'NO_SIMPLE_HP_TRANSFORM' if treatment_choice == 'T0_ordinary' else 'development_candidate_only',
        },
        'phaseB': {
            'classNames': list(CLASS_NAMES),
            'observedClassCountsAllPairs': dict(Counter(CLASS_NAMES[_get_three_class_label(pair)] for pair in pairs)),
            'modeledRows': len(eligible_pairs),
            'modeledClassCounts': dict(Counter(CLASS_NAMES[row['label']] for row in records)),
            'nativeExactBoundaryRows': len(boundary_pairs),
            'nativeExactBoundaryReasons': dict(Counter(
                reason for pair in boundary_pairs for reason in native_boundary_reasons(pair))),
            'nativeExactBoundarySources': [int(pair['pair']['sourceSeed']) for pair in boundary_pairs],
            'featureConstruction': 'only frozen ordinary pDeath, reserve-proxy pWin, and their fixed difference; outcomes are labels only',
            'crossValidation': outcome_model,
            'interpretation': 'five LOSS_CONSUMED rows are too few to qualify rescue prediction',
            'additionalLossConsumedExamplesRecommendedBeforeReassessment': 20,
            'totalLossConsumedTargetForNextModelReview': 25,
            'sampleSizeRationale': 'reach about five observed losses per 5-fold holdout set; this is a minimum reassessment target, not a qualification guarantee',
        },
        'phaseC': {
            'offlineAncestralDiagnostic': ancestral,
            'samplerBoundary': 'ordinary conditional heads only after WIN; Tail class controls active/spent state; losses terminate; Mark/Fairy exact boundaries fall back',
        },
        'finalClassification': 'LIZARD_MINIMAL_CORRECTION_DATA_LIMITED',
        'claimBoundary': 'descriptive development diagnostic only; no training artifact, runtime integration, or production qualification',
    }
    output_path.write_text(json.dumps(summary, indent=2) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--draws', type=int, default=32)
    args = parser.parse_args()
    if args.draws < 1:
        parser.error('--draws must be positive')
    print(json.dumps(analyze(args.manifest, args.output, draws=args.draws), indent=2))


if __name__ == '__main__':
    main()
