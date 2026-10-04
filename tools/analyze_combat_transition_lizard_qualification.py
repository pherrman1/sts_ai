#!/usr/bin/env python3
"""Score the frozen active-Lizard q/r candidate on a paired cohort.

This is a read-only qualification analysis: it never fits or tunes q/r, and it
does not change runtime support. B1 class masses are kept raw for reporting;
only sub-1e-6 negative differences attributable to float32 probability
rounding are projected to zero for probability scoring.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from tools import combat_transition_composed as composed
from tools import combat_transition_composed_evaluate as evaluate
from tools import combat_transition_lizard_minimal as minimal
from tools import combat_transition_lizard_pair_pilot as pilot
from tools import combat_transition_lizard_qr_artifact as qr

SCHEMA = 'active_lizard_minimal_ctm_fresh_qualification_v1'
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 20260929
B1_FLOAT32_EPSILON = 1e-6


def _source_bootstrap_ci(values, source_ids, *, reps=BOOTSTRAP_REPS, seed=BOOTSTRAP_SEED):
    values = np.asarray(values, dtype=np.float64)
    sources = np.asarray(source_ids, dtype=np.int64)
    if values.shape != sources.shape or not len(values):
        return None
    groups = defaultdict(list)
    for source, value in zip(sources, values):
        groups[int(source)].append(float(value))
    unique = np.asarray(sorted(groups), dtype=np.int64)
    rng = np.random.default_rng(seed)
    boot = np.empty(reps, dtype=np.float64)
    for index in range(reps):
        sampled = rng.choice(unique, size=len(unique), replace=True)
        retained = [value for source in sampled for value in groups[int(source)]]
        boot[index] = float(np.mean(retained))
    return [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))]


def _multiclass_arrays(probabilities, labels):
    p = np.asarray(probabilities, dtype=np.float64)
    y = np.asarray(labels, dtype=np.int64)
    if p.shape != (len(y), 3) or not len(y):
        return None
    if (not np.isfinite(p).all() or np.any(p < 0)
            or not np.allclose(p.sum(axis=1), 1.0, atol=1e-8)):
        raise ValueError('invalid three-class probabilities in qualification analysis')
    nll = -np.log(np.maximum(p[np.arange(len(y)), y], 1e-300))
    onehot = np.eye(3, dtype=np.float64)[y]
    brier = np.sum((p - onehot) ** 2, axis=1)
    return nll, brier


def _probability_comparison(base, candidate, labels, sources, *, seed):
    base_arrays = _multiclass_arrays(base, labels)
    candidate_arrays = _multiclass_arrays(candidate, labels)
    if base_arrays is None or candidate_arrays is None:
        return {'rows': 0, 'threeClassNll': None, 'multiclassBrier': None}
    base_nll, base_brier = base_arrays
    cand_nll, cand_brier = candidate_arrays
    source_ids = np.asarray(sources, dtype=np.int64)
    output = {
        'rows': len(source_ids),
        'baseline': minimal._prob_metrics(base, labels),
        'candidate': minimal._prob_metrics(candidate, labels),
    }
    for name, delta in (('threeClassNll', cand_nll - base_nll),
                        ('multiclassBrier', cand_brier - base_brier)):
        output[name] = {
            'meanCandidateMinusB1': float(delta.mean()),
            'sourceBootstrap95CI': _source_bootstrap_ci(
                delta, source_ids, seed=seed + (0 if name == 'threeClassNll' else 1)),
        }
    return output


def _binary_arrays(probabilities, labels):
    p = np.asarray(probabilities, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    if p.shape != y.shape or not len(y):
        return None
    p = np.clip(p, 1e-15, 1 - 1e-15)
    nll = -(y * np.log(p) + (1 - y) * np.log(1 - p))
    brier = (p - y) ** 2
    return nll, brier


def _binary_comparison(base, candidate, labels, sources, *, seed):
    base_arrays = _binary_arrays(base, labels)
    candidate_arrays = _binary_arrays(candidate, labels)
    if base_arrays is None or candidate_arrays is None:
        return {'rows': 0, 'nll': None, 'brier': None}
    base_nll, base_brier = base_arrays
    cand_nll, cand_brier = candidate_arrays
    source_ids = np.asarray(sources, dtype=np.int64)
    output = {
        'rows': len(source_ids),
        'baseline': minimal._binary_metrics(base, labels),
        'candidate': minimal._binary_metrics(candidate, labels),
    }
    for name, delta in (('nll', cand_nll - base_nll), ('brier', cand_brier - base_brier)):
        output[name] = {
            'meanCandidateMinusB1': float(delta.mean()),
            'sourceBootstrap95CI': _source_bootstrap_ci(
                delta, source_ids, seed=seed + (0 if name == 'nll' else 1)),
        }
    return output


def _calibration(probabilities, labels, bins=10):
    p = np.asarray(probabilities, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    if not len(y):
        return {'rows': 0, 'bins': [], 'expectedCalibrationError': None}
    ids = np.minimum((np.clip(p, 0, 1) * bins).astype(int), bins - 1)
    summaries = []
    weighted_error = 0.0
    for index in range(bins):
        mask = ids == index
        if not mask.any():
            continue
        predicted, observed = float(p[mask].mean()), float(y[mask].mean())
        count = int(mask.sum())
        weighted_error += count / len(y) * abs(predicted - observed)
        summaries.append({'lower': index / bins, 'upper': (index + 1) / bins,
                          'rows': count, 'meanPredicted': predicted,
                          'observedRate': observed})
    return {
        'rows': len(y), 'meanPredicted': float(p.mean()),
        'observedRate': float(y.mean()),
        'calibrationInTheLargePredictedMinusObserved': float(p.mean() - y.mean()),
        'expectedCalibrationErrorEqualWidth': float(weighted_error), 'bins': summaries,
    }


def _row_b1_probabilities(p_ordinary, p_reserve):
    difference = float(p_reserve) - float(p_ordinary)
    raw = [float(p_ordinary), difference, 1.0 - float(p_reserve)]
    if difference < -B1_FLOAT32_EPSILON:
        return raw, None, 'material_incoherence'
    if difference < 0.0:
        # Keep raw values above for audit; this only removes float32-scale noise
        # from the scoring vector and preserves a normalized probability mass.
        projected = [float(p_ordinary), 0.0, 1.0 - float(p_ordinary)]
        return raw, projected, 'within_float32_epsilon'
    return raw, [float(p_ordinary), difference, 1.0 - float(p_reserve)], 'coherent'


def _support_audit(pairs, models):
    reasons = Counter()
    eligible_rows = 0
    for pair in pairs:
        row_failed = False
        pre = pilot._strip_lizard(pair['activeTail']['transition']['pre'])
        predictor = pilot._strip_lizard_input(pair['activeTail']['predictorInput'])
        if pre != pair['noTail']['transition']['pre']:
            reasons['stripped_active_pre_differs_from_no_tail_pre'] += 1
            row_failed = True
        if predictor != pair['noTail']['predictorInput']:
            reasons['stripped_active_predictor_differs_from_no_tail_predictor'] += 1
            row_failed = True
        support_reasons = composed.full_support_reasons(pre, predictor, models)
        if support_reasons:
            reasons['unsupported:' + ','.join(support_reasons)] += 1
            row_failed = True
        boundary_reasons = minimal.native_boundary_reasons(pair)
        if boundary_reasons:
            reasons.update(boundary_reasons)
            row_failed = True
        if not row_failed:
            eligible_rows += 1
    return {'rows': len(pairs), 'failureCounts': dict(sorted(reasons.items())),
            'exactSupportRows': eligible_rows,
            'supportAndBoundaryFailureRows': len(pairs) - eligible_rows}


def _score_conditional_arm(pairs, models, *, arm):
    """Score T0 heads on recorded win outcomes from one arm."""
    scores = defaultdict(list)
    per_source = {}
    failures = Counter()
    torch = models.torch
    for pair in pairs:
        row = pair[arm]
        if int(row['transition']['combatOutcome']) != pilot.WIN:
            continue
        source = int(pair['pair']['sourceSeed'])
        actual_pre = pair['noTail']['transition']['pre']
        pre, predictor, start_hp = minimal._conditioned_pre(pair, 'T0_ordinary')
        post = (pilot._strip_lizard(row['transition']['post']) if arm == 'activeTail'
                else row['transition']['post'])
        try:
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
            target_index = ending - start_hp - int(models.classes[0])
            if not 0 <= target_index < len(models.classes):
                failures['observed_HP_outside_frozen_domain'] += 1
                continue
            if not 1 <= ending <= int(post['maxHp']):
                failures['observed_HP_outside_legal_domain'] += 1
                continue
            with torch.inference_mode():
                p_delta = evaluate.probabilities(models.max_net.max_hp_delta(
                    models.fp32_encoding(models.max_net.encoder, inputs)))[0]
                z = models.hp_encoding(inputs).cpu().numpy()
                p_hp = evaluate.hp_prob(models, z, np.asarray([delta_index]),
                                        np.asarray([start_hp]), np.asarray([int(post['maxHp'])]))[0]
                expected_hp = start_hp + float(np.dot(p_hp, models.classes))
                potion_z = models.fp32_encoding(models.potion_encoder.encoder, inputs).cpu().numpy()
                capacity = int(pre['potionCapacity'])
                potion_mask = int(composed.potion.encode_masks(
                    np.asarray([pre['potions']]), np.asarray([post['potions']]),
                    np.asarray([capacity]))[0])
                slots = arrays['potions'][:, :, 1].astype(np.int64)[0]
                ending_fraction = np.asarray([ending / int(post['maxHp'])], dtype=np.float32)
                p_potion = evaluate.potion_prob(models, potion_z, slots[None],
                    np.asarray([capacity]), np.asarray([delta_index]), ending_fraction)[0]
                p_relic = evaluate.relic_prob(models, z, np.asarray([target_index]),
                    ending_fraction, np.asarray([potion_mask], dtype=np.int64))
            hp_nll = -math.log(max(float(p_hp[target_index]), 1e-300))
            hp_crps = minimal._crps(p_hp, target_index)
            mae = abs(expected_hp - ending)
            max_nll = -math.log(max(float(p_delta[delta_index]), 1e-300))
            potion_nll = -math.log(max(float(p_potion[potion_mask]), 1e-300))
            allowed = composed.relic.trajectory_constraints(
                pre['relics'], post['relics'], predictor['globals']['encounter'], False)
            relic_row = {}
            for group in models.trained_groups:
                if group not in allowed or group not in p_relic:
                    continue
                mass = float(np.asarray(p_relic[group])[0, list(allowed[group])].sum())
                relic_row[group] = -math.log(max(mass, 1e-300))
                scores['relic:' + group].append(relic_row[group])
            row_scores = {'hpNll': hp_nll, 'hpCrps': hp_crps,
                          'expectedHpAbsError': mae, 'maxHpNll': max_nll,
                          'potionMaskNll': potion_nll,
                          'relicConstraintNllByGroup': relic_row}
            for name, value in row_scores.items():
                if name != 'relicConstraintNllByGroup':
                    scores[name].append(value)
            per_source[source] = row_scores
        except (KeyError, ValueError, IndexError, RuntimeError) as error:
            failures[f'{type(error).__name__}:{error}'] += 1
    return {'candidateWinRows': sum(int(pair[arm]['transition']['combatOutcome']) == pilot.WIN
                                    for pair in pairs),
            'scoredRowsByMetric': {name: len(values) for name, values in scores.items()},
            'meanMetrics': {name: float(np.mean(values)) if values else None
                            for name, values in scores.items()},
            'perSourceScores': per_source,
            'unscoredReasons': dict(sorted(failures.items()))}


def _cohort_indices(rows, name):
    if name == 'POOLED':
        return list(range(len(rows)))
    return [index for index, row in enumerate(rows) if row['cohort'] == name]


def analyze(manifest_path: Path, artifact_path: Path, artifact_sha256: str,
            output_path: Path) -> dict:
    manifest, pairs = pilot.validate_pair_corpus(manifest_path)
    artifact, actual_artifact_sha = qr.load_artifact(artifact_path, artifact_sha256)
    import torch
    torch.set_num_threads(4)
    models = composed.FrozenModels('cuda' if torch.cuda.is_available() else 'cpu')
    if models.hashes != artifact['frozenCtmComponentHashes']:
        raise ValueError('fresh qualification CTM hashes differ from frozen q/r artifact')
    selection_path = pilot._resolve_manifest_file(
        manifest['targetSelection']['path'], manifest_path.parent)
    selection = json.loads(selection_path.read_text())
    target_by_source = {int(row['sourceSeed']): row for row in selection['targets']}
    if len(target_by_source) != len(pairs):
        raise ValueError('target selection and paired cohort source counts differ')
    source_assignment_path = Path(selection['sourceAssignmentPath'])
    if not source_assignment_path.is_absolute():
        source_assignment_path = Path.cwd() / source_assignment_path
    source_assignment_bytes = source_assignment_path.read_bytes()
    source_assignment_sha = hashlib.sha256(source_assignment_bytes).hexdigest()
    if source_assignment_sha != selection['sourceAssignmentSha256']:
        raise ValueError('predeclared source assignment hash mismatch')
    evidence_dir = manifest_path.parent
    candidate_jsonl = evidence_dir / 'fresh_candidate_states.jsonl'
    candidate_manifest = evidence_dir / 'fresh_candidate_states.jsonl.manifest.json'
    if hashlib.sha256(candidate_jsonl.read_bytes()).hexdigest() != selection['candidateJsonlSha256']:
        raise ValueError('fresh candidate-state JSONL hash mismatch')
    if hashlib.sha256(candidate_manifest.read_bytes()).hexdigest() != selection['candidateManifestSha256']:
        raise ValueError('fresh candidate-state manifest hash mismatch')
    source_assignment = json.loads(source_assignment_bytes)
    assignment_by_source = {
        int(source): 'HARD96' for source in source_assignment['hard96SourceIds']}
    assignment_by_source.update({
        int(source): 'BROAD32' for source in source_assignment['broad32SourceIds']})
    if set(target_by_source) != set(assignment_by_source):
        raise ValueError('selected targets do not exactly match predeclared source assignment')
    cohort_counts = Counter(row['qualificationCohort'] for row in selection['targets'])
    if cohort_counts != Counter({'HARD96': 96, 'BROAD32': 32}):
        raise ValueError('selected cohort sizes differ from predeclared 96/32 split')
    for source, target in target_by_source.items():
        if target['qualificationCohort'] != assignment_by_source[source]:
            raise ValueError(f'cohort assignment mismatch for source {source}')
    for pair in pairs:
        source = int(pair['pair']['sourceSeed'])
        target = target_by_source.get(source)
        if (target is None or int(target['fightIdx']) != int(pair['pair']['fightIdx'])):
            raise ValueError(f'paired target identity mismatch for source {source}')

    support = _support_audit(pairs, models)
    records = minimal._precombat_risk_features(pairs, models)
    rows = []
    labels = []
    q_values, r_values = [], []
    b1_kinds = Counter()
    b1_negative = []
    b1_material_sources = []
    for pair, record in zip(pairs, records):
        source = int(pair['pair']['sourceSeed'])
        target = target_by_source[source]
        label = minimal._get_three_class_label(pair)
        q_pred, r_pred, class_pred = qr.predict_qr(
            float(record['pOrdinaryWin']), float(record['pReserveWin']), artifact)
        raw, scoring, kind = _row_b1_probabilities(
            record['pOrdinaryWin'], record['pReserveWin'])
        b1_kinds[kind] += 1
        if raw[1] < 0:
            b1_negative.append({'sourceSeed': source, 'fightIdx': int(pair['pair']['fightIdx']),
                                'cohort': target['qualificationCohort'],
                                'rawReserveMinusOrdinary': raw[1], 'kind': kind})
        if kind == 'material_incoherence':
            b1_material_sources.append(source)
        rows.append({
            'sourceSeed': source, 'fightIdx': int(pair['pair']['fightIdx']),
            'cohort': target['qualificationCohort'], 'label': int(label),
            'pOrdinaryWin': float(record['pOrdinaryWin']),
            'pReserveWin': float(record['pReserveWin']),
            'qB1': 1.0 - float(record['pOrdinaryWin']),
            'qFrozen': q_pred, 'rFrozen': r_pred,
            'rB1Raw': ((float(record['pReserveWin']) - float(record['pOrdinaryWin'])) /
                       max(1e-12, 1.0 - float(record['pOrdinaryWin']))),
            'classProbabilitiesFrozenQr': class_pred,
            'classProbabilitiesB1Raw': raw,
            'classProbabilitiesB1Scoring': scoring,
            'b1CoherenceKind': kind,
        })
        labels.append(label)
        q_values.append(q_pred)
        r_values.append(r_pred)
    labels = np.asarray(labels, dtype=np.int64)
    q_values = np.asarray(q_values, dtype=np.float64)
    r_values = np.asarray(r_values, dtype=np.float64)
    sources = np.asarray([row['sourceSeed'] for row in rows], dtype=np.int64)
    pair_arm_outcomes = {}
    for arm in ('noTail', 'activeTail'):
        counts = Counter(
            'WIN' if int(pair[arm]['transition']['combatOutcome']) == pilot.WIN else 'LOSS'
            for pair in pairs)
        pair_arm_outcomes[arm] = dict(counts)
    frozen_class = np.asarray([row['classProbabilitiesFrozenQr'] for row in rows], dtype=np.float64)
    b1_scoreable = np.asarray([row['classProbabilitiesB1Scoring'] is not None for row in rows])
    b1_class = np.asarray([row['classProbabilitiesB1Scoring'] or [0, 0, 0] for row in rows], dtype=np.float64)
    q_labels = np.isin(labels, (minimal.WIN_CONSUMED, minimal.LOSS_CONSUMED)).astype(np.int64)
    r_mask = q_labels == 1
    r_labels = (labels[r_mask] == minimal.WIN_CONSUMED).astype(np.int64)
    r_base, r_invalid = [], []
    for index in np.flatnonzero(r_mask):
        record = records[index]
        po, pr = float(record['pOrdinaryWin']), float(record['pReserveWin'])
        numerator, denominator = pr - po, 1.0 - po
        if denominator <= 1e-12 or numerator < -B1_FLOAT32_EPSILON:
            r_invalid.append(int(sources[index]))
            r_base.append(np.nan)
        else:
            r_base.append(min(1.0, max(0.0, numerator) / denominator))
    r_base = np.asarray(r_base, dtype=np.float64)
    r_valid = np.isfinite(r_base)

    cohort_results = {}
    for cohort_name in ('HARD96', 'BROAD32', 'POOLED'):
        indices = _cohort_indices(rows, cohort_name)
        idx = np.asarray(indices, dtype=np.int64)
        cohort_labels = labels[idx]
        cohort_sources = sources[idx]
        q_y = q_labels[idx]
        q_cmp = _binary_comparison(
            np.asarray([rows[i]['qB1'] for i in idx]), q_values[idx], q_y,
            cohort_sources, seed=BOOTSTRAP_SEED + 10 + len(cohort_name))
        r_local_mask = r_mask[idx]
        r_global_indices = idx[r_local_mask]
        # Index r-aligned arrays by mapping each original row to its consumed-row offset.
        consumed_offset = {int(row_index): offset for offset, row_index in enumerate(np.flatnonzero(r_mask))}
        r_offsets = np.asarray([consumed_offset[int(row_index)] for row_index in r_global_indices], dtype=np.int64)
        r_valid_local = r_valid[r_offsets]
        r_compare = _binary_comparison(
            r_base[r_offsets][r_valid_local], r_values[r_global_indices][r_valid_local],
            (labels[r_global_indices][r_valid_local] == minimal.WIN_CONSUMED).astype(np.int64),
            sources[r_global_indices][r_valid_local],
            seed=BOOTSTRAP_SEED + 20 + len(cohort_name)) if r_valid_local.any() else {
                'rows': 0, 'nll': None, 'brier': None}
        class_mask = b1_scoreable[idx]
        class_global = idx[class_mask]
        primary = _probability_comparison(
            b1_class[class_global], frozen_class[class_global], labels[class_global],
            sources[class_global], seed=BOOTSTRAP_SEED + 30 + len(cohort_name))
        observed_counts = Counter(minimal.CLASS_NAMES[int(labels[i])] for i in idx)
        loss_ids = {int(rows[i]['sourceSeed']) for i in idx
                    if labels[i] == minimal.LOSS_CONSUMED}
        consumed_count = int(np.sum(q_y))
        q_baseline = [rows[i]['qB1'] for i in idx]
        cohort_results[cohort_name] = {
            'rows': len(idx), 'classCounts': {name: observed_counts[name] for name in minimal.CLASS_NAMES},
            'consumedRows': consumed_count, 'lossConsumedDistinctSources': len(loss_ids),
            'threeClassQrVsB1': primary,
            'primaryGate': {
                'allRowsB1Scoreable': bool(class_mask.all()),
                'nllCiStrictlyBelowZero': bool(
                    primary.get('threeClassNll', {}).get('sourceBootstrap95CI') is not None
                    and primary['threeClassNll']['sourceBootstrap95CI'][1] < 0),
                'brierMeanNotWorse': bool(
                    primary.get('multiclassBrier', {}).get('meanCandidateMinusB1') is not None
                    and primary['multiclassBrier']['meanCandidateMinusB1'] <= 0),
                'brierIntervalShowsNoClearDegradation': bool(
                    primary.get('multiclassBrier', {}).get('sourceBootstrap95CI') is not None
                    and primary['multiclassBrier']['sourceBootstrap95CI'][0] <= 0),
            },
            'qConsumption': {
                'comparison': q_cmp,
                'frozenCalibration': _calibration(q_values[idx], q_y),
                'b1Calibration': _calibration(q_baseline, q_y),
                'gateNllNotWorse': bool(q_cmp.get('nll', {}).get('meanCandidateMinusB1') is not None
                                        and q_cmp['nll']['meanCandidateMinusB1'] <= 0),
                'gateBrierNotWorse': bool(q_cmp.get('brier', {}).get('meanCandidateMinusB1') is not None
                                          and q_cmp['brier']['meanCandidateMinusB1'] <= 0),
            },
            'rConditionalRescue': {
                'consumedRows': int(r_local_mask.sum()),
                'b1ScoreableConsumedRows': int(r_valid_local.sum()),
                'comparisonOnB1ScoreableConsumedRows': r_compare,
                'b1UndefinedOrMateriallyIncoherentRows': [
                    int(sources[row_index]) for row_index in r_global_indices
                    if not r_valid[consumed_offset[int(row_index)]]],
                'frozenCalibration': _calibration(r_values[r_global_indices],
                    (labels[r_global_indices] == minimal.WIN_CONSUMED).astype(np.int64)),
                'b1Calibration': _calibration(r_base[r_offsets][r_valid_local],
                    (labels[r_global_indices][r_valid_local] == minimal.WIN_CONSUMED).astype(np.int64))
                    if r_valid_local.any() else None,
                'gateNllCiStrictlyBelowZero': bool(
                    r_compare.get('nll', {}).get('sourceBootstrap95CI') is not None
                    and r_compare['nll']['sourceBootstrap95CI'][1] < 0),
                'gateBrierNotWorse': bool(
                    r_compare.get('brier', {}).get('meanCandidateMinusB1') is not None
                    and r_compare['brier']['meanCandidateMinusB1'] <= 0),
                'gateAllConsumedRowsB1Scoreable': bool(r_valid_local.all()),
            },
        }

    # T2 confirmation on fresh consumed wins, and a retained-win versus paired
    # no-Tail both-win T0 head comparison. These use frozen ordinary CTM heads.
    hp_by_cohort = {}
    retained_by_cohort = {}
    for cohort_name in ('HARD96', 'BROAD32', 'POOLED'):
        cohort_pairs = [pairs[i] for i in _cohort_indices(rows, cohort_name)]
        t0 = minimal.score_hp_treatment(cohort_pairs, models, 'T0_ordinary')
        t2 = minimal.score_hp_treatment(cohort_pairs, models, 'T2_revive')
        hp_delta = minimal._paired_bootstrap_delta(t0, t2)
        common = sorted(set(t0['perSourceScores']) & set(t2['perSourceScores']))
        t2_ci = lambda name: hp_delta[name]['sourceBootstrap95CI']
        material_downstream = any(
            result['sourceBootstrap95CI'] is not None and result['sourceBootstrap95CI'][0] > 0
            for name, result in hp_delta.items()
            if name in ('maxHpNll', 'potionMaskNll')
        ) or any(
            result['sourceBootstrap95CI'] is not None and result['sourceBootstrap95CI'][0] > 0
            for result in hp_delta.get('supportedRelicGroupConstraintNllByGroup', {}).values())
        hp_by_cohort[cohort_name] = {
            'T0': {k: t0[k] for k in ('candidateRows', 'scoredRowsByMetric', 'metrics',
                                      'supportedRelicGroupConstraintNll', 'unscoreableBecauseTransformedTargetOutsideModelDomain', 'unscoredReasons')},
            'T2': {k: t2[k] for k in ('candidateRows', 'scoredRowsByMetric', 'metrics',
                                      'supportedRelicGroupConstraintNll', 'unscoreableBecauseTransformedTargetOutsideModelDomain', 'unscoredReasons')},
            'pairedSourceBootstrapT2MinusT0': hp_delta,
            'commonSupportedWinSources': len(common),
            'gate': {
                'atLeast20SupportedWinRows': len(common) >= 20,
                'hpNllCiStrictlyBelowZero': bool(t2_ci('hpNll') is not None and t2_ci('hpNll')[1] < 0),
                'hpCrpsCiStrictlyBelowZero': bool(t2_ci('hpCrps') is not None and t2_ci('hpCrps')[1] < 0),
                'expectedHpMaeCiNotStrictlyAboveZero': bool(t2_ci('expectedHpAbsError') is not None and t2_ci('expectedHpAbsError')[0] <= 0),
                'noClearDownstreamDegradation': not material_downstream,
                'zeroT2UnscoredRows': not bool(t2['unscoredReasons']),
            },
        }

        retained = [pair for pair in cohort_pairs
                    if minimal._get_three_class_label(pair) == minimal.WIN_RETAINED]
        both_win = [pair for pair in cohort_pairs
                    if int(pair['noTail']['transition']['combatOutcome']) == pilot.WIN
                    and int(pair['activeTail']['transition']['combatOutcome']) == pilot.WIN]
        retained_t0 = _score_conditional_arm(retained, models, arm='activeTail')
        control_t0 = _score_conditional_arm(both_win, models, arm='noTail')
        paired = minimal._paired_bootstrap_delta(control_t0, retained_t0)
        retained_by_cohort[cohort_name] = {
            'winRetainedRows': len(retained), 'pairedNoTailBothWinRows': len(both_win),
            'commonSourceRowsForComparison': len(set(retained_t0['perSourceScores']) & set(control_t0['perSourceScores'])),
            'T0HeadsOnRetainedWins': {k: retained_t0[k] for k in ('candidateWinRows', 'meanMetrics', 'unscoredReasons')},
            'T0HeadsOnPairedNoTailBothWins': {k: control_t0[k] for k in ('candidateWinRows', 'meanMetrics', 'unscoredReasons')},
            'pairedSourceBootstrapRetainedMinusNoTail': paired,
            'anyT0MetricIntervalExcludesZero': any(
                result['sourceBootstrap95CI'] is not None
                and (result['sourceBootstrap95CI'][0] > 0 or result['sourceBootstrap95CI'][1] < 0)
                for result in paired.values()
                if isinstance(result, dict) and 'sourceBootstrap95CI' in result),
        }

    pooled = cohort_results['POOLED']
    losses = pooled['classCounts']['LOSS_CONSUMED']
    loss_sources = pooled['lossConsumedDistinctSources']
    consumed = pooled['consumedRows']
    rare_floor = losses >= 20 and loss_sources >= 10 and consumed >= 20
    pooled_primary = pooled['primaryGate']
    broad_primary = cohort_results['BROAD32']['primaryGate']
    broad_clear_degradation = any(
        comparison.get('sourceBootstrap95CI') is not None
        and comparison['sourceBootstrap95CI'][0] > 0
        for comparison in cohort_results['BROAD32']['threeClassQrVsB1'].values()
        if isinstance(comparison, dict) and 'sourceBootstrap95CI' in comparison)
    q_gate = all(pooled['qConsumption'][key] for key in ('gateNllNotWorse', 'gateBrierNotWorse'))
    r_gate = (pooled['rConditionalRescue']['gateNllCiStrictlyBelowZero']
              and pooled['rConditionalRescue']['gateBrierNotWorse']
              and pooled['rConditionalRescue']['gateAllConsumedRowsB1Scoreable']
              and rare_floor)
    primary_gate = (pooled_primary['allRowsB1Scoreable']
                    and support['exactSupportRows'] == len(pairs)
                    and pooled_primary['nllCiStrictlyBelowZero']
                    and pooled_primary['brierMeanNotWorse']
                    and pooled_primary['brierIntervalShowsNoClearDegradation']
                    and not broad_clear_degradation)
    t2_gate = hp_by_cohort['POOLED']['gate']
    phase4_pass = rare_floor and primary_gate and q_gate and r_gate
    phase5_pass = all(t2_gate.values())
    classification = ('ACTIVE_LIZARD_MINIMAL_CTM_QUALIFIED'
                      if phase4_pass and phase5_pass
                      else 'ACTIVE_LIZARD_QUALIFICATION_INCONCLUSIVE')
    pair_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    pair_jsonl_sha = manifest['jsonl']['sha256']
    selection_sha = manifest['targetSelection']['sha256']
    candidate_integrity = selection.get('integrity', {})
    analysis_script_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    summary = {
        'schema': SCHEMA,
        'baselineGitSha': manifest['baselineGitSha'],
        'analysisScriptSha256': analysis_script_sha,
        'analysisProtocol': {
            'bootstrapReplicates': BOOTSTRAP_REPS,
            'primaryAndBinaryBootstrapSeed': BOOTSTRAP_SEED,
            't2AndRetainedWinBootstrapSeed': minimal.BOOTSTRAP_SEED,
            'bootstrapUnit': 'sourceSeed; keep all rows from each sampled source; row-weighted mean delta',
            'calibration': '10 equal-width bins; report equal-width expected calibration error',
            'b1NegativeReserveDifferenceScoringEpsilon': B1_FLOAT32_EPSILON,
        },
        'cohort': {
            'sourceIds': [int(row['sourceSeed']) for row in selection['targets']],
            'sourceIdsByCohort': {
                name: sorted(source for source, cohort in assignment_by_source.items()
                             if cohort == name)
                for name in ('HARD96', 'BROAD32')},
            'cohortCounts': {**dict(cohort_counts), 'POOLED': len(pairs)},
            'sourceAssignmentSha256': source_assignment_sha,
            'sourceSeedRange': manifest['seedSpec'],
            'sourceAssignmentFreshnessAudit': source_assignment['freshnessAudit'],
            'selectionProtocol': {
                'hard96': source_assignment['hard96Selection'],
                'broad32': selection['broad32HashRule'],
                'outcomeBlind': bool(source_assignment['outcomeBlindSelection']),
                'eligibleCandidates': candidate_integrity.get('eligibleCandidates'),
                'candidateJsonlSha256': selection['candidateJsonlSha256'],
                'candidateManifestSha256': selection['candidateManifestSha256'],
                'candidateProducerGitSha': selection['candidateProducerGitSha'],
                'candidateProducerExecutableSha256': selection['candidateProducerExecutableSha256'],
            },
            'pairJsonlSha256': pair_jsonl_sha,
            'pairManifestSha256': pair_sha,
            'targetSelectionSha256': selection_sha,
            'frozenArtifactSha256': actual_artifact_sha,
            'teacherId': manifest['combatTeacher']['teacher_id'],
            'teacherSimulationsPerCombat': 10000,
            'pairedArmOutcomeCounts': pair_arm_outcomes,
            'frozenCtmHashes': models.hashes,
        },
        'supportAudit': support,
        'b1Coherence': {
            'float32ScoringEpsilon': B1_FLOAT32_EPSILON,
            'counts': dict(b1_kinds),
            'negativeRawDifferences': b1_negative,
            'materiallyIncoherentSources': b1_material_sources,
        },
        'freshThreeClassCounts': {name: result['classCounts']
                                  for name, result in cohort_results.items()},
        'rareEventFloor': {
            'lossConsumedRequired': 20, 'distinctLossSourceRequired': 10,
            'pooledLossConsumed': losses, 'pooledDistinctLossSources': loss_sources,
            'pooledConsumedRows': consumed,
            'passed': rare_floor,
            'classification': None if rare_floor else 'LIZARD_QUALIFICATION_INCONCLUSIVE_RARE_EVENT',
        },
        'phase4': {
            'primaryQrvB1ByCohort': {name: result['threeClassQrVsB1']
                                     for name, result in cohort_results.items()},
            'primaryGateByCohort': {name: result['primaryGate']
                                    for name, result in cohort_results.items()},
            'qConsumptionByCohort': {name: result['qConsumption']
                                     for name, result in cohort_results.items()},
            'rConditionalRescueByCohort': {name: result['rConditionalRescue']
                                           for name, result in cohort_results.items()},
            'gates': {'rareEventFloor': rare_floor, 'primaryThreeClass': primary_gate,
                      'qConsumption': q_gate, 'rConditionalRescue': r_gate,
                      'allRowsWithinExactSupport': support['exactSupportRows'] == len(pairs),
                      'broad32ClearPrimaryDegradation': broad_clear_degradation},
        },
        'phase5': {
            'freshT2ByCohort': hp_by_cohort,
            'retainedWinT0DistributionByCohort': retained_by_cohort,
            'pooledGate': t2_gate,
            'passed': phase5_pass,
        },
        'phase6AndLater': {
            'ancestralQualificationRun': False,
            'nativeRuntimeIntegration': False,
            'pythonNativeParity': False,
            'liveSmokeSeed13027029': False,
            'stopReason': ('rare-event floor not reached' if not rare_floor
                           else 'one or more earlier frozen gates did not pass'),
        },
        'finalClassification': classification,
        'qualificationSubclassification': (
            'LIZARD_QUALIFICATION_INCONCLUSIVE_RARE_EVENT' if not rare_floor else None),
        'claimBoundary': ('Fresh paired evidence is descriptive; no runtime support was integrated. '
                          'The production active-Lizard fail-closed guard remains in place.'),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--artifact-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.manifest, args.artifact, args.artifact_sha256, args.output)
    compact = {key: result[key] for key in ('rareEventFloor', 'finalClassification',
                                             'qualificationSubclassification', 'phase6AndLater')}
    compact['freshThreeClassCounts'] = result['freshThreeClassCounts']
    print(json.dumps(compact, indent=2))


if __name__ == '__main__':
    main()
