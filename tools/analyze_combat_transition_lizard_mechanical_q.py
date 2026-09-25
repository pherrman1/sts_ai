#!/usr/bin/env python3
"""Analyze the frozen mechanical-q / learned-r Lizard candidate.

This analyzer scores existing paired outcomes only. It never fits or changes
the frozen r model, and it never changes production CTM support.
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
from tools import combat_transition_lizard_mechanical_q as candidate_model
from tools import combat_transition_lizard_minimal as minimal
from tools import combat_transition_lizard_pair_pilot as pilot
from tools.combat_transition_contract import sha256

SCHEMA = 'active_lizard_mechanical_q_frozen_r_analysis_v1'
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 20260925
FLOAT32_EPSILON = candidate_model.B1_FLOAT32_EPSILON
# One read-only retrospective input is explicitly allowed to use the retired
# PR #326 Silver teacher. Pin the complete packet so this exception cannot be
# reused for a different historical or fresh cohort.
PR326_SCREEN_PACKET = {
    'pairManifestSha256': 'a8a38bb7f19a4e2a5ff6407eeb35c42fe886fa343c69cd841cc3ce6f7e42eb23',
    'pairJsonlSha256': 'ad297c0d189290d1956d9fb9a5f08e417f9861238e4986ba33f2f26c0be34d5b',
    'targetSelectionSha256': 'a78f4e8ddccc39769a9b01f9f4fc59195b79bdfd5ec427b062ee16a03605905b',
    'sourceAssignmentSha256': '46af3ba0397d523da7017daaa92fa5c37813d496fbf5608a7069ea39398ee992',
    'stateSelection': 'predeclared_qr_hard96_broad32_hash_v1',
}


def _source_bootstrap_ci(values, source_ids, *, seed):
    values = np.asarray(values, dtype=np.float64)
    sources = np.asarray(source_ids, dtype=np.int64)
    if values.shape != sources.shape or not len(values):
        return None
    groups = defaultdict(list)
    for source, value in zip(sources, values):
        groups[int(source)].append(float(value))
    unique = np.asarray(sorted(groups), dtype=np.int64)
    rng = np.random.default_rng(seed)
    boot = np.empty(BOOTSTRAP_REPS, dtype=np.float64)
    for index in range(BOOTSTRAP_REPS):
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
        raise ValueError('invalid three-class probabilities')
    nll = -np.log(np.maximum(p[np.arange(len(y)), y], 1e-300))
    brier = np.sum((p - np.eye(3, dtype=np.float64)[y]) ** 2, axis=1)
    return nll, brier


def _binary_arrays(probabilities, labels):
    p = np.asarray(probabilities, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    if p.shape != y.shape or not len(y):
        return None
    p = np.clip(p, 1e-15, 1.0 - 1e-15)
    return (-(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)), (p - y) ** 2)


def _multiclass_comparison(baseline, treatment, labels, sources, *, seed):
    base = _multiclass_arrays(baseline, labels)
    candidate = _multiclass_arrays(treatment, labels)
    if base is None or candidate is None:
        return {'rows': 0, 'threeClassNll': None, 'multiclassBrier': None}
    base_nll, base_brier = base
    candidate_nll, candidate_brier = candidate
    source_array = np.asarray(sources, dtype=np.int64)
    result = {
        'rows': len(source_array),
        'baseline': minimal._prob_metrics(baseline, labels),
        'candidate': minimal._prob_metrics(treatment, labels),
    }
    for offset, (name, delta) in enumerate((
            ('threeClassNll', candidate_nll - base_nll),
            ('multiclassBrier', candidate_brier - base_brier))):
        result[name] = {
            'meanCandidateMinusB1': float(delta.mean()),
            'sourceBootstrap95CI': _source_bootstrap_ci(
                delta, source_array, seed=seed + offset),
        }
    return result


def _binary_comparison(baseline, treatment, labels, sources, *, seed):
    base = _binary_arrays(baseline, labels)
    candidate = _binary_arrays(treatment, labels)
    if base is None or candidate is None:
        return {'rows': 0, 'nll': None, 'brier': None}
    base_nll, base_brier = base
    candidate_nll, candidate_brier = candidate
    source_array = np.asarray(sources, dtype=np.int64)
    result = {
        'rows': len(source_array),
        'baseline': minimal._binary_metrics(baseline, labels),
        'candidate': minimal._binary_metrics(treatment, labels),
    }
    for offset, (name, delta) in enumerate((('nll', candidate_nll - base_nll),
                                             ('brier', candidate_brier - base_brier))):
        result[name] = {
            'meanCandidateMinusB1': float(delta.mean()),
            'sourceBootstrap95CI': _source_bootstrap_ci(
                delta, source_array, seed=seed + offset),
        }
    return result


def _calibration(probabilities, labels, bins=10):
    p = np.asarray(probabilities, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    if not len(y):
        return {'rows': 0, 'meanPredicted': None, 'observedRate': None, 'bins': []}
    bin_ids = np.minimum((np.clip(p, 0.0, 1.0) * bins).astype(int), bins - 1)
    summaries, weighted_error = [], 0.0
    for index in range(bins):
        mask = bin_ids == index
        if not mask.any():
            continue
        predicted, observed, count = float(p[mask].mean()), float(y[mask].mean()), int(mask.sum())
        weighted_error += count / len(y) * abs(predicted - observed)
        summaries.append({'lower': index / bins, 'upper': (index + 1) / bins,
                          'rows': count, 'meanPredicted': predicted, 'observedRate': observed})
    return {
        'rows': len(y), 'meanPredicted': float(p.mean()), 'observedRate': float(y.mean()),
        'calibrationInTheLargePredictedMinusObserved': float(p.mean() - y.mean()),
        'expectedCalibrationErrorEqualWidth': float(weighted_error), 'bins': summaries,
    }


def _row_b1_probabilities(p_ordinary, p_reserve):
    po, pr = float(p_ordinary), float(p_reserve)
    difference = pr - po
    raw = [po, difference, 1.0 - pr]
    if difference < -FLOAT32_EPSILON:
        return raw, None, 'material_incoherence'
    if difference < 0.0:
        return raw, [po, 0.0, 1.0 - po], 'within_float32_epsilon'
    return raw, [po, difference, 1.0 - pr], 'coherent'


def _support_audit(pairs, models):
    reasons = Counter()
    eligible = 0
    for pair in pairs:
        failed = False
        pre = pilot._strip_lizard(pair['activeTail']['transition']['pre'])
        predictor = pilot._strip_lizard_input(pair['activeTail']['predictorInput'])
        if pre != pair['noTail']['transition']['pre']:
            reasons['stripped_active_pre_differs_from_no_tail_pre'] += 1
            failed = True
        if predictor != pair['noTail']['predictorInput']:
            reasons['stripped_active_predictor_differs_from_no_tail_predictor'] += 1
            failed = True
        support_reasons = composed.full_support_reasons(pre, predictor, models)
        if support_reasons:
            reasons['unsupported:' + ','.join(support_reasons)] += 1
            failed = True
        boundaries = minimal.native_boundary_reasons(pair)
        if boundaries:
            reasons.update(boundaries)
            failed = True
        if not failed:
            eligible += 1
    return {'rows': len(pairs), 'exactSupportRows': eligible,
            'supportAndBoundaryFailureRows': len(pairs) - eligible,
            'failureCounts': dict(sorted(reasons.items()))}


def _validate_existing_screen_packet_header(manifest_path: Path) -> dict:
    if sha256(manifest_path) != PR326_SCREEN_PACKET['pairManifestSha256']:
        raise ValueError('existing-data screen is restricted to the exact pinned PR #326 packet')
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('jsonl', {}).get('sha256') != PR326_SCREEN_PACKET['pairJsonlSha256']:
        raise ValueError('PR #326 pair JSONL hash differs from the pinned screen packet')
    if manifest.get('targetSelection', {}).get('sha256') != PR326_SCREEN_PACKET['targetSelectionSha256']:
        raise ValueError('PR #326 target-selection hash differs from the pinned screen packet')
    return manifest


def _native_transfer_agreement(archived_pairs, native_pairs) -> dict:
    archived_by_source = {int(row['pair']['sourceSeed']): row for row in archived_pairs}
    native_by_source = {int(row['pair']['sourceSeed']): row for row in native_pairs}
    if set(archived_by_source) != set(native_by_source):
        raise ValueError('native transfer source set differs from archived PR #326 cohort')
    class_names = list(minimal.CLASS_NAMES)
    class_matrix = {old: {new: 0 for new in class_names} for old in class_names}
    arm_matrix = {
        arm: {'archived_WIN': {'native_WIN': 0, 'native_DEATH': 0},
              'archived_DEATH': {'native_WIN': 0, 'native_DEATH': 0}}
        for arm in ('noTail', 'activeTail')}
    tail_matrix = {'archived_CONSUMED': {'native_CONSUMED': 0, 'native_RETAINED': 0},
                   'archived_RETAINED': {'native_CONSUMED': 0, 'native_RETAINED': 0}}
    exact_state_sources, state_mismatches = [], []
    label_disagreements = []
    def outcome_name(row):
        value = int(row['transition']['combatOutcome'])
        if value == pilot.WIN:
            return 'WIN'
        if value == pilot.DEATH:
            return 'DEATH'
        raise ValueError('transfer pair has undecided combat outcome')
    for source in sorted(archived_by_source):
        old, new = archived_by_source[source], native_by_source[source]
        old_state = (old['pair']['fightIdx'], old['pair']['sourceStateFingerprint'],
                     old['noTail']['transition']['pre'], old['noTail']['predictorInput'])
        new_state = (new['pair']['fightIdx'], new['pair']['sourceStateFingerprint'],
                     new['noTail']['transition']['pre'], new['noTail']['predictorInput'])
        if old_state == new_state:
            exact_state_sources.append(source)
        else:
            state_mismatches.append(source)
            continue
        old_label = minimal.CLASS_NAMES[minimal._get_three_class_label(old)]
        new_label = minimal.CLASS_NAMES[minimal._get_three_class_label(new)]
        class_matrix[old_label][new_label] += 1
        if old_label != new_label:
            label_disagreements.append(source)
        for arm in ('noTail', 'activeTail'):
            arm_matrix[arm][f'archived_{outcome_name(old[arm])}'][
                f"native_{outcome_name(new[arm])}"] += 1
        old_consumed = int(old['pair']['activeTailPostData']) == 0
        new_consumed = int(new['pair']['activeTailPostData']) == 0
        tail_matrix['archived_CONSUMED' if old_consumed else 'archived_RETAINED'][
            'native_CONSUMED' if new_consumed else 'native_RETAINED'] += 1
    compared = len(exact_state_sources)
    return {
        'archivedRows': len(archived_pairs), 'nativeRows': len(native_pairs),
        'exactPrecombatStateRows': compared,
        'stateMismatchRows': len(state_mismatches), 'stateMismatchSources': state_mismatches,
        'threeClassLabelAgreement': {
            'matrixArchivedRowsByNativeColumns': class_matrix,
            'comparedRows': compared,
            'agreements': compared - len(label_disagreements),
            'disagreements': len(label_disagreements),
            'disagreementSources': label_disagreements,
        },
        'combatOutcomeAgreementByArm': {
            arm: {'matrix': table, 'agreements': sum(table[f'archived_{value}'][f'native_{value}']
                                                       for value in ('WIN', 'DEATH')),
                  'comparedRows': compared}
            for arm, table in arm_matrix.items()},
        'tailConsumptionAgreement': {'matrix': tail_matrix, 'comparedRows': compared,
            'agreements': tail_matrix['archived_CONSUMED']['native_CONSUMED']
                + tail_matrix['archived_RETAINED']['native_RETAINED']},
        'claimBoundary': 'descriptive agreement table only; teachers are analyzed separately and never pooled',
    }


def _has_clear_positive_delta(metric_results) -> bool:
    for item in metric_results:
        interval = item.get('sourceBootstrap95CI') if isinstance(item, dict) else None
        if interval is not None and interval[0] > 0.0:
            return True
    return False


def _score_conditional_arm(pairs, models, *, arm):
    """Score ordinary T0 heads on recorded wins from the requested arm."""
    scores, per_source, failures = defaultdict(list), {}, Counter()
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
                p_potion = evaluate.potion_prob(
                    models, potion_z, slots[None], np.asarray([capacity]),
                    np.asarray([delta_index]), ending_fraction)[0]
                p_relic = evaluate.relic_prob(
                    models, z, np.asarray([target_index]), ending_fraction,
                    np.asarray([potion_mask], dtype=np.int64))
            hp_nll = -math.log(max(float(p_hp[target_index]), 1e-300))
            hp_crps = minimal._crps(p_hp, target_index)
            expected_hp_error = abs(expected_hp - ending)
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
            row_scores = {
                'hpNll': hp_nll, 'hpCrps': hp_crps,
                'expectedHpAbsError': expected_hp_error,
                'maxHpNll': max_nll, 'potionMaskNll': potion_nll,
                'relicConstraintNllByGroup': relic_row,
            }
            per_source[source] = row_scores
            for name in ('hpNll', 'hpCrps', 'expectedHpAbsError', 'maxHpNll', 'potionMaskNll'):
                scores[name].append(row_scores[name])
            for group, value in relic_row.items():
                scores['relic:' + group].append(value)
        except (KeyError, ValueError, IndexError, RuntimeError) as error:
            failures[f'{type(error).__name__}:{error}'] += 1
    return {
        'candidateWinRows': sum(int(pair[arm]['transition']['combatOutcome']) == pilot.WIN
                                for pair in pairs),
        'scoredRowsByMetric': {name: len(values) for name, values in sorted(scores.items())},
        'meanMetrics': {name: float(np.mean(values)) if values else None
                        for name, values in sorted(scores.items())},
        'perSourceScores': per_source,
        'unscoredReasons': dict(sorted(failures.items())),
    }


def _cohorts_from_assignment(assignment):
    if isinstance(assignment.get('cohorts'), dict):
        return {name: sorted(int(x) for x in sources)
                for name, sources in assignment['cohorts'].items()}
    return {
        'HARD96': sorted(int(x) for x in assignment['hard96SourceIds']),
        'BROAD32': sorted(int(x) for x in assignment['broad32SourceIds']),
    }


def _cohort_indices(rows, name):
    if name == 'POOLED':
        return list(range(len(rows)))
    return [index for index, row in enumerate(rows) if row['cohort'] == name]


def _load_frozen_selection(manifest_path, manifest, pairs):
    selection_path = pilot._resolve_manifest_file(
        manifest['targetSelection']['path'], manifest_path.parent)
    if sha256(selection_path) != manifest['targetSelection']['sha256']:
        raise ValueError('target selection hash mismatch')
    selection = json.loads(selection_path.read_text())
    source_assignment_path = pilot._resolve_manifest_file(
        selection['sourceAssignmentPath'], manifest_path.parent)
    source_assignment_sha = sha256(source_assignment_path)
    if source_assignment_sha != selection.get('sourceAssignmentSha256'):
        raise ValueError('predeclared source assignment hash mismatch')
    assignment = json.loads(source_assignment_path.read_text())
    cohorts = _cohorts_from_assignment(assignment)
    assignment_by_source = {
        int(source): name for name, sources in cohorts.items() for source in sources}
    targets = selection.get('targets', [])
    target_by_source = {int(row['sourceSeed']): row for row in targets}
    if len(target_by_source) != len(targets) or set(target_by_source) != set(assignment_by_source):
        raise ValueError('targets do not exactly match the predeclared source assignment')
    if len(pairs) != len(targets):
        raise ValueError('target selection and paired source counts differ')
    for source, target in target_by_source.items():
        if target.get('qualificationCohort') != assignment_by_source[source]:
            raise ValueError(f'cohort assignment mismatch for source {source}')
    for pair in pairs:
        source = int(pair['pair']['sourceSeed'])
        target = target_by_source.get(source)
        if (target is None or int(target['fightIdx']) != int(pair['pair']['fightIdx'])):
            raise ValueError(f'paired target identity mismatch for source {source}')
    candidate_manifest_path = manifest_path.parent / 'fresh_candidate_states.jsonl.manifest.json'
    candidate_data_path = manifest_path.parent / 'fresh_candidate_states.jsonl'
    if selection.get('candidateGeneratorManifestSha256'):
        if sha256(candidate_manifest_path) != selection['candidateGeneratorManifestSha256']:
            raise ValueError('fresh candidate-state manifest hash mismatch')
    elif selection.get('candidateManifestSha256'):
        if sha256(candidate_manifest_path) != selection['candidateManifestSha256']:
            raise ValueError('candidate-state manifest hash mismatch')
    if selection.get('candidateJsonlSha256') and sha256(candidate_data_path) != selection['candidateJsonlSha256']:
        raise ValueError('candidate-state JSONL hash mismatch')
    return selection, assignment, cohorts, target_by_source, source_assignment_sha


def _analyze(manifest_path: Path, candidate_path: Path, expected_candidate_sha: str | None,
             output_path: Path, *, purpose: str,
             archived_manifest_path: Path | None = None,
             native_teacher_path: Path | None = None) -> dict:
    candidate, artifact, candidate_sha = candidate_model.load_candidate(
        candidate_path, expected_candidate_sha)
    archived_pairs, transfer_agreement = None, None
    native_teacher, native_teacher_sha = None, None
    if purpose == 'existing_data_screen':
        _validate_existing_screen_packet_header(manifest_path)
        manifest, pairs = pilot.validate_pair_corpus(
            manifest_path, historical_teacher=candidate['silverTeacher'])
    else:
        if native_teacher_path is None:
            raise ValueError('native evaluation requires a frozen current native-Silver teacher manifest')
        native_teacher = json.loads(native_teacher_path.read_text())
        pilot.validate_teacher(native_teacher)
        native_teacher_sha = sha256(native_teacher_path)
        manifest, pairs = pilot.validate_pair_corpus(manifest_path)
        if (manifest['combatTeacher'] != native_teacher
                or manifest['combatTeacherManifestSha256'] != native_teacher_sha
                or manifest['producerGitSha'] != native_teacher['git_sha']
                or manifest['producerExecutableSha256'] != native_teacher['executable_sha256']):
            raise ValueError('native pair provenance differs from the frozen current teacher manifest')
        if purpose == 'native_teacher_transfer':
            if archived_manifest_path is None:
                raise ValueError('native teacher transfer requires the exact archived PR #326 manifest')
            _validate_existing_screen_packet_header(archived_manifest_path)
            archived_manifest, archived_pairs = pilot.validate_pair_corpus(
                archived_manifest_path, historical_teacher=candidate['silverTeacher'])
            archived_selection, archived_assignment, archived_cohorts, archived_targets, archived_assignment_sha = (
                _load_frozen_selection(archived_manifest_path, archived_manifest, archived_pairs))
            if (manifest.get('targetSelection', {}).get('sha256')
                    != PR326_SCREEN_PACKET['targetSelectionSha256']):
                raise ValueError('native teacher transfer must use the exact archived target-selection bytes')
        else:
            archived_selection, archived_assignment, archived_cohorts, archived_targets = None, None, None, None
            archived_assignment_sha = None
    import torch
    torch.set_num_threads(4)
    models = composed.FrozenModels('cuda' if torch.cuda.is_available() else 'cpu')
    if models.hashes != candidate['frozenCtmComponentHashes']:
        raise ValueError('analysis CTM component hashes differ from frozen candidate')
    selection, assignment, cohorts, target_by_source, assignment_sha = _load_frozen_selection(
        manifest_path, manifest, pairs)
    if purpose == 'existing_data_screen':
        if (assignment_sha != PR326_SCREEN_PACKET['sourceAssignmentSha256']
                or selection.get('stateSelection') != PR326_SCREEN_PACKET['stateSelection']):
            raise ValueError('PR #326 source assignment or state-selection policy differs from pinned screen packet')
    elif purpose == 'native_teacher_transfer':
        if (assignment_sha != archived_assignment_sha
                or archived_selection.get('stateSelection') != selection.get('stateSelection')
                or archived_cohorts != cohorts
                or archived_targets != target_by_source):
            raise ValueError('native teacher transfer changed the exact archived source/state selection')
        transfer_agreement = _native_transfer_agreement(archived_pairs, pairs)
    support = _support_audit(pairs, models)
    records = minimal._precombat_risk_features(pairs, models)
    rows, labels = [], []
    b1_kinds, b1_negative = Counter(), []
    for pair, record in zip(pairs, records):
        source = int(pair['pair']['sourceSeed'])
        target = target_by_source[source]
        label = minimal._get_three_class_label(pair)
        q, r, class_probabilities = candidate_model.predict(
            float(record['pOrdinaryWin']), float(record['pReserveWin']), artifact)
        raw, scoring, kind = _row_b1_probabilities(
            record['pOrdinaryWin'], record['pReserveWin'])
        b1_kinds[kind] += 1
        if raw[1] < 0:
            b1_negative.append({
                'sourceSeed': source, 'fightIdx': int(pair['pair']['fightIdx']),
                'cohort': target['qualificationCohort'],
                'rawReserveMinusOrdinary': raw[1], 'kind': kind,
            })
        rows.append({
            'sourceSeed': source, 'fightIdx': int(pair['pair']['fightIdx']),
            'cohort': target['qualificationCohort'], 'label': int(label),
            'pOrdinaryWin': float(record['pOrdinaryWin']),
            'pReserveWin': float(record['pReserveWin']),
            'qB1': 1.0 - float(record['pOrdinaryWin']), 'qCandidate': q,
            'rCandidate': r,
            'rB1': None,
            'classProbabilitiesCandidate': class_probabilities,
            'classProbabilitiesB1Raw': raw,
            'classProbabilitiesB1Scoring': scoring,
            'b1CoherenceKind': kind,
        })
        labels.append(label)
    labels = np.asarray(labels, dtype=np.int64)
    sources = np.asarray([row['sourceSeed'] for row in rows], dtype=np.int64)
    q_candidate = np.asarray([row['qCandidate'] for row in rows], dtype=np.float64)
    q_b1 = np.asarray([row['qB1'] for row in rows], dtype=np.float64)
    candidate_class = np.asarray([row['classProbabilitiesCandidate'] for row in rows], dtype=np.float64)
    b1_scoreable = np.asarray([row['classProbabilitiesB1Scoring'] is not None for row in rows])
    b1_class = np.asarray([row['classProbabilitiesB1Scoring'] or [0.0, 0.0, 0.0]
                           for row in rows], dtype=np.float64)
    consumed = np.isin(labels, (minimal.WIN_CONSUMED, minimal.LOSS_CONSUMED))
    consumed_indices = np.flatnonzero(consumed)
    r_candidate = np.asarray([rows[index]['rCandidate'] for index in consumed_indices], dtype=np.float64)
    consumed_labels = (labels[consumed_indices] == minimal.WIN_CONSUMED).astype(np.int64)
    consumed_sources = sources[consumed_indices]
    r_b1, r_valid = [], []
    for index in consumed_indices:
        po, pr = rows[index]['pOrdinaryWin'], rows[index]['pReserveWin']
        numerator, denominator = pr - po, 1.0 - po
        if denominator <= 1e-12 or numerator < -FLOAT32_EPSILON:
            r_b1.append(float('nan'))
            r_valid.append(False)
        else:
            r_b1.append(min(1.0, max(0.0, numerator) / denominator))
            r_valid.append(True)
    r_b1 = np.asarray(r_b1, dtype=np.float64)
    r_valid = np.asarray(r_valid, dtype=bool)
    for consumed_offset, index in enumerate(consumed_indices):
        rows[index]['rB1'] = float(r_b1[consumed_offset]) if r_valid[consumed_offset] else None

    cohort_names = list(cohorts)
    cohort_results = {}
    consumed_offset = {int(row_index): offset for offset, row_index in enumerate(consumed_indices)}
    for cohort_name in cohort_names + ['POOLED']:
        indices = np.asarray(_cohort_indices(rows, cohort_name), dtype=np.int64)
        cohort_labels, cohort_sources = labels[indices], sources[indices]
        class_mask = b1_scoreable[indices]
        class_global = indices[class_mask]
        primary = _multiclass_comparison(
            b1_class[class_global], candidate_class[class_global], labels[class_global],
            sources[class_global], seed=BOOTSTRAP_SEED + 10 + len(cohort_name))
        candidate_consumed = np.isin(cohort_labels, (minimal.WIN_CONSUMED, minimal.LOSS_CONSUMED))
        q_truth = candidate_consumed.astype(np.int64)
        q_cmp = _binary_comparison(q_b1[indices], q_candidate[indices], q_truth,
                                   cohort_sources, seed=BOOTSTRAP_SEED + 20 + len(cohort_name))
        consumed_local_indices = indices[candidate_consumed]
        r_offsets = np.asarray([consumed_offset[int(i)] for i in consumed_local_indices], dtype=np.int64)
        r_valid_local = r_valid[r_offsets]
        if r_valid_local.any():
            r_cmp = _binary_comparison(
                r_b1[r_offsets][r_valid_local],
                r_candidate[r_offsets][r_valid_local],
                (labels[consumed_local_indices][r_valid_local] == minimal.WIN_CONSUMED).astype(np.int64),
                sources[consumed_local_indices][r_valid_local],
                seed=BOOTSTRAP_SEED + 30 + len(cohort_name))
        else:
            r_cmp = {'rows': 0, 'nll': None, 'brier': None}
        counts = Counter(minimal.CLASS_NAMES[int(value)] for value in cohort_labels)
        loss_sources = {int(rows[i]['sourceSeed']) for i in indices
                        if labels[i] == minimal.LOSS_CONSUMED}
        cohort_results[cohort_name] = {
            'rows': len(indices),
            'classCounts': {name: counts[name] for name in minimal.CLASS_NAMES},
            'consumedRows': int(candidate_consumed.sum()),
            'lossConsumedDistinctSources': len(loss_sources),
            'threeClassCandidateVsB1': primary,
            'qConsumption': {
                'candidate': minimal._binary_metrics(q_candidate[indices], q_truth),
                'b1': minimal._binary_metrics(q_b1[indices], q_truth),
                'comparison': q_cmp,
                'calibration': _calibration(q_candidate[indices], q_truth),
                'exactParityRows': int(np.count_nonzero(q_candidate[indices] == q_b1[indices])),
                'rows': len(indices),
            },
            'rConditionalRescue': {
                'consumedRows': int(candidate_consumed.sum()),
                'b1ScoreableConsumedRows': int(r_valid_local.sum()),
                'candidate': minimal._binary_metrics(
                    r_candidate[r_offsets],
                    (labels[consumed_local_indices] == minimal.WIN_CONSUMED).astype(np.int64)),
                'b1': minimal._binary_metrics(
                    r_b1[r_offsets][r_valid_local],
                    (labels[consumed_local_indices][r_valid_local] == minimal.WIN_CONSUMED).astype(np.int64))
                    if r_valid_local.any() else None,
                'comparisonOnB1ScoreableConsumedRows': r_cmp,
                'calibration': _calibration(
                    r_candidate[r_offsets],
                    (labels[consumed_local_indices] == minimal.WIN_CONSUMED).astype(np.int64)),
                'allConsumedRowsB1Scoreable': bool(r_valid_local.all()),
            },
            'primaryGate': {
                'allRowsB1Scoreable': bool(class_mask.all()),
                'nllCiStrictlyBelowZero': bool(
                    primary.get('threeClassNll', {}).get('sourceBootstrap95CI') is not None
                    and primary['threeClassNll']['sourceBootstrap95CI'][1] < 0.0),
                'brierMeanNotWorse': bool(
                    primary.get('multiclassBrier', {}).get('meanCandidateMinusB1') is not None
                    and primary['multiclassBrier']['meanCandidateMinusB1'] <= 0.0),
                'brierIntervalShowsNoClearDegradation': bool(
                    primary.get('multiclassBrier', {}).get('sourceBootstrap95CI') is not None
                    and primary['multiclassBrier']['sourceBootstrap95CI'][0] <= 0.0),
            },
        }

    hp_by_cohort, retained_by_cohort = {}, {}
    for cohort_name in cohort_names + ['POOLED']:
        cohort_pairs = [pairs[i] for i in _cohort_indices(rows, cohort_name)]
        t0 = minimal.score_hp_treatment(cohort_pairs, models, 'T0_ordinary')
        t2 = minimal.score_hp_treatment(cohort_pairs, models, 'T2_revive')
        hp_delta = minimal._paired_bootstrap_delta(t0, t2)
        common = sorted(set(t0['perSourceScores']) & set(t2['perSourceScores']))
        def metric_ci(name):
            return hp_delta.get(name, {}).get('sourceBootstrap95CI')
        material_downstream = any(
            result.get('sourceBootstrap95CI') is not None
            and result['sourceBootstrap95CI'][0] > 0.0
            for name, result in hp_delta.items()
            if name in ('maxHpNll', 'potionMaskNll')) or any(
            result.get('sourceBootstrap95CI') is not None
            and result['sourceBootstrap95CI'][0] > 0.0
            for result in hp_delta.get('supportedRelicGroupConstraintNllByGroup', {}).values())
        score_rows = len(t2['perSourceScores'])
        hp_by_cohort[cohort_name] = {
            'T0': {key: t0[key] for key in ('candidateRows', 'metrics',
                    'supportedRelicGroupConstraintNll', 'unscoreableBecauseTransformedTargetOutsideModelDomain',
                    'unscoredReasons')},
            'T2': {key: t2[key] for key in ('candidateRows', 'metrics',
                    'supportedRelicGroupConstraintNll', 'unscoreableBecauseTransformedTargetOutsideModelDomain',
                    'unscoredReasons')},
            'T2ScoredRowsByMetric': {key: score_rows for key in
                ('hpNll', 'hpCrps', 'expectedHpAbsError', 'maxHpNll', 'potionMaskNll')},
            'pairedSourceBootstrapT2MinusT0': hp_delta,
            'commonSupportedConsumedWinSources': len(common),
            'gate': {
                'atLeast20SupportedConsumedWinRows': len(common) >= 20,
                'hpNllCiStrictlyBelowZero': bool(metric_ci('hpNll') is not None and metric_ci('hpNll')[1] < 0.0),
                'hpCrpsCiStrictlyBelowZero': bool(metric_ci('hpCrps') is not None and metric_ci('hpCrps')[1] < 0.0),
                'expectedHpMaeNoClearDegradation': bool(
                    metric_ci('expectedHpAbsError') is not None
                    and metric_ci('expectedHpAbsError')[0] <= 0.0),
                'noClearDownstreamDegradation': not material_downstream,
                'zeroT2UnscoredOrDomainInvalidRows': (
                    score_rows == int(t2['candidateRows'])
                    and not t2['unscoredReasons']
                    and t2['unscoreableBecauseTransformedTargetOutsideModelDomain'] == 0),
            },
        }
        retained = [pair for pair in cohort_pairs
                    if minimal._get_three_class_label(pair) == minimal.WIN_RETAINED]
        both_win = [pair for pair in cohort_pairs
                    if int(pair['noTail']['transition']['combatOutcome']) == pilot.WIN
                    and int(pair['activeTail']['transition']['combatOutcome']) == pilot.WIN]
        retained_scores = _score_conditional_arm(retained, models, arm='activeTail')
        control_scores = _score_conditional_arm(both_win, models, arm='noTail')
        shared = sorted(set(retained_scores['perSourceScores']) & set(control_scores['perSourceScores']))
        paired = {}
        metric_names = ('hpNll', 'hpCrps', 'expectedHpAbsError', 'maxHpNll', 'potionMaskNll')
        for offset, metric in enumerate(metric_names):
            delta = np.asarray([
                retained_scores['perSourceScores'][source][metric]
                - control_scores['perSourceScores'][source][metric]
                for source in shared], dtype=np.float64)
            paired[metric] = {
                'pairs': len(delta),
                'meanRetainedMinusNoTail': float(delta.mean()) if len(delta) else None,
                'sourceBootstrap95CI': _source_bootstrap_ci(
                    delta, shared, seed=BOOTSTRAP_SEED + 100 + offset)
                    if len(delta) else None,
            }
        relic_groups = set()
        for source in shared:
            relic_groups.update(retained_scores['perSourceScores'][source]['relicConstraintNllByGroup'])
            relic_groups.update(control_scores['perSourceScores'][source]['relicConstraintNllByGroup'])
        paired_relic = {}
        for offset, group in enumerate(sorted(relic_groups)):
            common_group_sources = [source for source in shared
                if group in retained_scores['perSourceScores'][source]['relicConstraintNllByGroup']
                and group in control_scores['perSourceScores'][source]['relicConstraintNllByGroup']]
            delta = np.asarray([
                retained_scores['perSourceScores'][source]['relicConstraintNllByGroup'][group]
                - control_scores['perSourceScores'][source]['relicConstraintNllByGroup'][group]
                for source in common_group_sources], dtype=np.float64)
            paired_relic[group] = {
                'pairs': len(delta),
                'meanRetainedMinusNoTail': float(delta.mean()) if len(delta) else None,
                'sourceBootstrap95CI': _source_bootstrap_ci(
                    delta, common_group_sources,
                    seed=BOOTSTRAP_SEED + 120 + offset) if len(delta) else None,
            }
        retained_by_cohort[cohort_name] = {
            'winRetainedRows': len(retained),
            'pairedNoTailBothWinRows': len(both_win),
            'commonSourceRowsForComparison': len(shared),
            'T0HeadsOnRetainedWins': {
                'candidateWinRows': retained_scores['candidateWinRows'],
                'scoredRowsByMetric': retained_scores['scoredRowsByMetric'],
                'meanMetrics': retained_scores['meanMetrics'],
                'unscoredReasons': retained_scores['unscoredReasons'],
            },
            'T0HeadsOnPairedNoTailBothWins': {
                'candidateWinRows': control_scores['candidateWinRows'],
                'scoredRowsByMetric': control_scores['scoredRowsByMetric'],
                'meanMetrics': control_scores['meanMetrics'],
                'unscoredReasons': control_scores['unscoredReasons'],
            },
            'pairedSourceBootstrapRetainedMinusNoTail': paired,
            'supportedRelicGroups': paired_relic,
            'diagnostics': {
                'cardsRelicWarningReproduces': bool(
                    paired_relic.get('cards', {}).get('sourceBootstrap95CI') is not None
                    and paired_relic['cards']['sourceBootstrap95CI'][0] > 0.0),
                'potionSignalClear': bool(
                    paired.get('potionMaskNll', {}).get('sourceBootstrap95CI') is not None
                    and paired['potionMaskNll']['sourceBootstrap95CI'][0] > 0.0),
            },
        }

    pooled = cohort_results['POOLED']
    loss_count = pooled['classCounts']['LOSS_CONSUMED']
    loss_sources = pooled['lossConsumedDistinctSources']
    consumed_count = pooled['consumedRows']
    rare_floor = loss_count >= 20 and loss_sources >= 10 and consumed_count >= 20
    pooled_primary = pooled['primaryGate']
    pooled_primary_scores = pooled['threeClassCandidateVsB1']
    all_q_parity = bool(np.array_equal(q_candidate, q_b1))
    q_gate = all_q_parity
    r_result = pooled['rConditionalRescue']
    r_ci = r_result['comparisonOnB1ScoreableConsumedRows'].get('nll', {}).get('sourceBootstrap95CI')
    r_brier = r_result['comparisonOnB1ScoreableConsumedRows'].get('brier', {}).get('meanCandidateMinusB1')
    r_nonrare_gate = bool(
        r_ci is not None and r_ci[1] < 0.0 and r_brier is not None and r_brier <= 0.0
        and r_result['allConsumedRowsB1Scoreable'])
    broad_name = next((name for name in cohort_names if name.startswith('BROAD')), None)
    broad_clear_degradation = False
    if broad_name:
        broad_primary = cohort_results[broad_name]['threeClassCandidateVsB1']
        broad_clear_degradation = any(
            result.get('sourceBootstrap95CI') is not None
            and result['sourceBootstrap95CI'][0] > 0.0
            for result in broad_primary.values() if isinstance(result, dict))
    primary_gate = (
        pooled_primary['allRowsB1Scoreable']
        and support['exactSupportRows'] == len(pairs)
        and pooled_primary['nllCiStrictlyBelowZero']
        and pooled_primary['brierMeanNotWorse']
        and pooled_primary['brierIntervalShowsNoClearDegradation']
        and not broad_clear_degradation)
    t2_gate = hp_by_cohort['POOLED']['gate']
    qualification_gates_without_rare = (
        primary_gate and q_gate and r_nonrare_gate and all(t2_gate.values()))
    if qualification_gates_without_rare and rare_floor:
        classification = 'ACTIVE_LIZARD_MECHANICAL_Q_LEARNED_R_T2_NATIVE_QUALIFIED'
    elif qualification_gates_without_rare and not rare_floor:
        classification = 'LIZARD_MECHANICAL_Q_NATIVE_QUALIFICATION_INCONCLUSIVE_RARE_EVENT'
    else:
        classification = 'ACTIVE_LIZARD_MECHANICAL_Q_LEARNED_R_T2_NATIVE_REJECTED'
    hard_name = next((name for name in cohort_names if name.startswith('HARD')), None)
    hard_clear_degradation = False
    if hard_name:
        hard_primary = cohort_results[hard_name]['threeClassCandidateVsB1']
        hard_clear_degradation = any(
            result.get('sourceBootstrap95CI') is not None
            and result['sourceBootstrap95CI'][0] > 0.0
            for result in hard_primary.values() if isinstance(result, dict))
    pooled_nll = pooled_primary_scores.get('threeClassNll', {})
    pooled_brier = pooled_primary_scores.get('multiclassBrier', {})
    screen_pass = (
        pooled_nll.get('meanCandidateMinusB1') is not None
        and pooled_nll['meanCandidateMinusB1'] < 0.0
        and pooled_brier.get('meanCandidateMinusB1') is not None
        and pooled_brier['meanCandidateMinusB1'] <= 0.0
        and not hard_clear_degradation and not broad_clear_degradation
        and all_q_parity and support['exactSupportRows'] == len(pairs))
    transfer_assessment = None
    if purpose == 'native_teacher_transfer':
        primary_results = [cohort_results[name]['threeClassCandidateVsB1']
                           for name in cohort_names + ['POOLED']]
        clear_primary_regression = any(
            _has_clear_positive_delta([result.get(metric)])
            for result in primary_results
            for metric in ('threeClassNll', 'multiclassBrier'))
        r_comparison = r_result['comparisonOnB1ScoreableConsumedRows']
        clear_r_regression = any(
            _has_clear_positive_delta([r_comparison.get(metric)])
            for metric in ('nll', 'brier'))
        pooled_t2 = hp_by_cohort['POOLED']
        t2_delta = pooled_t2['pairedSourceBootstrapT2MinusT0']
        clear_t2_regression = any(
            _has_clear_positive_delta([t2_delta.get(metric)])
            for metric in ('hpNll', 'hpCrps', 'expectedHpAbsError',
                           'maxHpNll', 'potionMaskNll')) or any(
            _has_clear_positive_delta([result])
            for result in t2_delta.get('supportedRelicGroupConstraintNllByGroup', {}).values())
        t2_domain_clean = (
            pooled_t2['T2']['unscoreableBecauseTransformedTargetOutsideModelDomain'] == 0
            and not pooled_t2['T2']['unscoredReasons']
            and all(value == pooled_t2['T2']['candidateRows']
                    for value in pooled_t2['T2ScoredRowsByMetric'].values()))
        exact_transfer_states = (transfer_agreement is not None
                                 and transfer_agreement['exactPrecombatStateRows'] == len(pairs)
                                 and transfer_agreement['stateMismatchRows'] == 0)
        clear_regression = clear_primary_regression or clear_r_regression or clear_t2_regression
        transfer_pass = bool(
            exact_transfer_states
            and support['exactSupportRows'] == len(pairs)
            and all_q_parity
            and pooled_primary['allRowsB1Scoreable']
            and r_result['allConsumedRowsB1Scoreable']
            and t2_domain_clean
            and not clear_regression)
        transfer_assessment = {
            'decision': 'PROCEED_TO_FRESH_NATIVE_QUALIFICATION' if transfer_pass else 'STOP',
            'pass': transfer_pass,
            'exactArchivedPrecombatStates': exact_transfer_states,
            'exactStateRows': (transfer_agreement['exactPrecombatStateRows']
                               if transfer_agreement else 0),
            'expectedStateRows': len(pairs),
            'exactSupportEveryPair': support['exactSupportRows'] == len(pairs),
            'mechanicalQParityEveryRow': all_q_parity,
            'allPrimaryRowsB1Scoreable': pooled_primary['allRowsB1Scoreable'],
            'allConsumedRowsB1Scoreable': r_result['allConsumedRowsB1Scoreable'],
            'T2ZeroUnscoredOrDomainInvalidRows': t2_domain_clean,
            'clearCandidateRegression': clear_primary_regression,
            'clearLearnedRRegression': clear_r_regression,
            'clearT2Regression': clear_t2_regression,
            'clearRegressionRule': (
                'stop if any source-bootstrap 95% CI lower bound for candidate-vs-B1 '
                'three-class NLL/Brier in pooled/HARD/BROAD, learned-r NLL/Brier, or '
                'T2 HP/expected-HP/downstream metrics is above zero'),
            'retainedWinWarningsAreDiagnosticOnly': True,
        }
    if purpose == 'fresh_qualification':
        if (len(pairs) != 320 or len(cohorts.get('HARD288', [])) != 288
                or len(cohorts.get('BROAD32', [])) != 32
                or selection.get('stateSelection') != candidate_model.STATE_SELECTION):
            raise ValueError('fresh native qualification differs from the frozen HARD288/BROAD32 assignment')
    pair_manifest_sha = sha256(manifest_path)
    pair_data_path = pilot._resolve_manifest_file(manifest['jsonl']['path'], manifest_path.parent)
    pair_data_sha = sha256(pair_data_path)
    summary = {
        'schema': SCHEMA,
        'purpose': purpose,
        'classification': (
            classification if purpose == 'fresh_qualification' else
            'VENDORED_TO_NATIVE_LIZARD_TEACHER_TRANSFER_DIAGNOSTIC'
            if purpose == 'native_teacher_transfer' else 'DEVELOPMENT_SCREEN_ONLY'),
        'screenDecision': (
            'PROCEED_TO_NATIVE_TEACHER_TRANSFER' if purpose == 'existing_data_screen' and screen_pass else
            'STOP' if purpose == 'existing_data_screen' else
            transfer_assessment['decision'] if purpose == 'native_teacher_transfer' else
            'CLASSIFICATION_COMPLETE'),
        'candidate': {
            'candidateId': candidate['candidateId'],
            'candidateManifestSha256': candidate_sha,
            'qMode': candidate['qMode'], 'rMode': candidate['rMode'],
            'rArtifactSha256': candidate['rArtifact']['sha256'],
            'rModelSha256': candidate['rArtifact']['rModelSha256'],
            'rPredictorAstSha256': candidate['rPredictorAstSha256'],
            'treatment': candidate['treatment'], 't2Rule': candidate['t2Rule'],
            'frozenCtmComponentHashes': candidate['frozenCtmComponentHashes'],
            'silverTeacher': candidate['silverTeacher'],
        },
        'input': {
            'baselineGitSha': manifest['baselineGitSha'],
            'pairManifestSha256': pair_manifest_sha,
            'pairJsonlSha256': pair_data_sha,
            'targetSelectionSha256': manifest['targetSelection']['sha256'],
            'sourceAssignmentSha256': assignment_sha,
            'sourceAssignment': assignment,
            'sourceAssignmentCohorts': cohorts,
            'teacherId': manifest['combatTeacher']['teacher_id'],
            'teacherManifestSha256': manifest['combatTeacherManifestSha256'],
            'nativeTeacherFileSha256': native_teacher_sha,
            'pairProducerGitSha': manifest['producerGitSha'],
            'pairProducerExecutableSha256': manifest['producerExecutableSha256'],
            'pairSeedSpec': manifest['seedSpec'],
        },
        'analysisProtocol': {
            'bootstrapReplicates': BOOTSTRAP_REPS,
            'bootstrapSeed': BOOTSTRAP_SEED,
            'bootstrapUnit': 'sourceSeed; all rows from a sampled source remain together',
            'b1NegativeReserveDifferenceScoringEpsilon': FLOAT32_EPSILON,
            'calibration': '10 equal-width bins',
            'teacherBoundary': (
                'Native transfer metrics use only native rows; archived vendored rows are joined by exact source/state for descriptive agreement tables only. '
                'No cross-teacher pooling or bootstrap is performed.'),
        },
        'supportAudit': support,
        'nativeTeacherTransferAgreement': transfer_agreement,
        'nativeTeacherTransferAssessment': transfer_assessment,
        'b1Coherence': {
            'float32ScoringEpsilon': FLOAT32_EPSILON,
            'counts': dict(sorted(b1_kinds.items())),
            'negativeRawDifferences': b1_negative,
        },
        'pairedArmOutcomeCounts': {
            arm: dict(Counter('WIN' if int(pair[arm]['transition']['combatOutcome']) == pilot.WIN
                              else 'LOSS' for pair in pairs))
            for arm in ('noTail', 'activeTail')
        },
        'threeClassCountsByCohort': {
            name: result['classCounts'] for name, result in cohort_results.items()},
        'primaryCandidateVsB1ByCohort': {
            name: result['threeClassCandidateVsB1'] for name, result in cohort_results.items()},
        'qParityAndCalibrationByCohort': {
            name: result['qConsumption'] for name, result in cohort_results.items()},
        'rConditionalMetricsByCohort': {
            name: result['rConditionalRescue'] for name, result in cohort_results.items()},
        't2ByCohort': hp_by_cohort,
        'retainedWinT0ByCohort': retained_by_cohort,
        'rareEventFloor': {
            'requiredLossConsumed': 20, 'requiredDistinctLossSources': 10,
            'requiredConsumedRows': 20, 'observedLossConsumed': loss_count,
            'observedDistinctLossSources': loss_sources, 'observedConsumedRows': consumed_count,
            'passed': rare_floor,
        },
        'gates': {
            'qParityEveryScoreableRow': q_gate,
            'primaryThreeClass': primary_gate,
            'learnedR': r_nonrare_gate,
            'rareEventFloor': rare_floor,
            'T2': all(t2_gate.values()),
            'exactSupportEveryPair': support['exactSupportRows'] == len(pairs),
            'broadClearDegradation': broad_clear_degradation,
            'hardClearDegradation': hard_clear_degradation,
        },
        'finalClassification': classification if purpose == 'fresh_qualification' else None,
        'claimBoundary': (
            'This is a development screen.' if purpose == 'existing_data_screen' else
            'No runtime support was integrated; production remains active_unqualified_lizard.'),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--candidate-sha256')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--purpose', choices=(
        'existing_data_screen', 'native_teacher_transfer', 'fresh_qualification'), required=True)
    parser.add_argument('--archived-manifest', type=Path)
    parser.add_argument('--native-teacher', type=Path)
    args = parser.parse_args()
    result = _analyze(args.manifest, args.candidate, args.candidate_sha256,
                      args.output, purpose=args.purpose,
                      archived_manifest_path=args.archived_manifest,
                      native_teacher_path=args.native_teacher)
    print(json.dumps({
        'purpose': result['purpose'],
        'screenDecision': result['screenDecision'],
        'finalClassification': result['finalClassification'],
        'nativeTeacherTransferAssessment': result['nativeTeacherTransferAssessment'],
        'threeClassCountsByCohort': result['threeClassCountsByCohort'],
        'gates': result['gates'],
    }, indent=2))


if __name__ == '__main__':
    main()
