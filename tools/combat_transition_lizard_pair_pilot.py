#!/usr/bin/env python3
"""Validate and descriptively analyze a matched active-Lizard pilot.

This is a screen only: it never fits a model or changes runtime support.
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
from tools.combat_transition_contract import (
    ROW_SCHEMA_VERSION, SCHEMA_VERSION, sha256, validate_state,
)
from tools.combat_predictor_input_contract import (
    FIELD_SCHEMA_HASH, SCHEMA_VERSION as PREDICTOR_SCHEMA, validate_predictor_input,
)
from tools.ooc_pipeline_contract import validate_teacher

LIZARD_TAIL_ID = 35
WIN, DEATH = 1, 2


def _lizard_data(relics, *, required):
    found = [r['data'] for r in relics if int(r['id']) == LIZARD_TAIL_ID]
    if len(found) > 1 or (required and len(found) != 1):
        raise ValueError('invalid Lizard Tail multiplicity')
    return found[0] if found else None


def _strip_lizard(state):
    relic_bits = list(state['relicBits'])
    bit_word, bit_offset = divmod(LIZARD_TAIL_ID, 64)
    relic_bits[bit_word] = int(relic_bits[bit_word]) & ~(1 << bit_offset)
    return {
        **state,
        'relics': [r for r in state['relics'] if int(r['id']) != LIZARD_TAIL_ID],
        'relicBits': relic_bits,
    }


def _strip_lizard_input(value):
    return {**value, 'relics': [r for r in value['relics'] if int(r['relicId']) != LIZARD_TAIL_ID]}


def _resolve_manifest_file(raw_path: str, manifest_dir: Path) -> Path:
    """Resolve archived absolute paths against this packet when files moved.

    The content hash is still checked by the caller. Relative paths are
    confined to the packet so a copied manifest cannot escape its evidence
    directory.
    """
    path = Path(raw_path)
    root = manifest_dir.resolve()
    if path.is_absolute():
        if path.is_file():
            return path
        sibling = root / path.name
    else:
        resolved = (root / path).resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError(f'relative manifest artifact escapes packet: {raw_path}')
        if resolved.is_file():
            return resolved
        sibling = root / path.name
    if sibling.is_file():
        return sibling
    raise ValueError(f'manifest artifact missing: {raw_path}')


def _validate_historical_teacher(manifest: dict, expected: dict) -> None:
    """Pin a read-only historical cohort to its original retired teacher.

    This path is for archived analysis only. It does not make retired teacher
    manifests valid for new collection; fresh collection uses validate_teacher.
    """
    teacher = manifest.get('combatTeacher', {})
    if (teacher.get('combat_backend') != 'silver_uct'
            or teacher != expected.get('provenance')
            or teacher.get('teacher_id') != expected.get('identity')
            or manifest.get('combatTeacherManifestSha256') != expected.get('manifestSha256')):
        raise ValueError('historical teacher differs from the explicitly pinned frozen provenance')


def validate_pair_corpus(manifest_path: Path, *, historical_teacher: dict | None = None):
    manifest = json.loads(manifest_path.read_text())
    required = {
        'schema', 'rowSchemaVersion', 'predictorInputSchemaVersion',
        'predictorInputFieldSchemaHash', 'format', 'producerGitSha',
        'producerExecutableSha256', 'baselineGitSha', 'combatTeacher',
        'combatTeacherManifestSha256', 'seedSpec', 'jsonl', 'integrity', 'protocol',
    }
    direct_snapshot = manifest.get('schema') == 'lizard_tail_direct_snapshot_paired_transition_diagnostic_v1'
    targeted = manifest.get('schema') in (
        'lizard_tail_targeted_paired_transition_pilot_v1',
        'lizard_tail_direct_snapshot_paired_transition_diagnostic_v1')
    targeted_keys = {'targetSelection', 'sourceSeeds'} if targeted else set()
    if direct_snapshot:
        targeted_keys.add('directReplayPlan')
    expected_keys = required | targeted_keys
    if (set(manifest) != expected_keys or manifest['schema'] not in (
            'lizard_tail_paired_transition_pilot_v1',
            'lizard_tail_targeted_paired_transition_pilot_v1',
            'lizard_tail_direct_snapshot_paired_transition_diagnostic_v1')):
        raise ValueError('paired pilot manifest keys/schema mismatch')
    if manifest['rowSchemaVersion'] != ROW_SCHEMA_VERSION or manifest['predictorInputSchemaVersion'] != PREDICTOR_SCHEMA:
        raise ValueError('paired pilot transition schema mismatch')
    if manifest['predictorInputFieldSchemaHash'] != FIELD_SCHEMA_HASH or manifest['format'] != 'jsonl':
        raise ValueError('paired pilot predictor schema/format mismatch')
    for key, length in (('producerGitSha', 40), ('producerExecutableSha256', 64),
                        ('baselineGitSha', 40), ('combatTeacherManifestSha256', 64)):
        value = manifest[key]
        if not isinstance(value, str) or len(value) != length or any(c not in '0123456789abcdef' for c in value):
            raise ValueError(f'invalid {key}')
    teacher = manifest['combatTeacher']
    if historical_teacher is None:
        validate_teacher(teacher)
    else:
        _validate_historical_teacher(manifest, historical_teacher)
    if not isinstance(teacher.get('teacher_id'), str) or not teacher['teacher_id']:
        raise ValueError('paired pilot is missing its exact-10k combat teacher identity')
    targets = None
    if targeted:
        target_file = _resolve_manifest_file(
            manifest['targetSelection']['path'], manifest_path.parent)
        if sha256(target_file) != manifest['targetSelection']['sha256']:
            raise ValueError('target-selection file missing or hash mismatch')
        targets = json.loads(target_file.read_text())
        if (targets.get('schema') != 'lizard_tail_risk_target_selection_v1'
                or not isinstance(targets.get('targets'), list)
                or (not direct_snapshot
                    and len(targets.get('targets', [])) != int(manifest['seedSpec']['count']))
                or (direct_snapshot and len(targets.get('targets', [])) != 128)):
            raise ValueError('invalid risk target selection file')
    if direct_snapshot:
        replay_plan_file = _resolve_manifest_file(
            manifest['directReplayPlan']['path'], manifest_path.parent)
        if sha256(replay_plan_file) != manifest['directReplayPlan'].get('sha256'):
            raise ValueError('direct replay plan missing or hash mismatch')
        replay_plan = json.loads(replay_plan_file.read_text())
        if (replay_plan.get('schema') != 'lizard_tail_direct_snapshot_replay_plan_v1'
                or replay_plan.get('replayMode') != 'persistent_snapshot_direct'
                or replay_plan.get('archivedTargetSelection', {}).get('sha256')
                    != manifest['targetSelection']['sha256']):
            raise ValueError('direct replay plan does not bind the target selection')
        if (manifest['baselineGitSha'] != replay_plan.get('baselineGitSha')
                or manifest['producerGitSha'] != replay_plan.get('collectorGitSha')
                or manifest['producerExecutableSha256']
                    != replay_plan.get('collectorExecutableSha256')):
            raise ValueError('direct replay producer differs from the frozen plan')
        teacher_plan = replay_plan.get('nativeTeacherManifest', {})
        teacher_file = _resolve_manifest_file(teacher_plan.get('path', ''), replay_plan_file.parent)
        if (sha256(teacher_file) != teacher_plan.get('sha256')
                or teacher_plan.get('identity') != teacher.get('teacher_id')
                or json.loads(teacher_file.read_text()) != teacher
                or teacher.get('git_sha') != replay_plan.get('collectorGitSha')
                or teacher.get('executable_sha256') != replay_plan.get('collectorExecutableSha256')
                or teacher.get('environment') != replay_plan.get('executionEnvironment')):
            raise ValueError('direct replay native teacher differs from the frozen plan')
        selection_ref = Path(replay_plan['archivedTargetSelection']['path'])
        if selection_ref.is_relative():
            selection_ref = replay_plan_file.parent / selection_ref
        selection_ref = selection_ref.resolve()
        packet_root = manifest_path.parent.parent.resolve()
        if (packet_root not in selection_ref.parents or not selection_ref.is_file()
                or sha256(selection_ref) != manifest['targetSelection']['sha256']):
            raise ValueError('direct replay plan does not resolve to the canonical archived selection')
        expected_excluded = {
            (4201016, 12), (4201026, 5), (4201030, 12), (4201031, 20),
            (4201055, 20), (4201070, 4), (4201089, 16), (4201103, 14),
            (4201113, 6),
        }
        actual_excluded = {
            (int(row['sourceSeed']), int(row['fightIdx']))
            for row in replay_plan.get('excludedBurningEliteTargets', [])}
        manifest_excluded = {
            (int(row['sourceSeed']), int(row['fightIdx']))
            for row in manifest['directReplayPlan'].get('excludedBurningEliteTargets', [])}
        if actual_excluded != expected_excluded or manifest_excluded != expected_excluded:
            raise ValueError('direct replay exclusions differ from the preregistered burning-elite identities')
        targets_by_key = {
            (int(row['sourceSeed']), int(row['fightIdx'])): row
            for row in targets['targets']}
        if len(targets_by_key) != 128 or any(
                key not in targets_by_key
                or not targets_by_key[key]['predictorInput']['globals']['isBurningElite']
                for key in expected_excluded):
            raise ValueError('direct replay exclusions are not the exact archived burning-elite targets')
        if any(row['predictorInput']['globals']['isBurningElite']
               for key, row in targets_by_key.items() if key not in expected_excluded):
            raise ValueError('unregistered burning-elite target in direct replay selection')
    selected_state_policy = (
        'direct_archived_snapshot_replay_nonburning_subset_v1' if direct_snapshot else
        targets.get('stateSelection', 'preoutcome_ctm_death_risk_bands') if targeted else None)
    if targeted and selected_state_policy not in (
            'preoutcome_ctm_death_risk_bands',
            'predeclared_qr_hard96_broad32_hash_v1',
            'predeclared_mechanical_q_hard288_broad32_hash_v1',
            'direct_archived_snapshot_replay_nonburning_subset_v1'):
        raise ValueError('unsupported targeted state-selection policy')
    protocol = {
        'samePrecombatContext': True, 'sameSilverSearchRngSeed': True,
        'ordinaryBranchLizard': 'absent', 'interventionBranchLizard': 'active_data_1',
        'stateSelection': (selected_state_policy if targeted
                           else 'uniform_reservoir_without_outcome_filter'),
        'markOfBloom': 'eligible_states_excluded', 'sourceTrajectory': (
            'not_replayed_direct_snapshot' if direct_snapshot else 'untouched_normal_policy'),
    }
    if manifest['protocol'] != protocol:
        raise ValueError('paired pilot protocol mismatch')
    target_by_seed = ({int(row['sourceSeed']): row for row in targets['targets']}
                      if targeted else {})
    selected_by_seed = ({int(seed): target_by_seed.get(int(seed))
                         for seed in manifest.get('sourceSeeds', [])} if targeted else {})
    if targeted and any(target is None for target in selected_by_seed.values()):
        raise ValueError('targeted pair source is absent from frozen target selection')
    if direct_snapshot:
        excluded = {
            (int(row['sourceSeed']), int(row['fightIdx']))
            for row in manifest['directReplayPlan']['excludedBurningEliteTargets']}
        expected_seeds = sorted({int(row['sourceSeed']) for row in targets['targets']}
                                - {seed for seed, _ in excluded})
        if manifest['sourceSeeds'] != expected_seeds:
            raise ValueError('direct replay source list is not the exact non-burning archive subset')
    seed_spec = manifest['seedSpec']
    if not isinstance(seed_spec, dict) or set(seed_spec) != {'start', 'count'}:
        raise ValueError('invalid seedSpec')
    start, count = int(seed_spec['start']), int(seed_spec['count'])
    source_seeds = manifest.get('sourceSeeds') if targeted else list(range(start, start + count))
    if targeted and (not isinstance(source_seeds, list) or len(source_seeds) != count
                     or source_seeds != sorted(set(source_seeds))):
        raise ValueError('targeted source seed list invalid')
    integrity = manifest['integrity']
    if integrity != {'requestedSeeds': count, 'completedSeeds': count,
                     'quarantinedSeeds': 0, 'pairs': count}:
        raise ValueError('pilot has missing/quarantined pair seeds')
    corpus_path = _resolve_manifest_file(manifest['jsonl']['path'], manifest_path.parent)
    if sha256(corpus_path) != manifest['jsonl'].get('sha256'):
        raise ValueError('paired JSONL missing or hash mismatch')

    rows = [json.loads(line) for line in corpus_path.read_text().splitlines() if line]
    if len(rows) != count:
        raise ValueError('paired row count differs from seed count')
    seen = set()
    for index, pair in enumerate(rows):
        if set(pair) != {'pair', 'noTail', 'activeTail'}:
            raise ValueError(f'pair row {index} keys mismatch')
        meta = pair['pair']
        seed = int(source_seeds[index])
        if int(meta.get('sourceSeed', -1)) != seed or seed in seen:
            raise ValueError('pair seeds are missing, duplicated, or out of order')
        seen.add(seed)
        eligible = int(meta.get('eligibleBattlesInSource', 0))
        ordinal = int(meta.get('selectedEligibleOrdinal', 0))
        if direct_snapshot:
            if (meta.get('replayMode') != 'direct_archived_snapshot'
                    or eligible != 0 or ordinal != 0
                    or int(meta.get('fightIdx', -1)) < 0):
                raise ValueError('invalid direct snapshot replay metadata')
        elif eligible < 1 or not 1 <= ordinal <= eligible or int(meta.get('fightIdx', -1)) < 0:
            raise ValueError('invalid selected fight metadata')
        target = selected_by_seed.get(seed) if targeted else None
        if targeted and (
                int(target['sourceSeed']) != seed
                or int(target['fightIdx']) != int(meta['fightIdx'])
                or target['riskBand'] != meta.get('targetRiskBand')
                or abs(float(target['pDeath']) - float(meta.get('targetPDeath', -1))) > 1e-12):
            raise ValueError('pair does not match its pre-outcome risk target')
        left, right = pair['noTail'], pair['activeTail']
        for side, row in (('noTail', left), ('activeTail', right)):
            if (row.get('schemaVersion') != SCHEMA_VERSION or row.get('rowSchemaVersion') != ROW_SCHEMA_VERSION
                    or row.get('teacherId') != teacher['teacher_id'] or row.get('runValid') is not True
                    or row.get('captureCount') != 1 or row.get('captureStatus') != 'exactly_one'
                    or row.get('quarantineReason') != '' or not isinstance(row.get('transition'), dict)):
                raise ValueError(f'invalid {side} transition row at pair {index}')
            if int(row['sourceSeed']) != seed or int(row['fightIdx']) != int(meta['fightIdx']):
                raise ValueError(f'{side} row identity mismatch at pair {index}')
            validate_predictor_input(row['predictorInput'])
            validate_state(row['transition']['pre'], f'{side}.pre')
            validate_state(row['transition']['post'], f'{side}.post')
        if _lizard_data(left['transition']['pre']['relics'], required=False) is not None:
            raise ValueError('ordinary paired state already owns Lizard Tail')
        if _lizard_data(right['transition']['pre']['relics'], required=True) != 1:
            raise ValueError('intervention Lizard is not active before combat')
        bloom_id = composed.base._RELIC_IDS['MARK_OF_THE_BLOOM']
        if (any(int(r['id']) == bloom_id for r in left['transition']['pre']['relics'])
                or any(int(r['id']) == bloom_id for r in right['transition']['pre']['relics'])
                or any(int(r['relicId']) == bloom_id for r in left['predictorInput']['relics'])
                or any(int(r['relicId']) == bloom_id for r in right['predictorInput']['relics'])):
            raise ValueError('Mark of the Bloom contaminated a paired intervention')
        if _strip_lizard(left['transition']['pre']) != _strip_lizard(right['transition']['pre']):
            raise ValueError('paired persistent pre-states differ beyond injected Tail')
        if _strip_lizard_input(left['predictorInput']) != _strip_lizard_input(right['predictorInput']):
            raise ValueError('paired predictor inputs differ beyond injected Tail')
        if targeted:
            if left['predictorInput'] != target['predictorInput']:
                raise ValueError('selected ordinary precombat input differs from risk-scored candidate')
            digest_input = json.dumps(left['predictorInput'], sort_keys=True, separators=(',', ':'))
            if hashlib.sha256(digest_input.encode('utf-8')).hexdigest() != target['predictorInputSha256']:
                raise ValueError('selected candidate input hash mismatch')
            digest_state = json.dumps(left['transition']['pre'], sort_keys=True, separators=(',', ':'))
            if (left['transition']['pre'] != target['preState']
                    or hashlib.sha256(digest_state.encode('utf-8')).hexdigest() != target['preStateSha256']):
                raise ValueError('selected candidate full pre-state mismatch')
            for side, row in (('noTail', left), ('activeTail', right)):
                trace = row.get('silverActionTraceBits')
                first = row.get('silverFirstActionBits')
                if (not isinstance(trace, list) or not trace
                        or any(type(action) is not int or not 0 <= action <= 0xffffffff for action in trace)
                        or first != trace[0]):
                    raise ValueError(f'missing/invalid committed {side} Silver action trace')
        if int(left['transition']['combatOutcome']) not in (WIN, DEATH) or int(right['transition']['combatOutcome']) not in (WIN, DEATH):
            raise ValueError('paired outcome is not a decided combat transition')
        post_data = _lizard_data(right['transition']['post']['relics'], required=True)
        if post_data not in (0, 1) or meta.get('activeTailPostData') != post_data:
            raise ValueError('active Tail post-state disagrees with pair metadata')
        try:
            fingerprint = json.loads(meta['sourceStateFingerprint'])
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError('missing normalized source-state fingerprint') from error
        if fingerprint != left['transition']['pre']:
            raise ValueError('normalized source-state fingerprint does not bind ordinary pre-state')
    return manifest, rows


def conditional_head_screen(pairs, models, *, tail_consumed=None, arm='activeTail'):
    """Score existing heads on active wins using the paired ordinary input."""
    from tools import combat_transition_composed_evaluate as evaluate

    candidates = [pair for pair in pairs
                  if int(pair[arm]['transition']['combatOutcome']) == WIN
                  and (tail_consumed is None
                       or (int(pair['pair']['activeTailPostData']) == 0) == tail_consumed)]
    scores = {'maxHpNll': [], 'maxHpModeCorrect': [], 'hpNll': [], 'expectedHpAbsError': [],
              'potionMaskNll': [], 'potionMaskModeCorrect': []}
    relic_scores = {group: [] for group in models.trained_groups}
    failures = Counter()
    pair_scores = []
    torch = models.torch
    for pair in candidates:
        row = pair[arm]
        ordinary = pair['noTail']
        pre = ordinary['transition']['pre']
        post = _strip_lizard(row['transition']['post'])
        predictor_input = ordinary['predictorInput']
        try:
            reasons = composed.full_support_reasons(pre, predictor_input, models)
            if reasons:
                failures['unsupported:' + ','.join(reasons)] += 1
                continue
            inputs = models.encode_visible(predictor_input)
            arrays = composed.visible_arrays(predictor_input)
            delta = int(post['maxHp']) - int(pre['maxHp'])
            delta_index = {int(v): i for i, v in enumerate(models.delta_values)}.get(delta)
            if delta_index is None:
                raise ValueError('maxHP delta outside frozen class domain')
            with torch.inference_mode():
                p_delta = evaluate.probabilities(models.max_net.max_hp_delta(
                    models.fp32_encoding(models.max_net.encoder, inputs)))[0]
                z = models.hp_encoding(inputs).cpu().numpy()
                pre_hp, maximum, ending = int(pre['curHp']), int(post['maxHp']), int(post['curHp'])
                signed_value = ending - pre_hp
                hp_target = signed_value - int(models.classes[0])
                if not 0 <= hp_target < len(models.classes):
                    raise ValueError('winning HP transition outside frozen class domain')
                p_hp = evaluate.hp_prob(models, z, np.asarray([delta_index]),
                                        np.asarray([pre_hp]), np.asarray([maximum]))[0]
                hp_expected = pre_hp + float(np.dot(p_hp, models.classes))
                potion_z = models.fp32_encoding(models.potion_encoder.encoder, inputs).cpu().numpy()
                capacity = int(pre['potionCapacity'])
                potion_mask = int(composed.potion.encode_masks(
                    np.asarray([pre['potions']]), np.asarray([post['potions']]),
                    np.asarray([capacity]))[0])
                slots = arrays['potions'][:, :, 1].astype(np.int64)[0]
                fraction = np.asarray([ending / maximum], dtype=np.float32)
                p_potion = evaluate.potion_prob(models, potion_z, slots[None],
                                                np.asarray([capacity]),
                                                np.asarray([delta_index]), fraction)[0]
                hp_fraction = fraction
                p_relic = evaluate.relic_prob(models, z,
                    np.asarray([hp_target], dtype=np.int64), hp_fraction,
                    np.asarray([potion_mask], dtype=np.int64))
            scores['maxHpNll'].append(-math.log(max(float(p_delta[delta_index]), 1e-300)))
            scores['maxHpModeCorrect'].append(int(int(models.delta_values[int(np.argmax(p_delta))]) == delta))
            scores['hpNll'].append(-math.log(max(float(p_hp[hp_target]), 1e-300)))
            scores['expectedHpAbsError'].append(abs(hp_expected - ending))
            scores['potionMaskNll'].append(-math.log(max(float(p_potion[potion_mask]), 1e-300)))
            scores['potionMaskModeCorrect'].append(int(int(np.argmax(p_potion)) == potion_mask))
            bloom = any(int(x['id']) == composed.base._RELIC_IDS['MARK_OF_THE_BLOOM']
                        for x in pre['relics'])
            allowed = composed.relic.trajectory_constraints(
                pre['relics'], post['relics'], predictor_input['globals']['encounter'], bloom)
            relic_row_scores = {}
            for group in models.trained_groups:
                if group in allowed and group in p_relic:
                    mass = float(np.asarray(p_relic[group])[0, list(allowed[group])].sum())
                    value = -math.log(max(mass, 1e-300))
                    relic_scores[group].append(value)
                    relic_row_scores[group] = value
            pair_scores.append({
                'sourceSeed': int(pair['pair']['sourceSeed']),
                'maxHpNll': -math.log(max(float(p_delta[delta_index]), 1e-300)),
                'hpNll': -math.log(max(float(p_hp[hp_target]), 1e-300)),
                'expectedHpAbsError': abs(hp_expected - ending),
                'potionMaskNll': -math.log(max(float(p_potion[potion_mask]), 1e-300)),
                'nonLizardRelicTrajectoryNllByGroup': relic_row_scores,
            })
        except (KeyError, ValueError, IndexError, RuntimeError) as error:
            failures[f'{type(error).__name__}:{error}'] += 1
    n = len(candidates)
    result = {
        'rows': n,
        'method': f'{arm}_teacher_forced_on_ordinary_precombat_input; descriptive only; no qualification gate applied',
        'scoredRows': {name: len(values) for name, values in scores.items()},
        'metrics': {name: (float(np.mean(values)) if values else None) for name, values in scores.items()},
        'perPairScores': pair_scores,
        'nonLizardRelicTrajectoryNllByGroup': {
            name: {'rows': len(values), 'meanNll': (float(np.mean(values)) if values else None)}
            for name, values in relic_scores.items()},
        'unscoredReasons': dict(sorted(failures.items())),
    }
    return result


def _action_trace_summary(pairs):
    if any('silverActionTraceBits' not in pair['noTail']
           or 'silverActionTraceBits' not in pair['activeTail'] for pair in pairs):
        return {'status': 'not_recorded_in_pilot_corpus', 'pairs': len(pairs)}
    per_pair = []
    for pair in pairs:
        left = [int(value) for value in pair['noTail']['silverActionTraceBits']]
        right = [int(value) for value in pair['activeTail']['silverActionTraceBits']]
        left_digest = hashlib.sha256(','.join(f'{value:08x}' for value in left).encode()).hexdigest()
        right_digest = hashlib.sha256(','.join(f'{value:08x}' for value in right).encode()).hexdigest()
        common = 0
        for a, b in zip(left, right):
            if a != b:
                break
            common += 1
        per_pair.append({
            'seed': int(pair['pair']['sourceSeed']),
            'tailConsumed': int(pair['pair']['activeTailPostData']) == 0,
            'activeTailWon': int(pair['pair']['activeTailOutcome']) == WIN,
            'noTailFirstActionBits': (left[0] if left else None),
            'activeTailFirstActionBits': (right[0] if right else None),
            'noTailTraceSha256': left_digest,
            'activeTailTraceSha256': right_digest,
            'firstActionEqual': bool(left and right and left[0] == right[0]),
            'fullTraceEqual': left == right,
            'commonPrefixActions': common,
            'shorterTraceActions': min(len(left), len(right)),
        })

    def summarize(rows):
        n = len(rows)
        return {
            'pairs': n,
            'firstActionChanged': sum(not row['firstActionEqual'] for row in rows),
            'firstActionChangeRate': (sum(not row['firstActionEqual'] for row in rows) / n if n else None),
            'fullTraceChanged': sum(not row['fullTraceEqual'] for row in rows),
            'fullTraceChangeRate': (sum(not row['fullTraceEqual'] for row in rows) / n if n else None),
            'meanCommonPrefixActions': (float(np.mean([row['commonPrefixActions'] for row in rows])) if n else None),
            'meanShorterTraceActions': (float(np.mean([row['shorterTraceActions'] for row in rows])) if n else None),
        }

    retained_wins = [row for row in per_pair if row['activeTailWon'] and not row['tailConsumed']]
    return {
        'allPairs': summarize(per_pair),
        'activeTailWinsWithTailRetained': summarize(retained_wins),
        'perSourcePair': per_pair,
    }


def _paired_retained_head_deltas(control, treatment, *, seed=20260924, reps=2000):
    """Paired head-score deltas for retained-Tail wins won by both arms."""
    control_rows = {row['sourceSeed']: row for row in control['perPairScores']}
    treatment_rows = {row['sourceSeed']: row for row in treatment['perPairScores']}
    shared = sorted(set(control_rows) & set(treatment_rows))
    fields = ('maxHpNll', 'hpNll', 'expectedHpAbsError', 'potionMaskNll')
    deltas = {}
    rng = np.random.default_rng(seed)
    for field in fields:
        values = np.asarray([treatment_rows[source][field] - control_rows[source][field]
                             for source in shared], dtype=np.float64)
        if len(values):
            boot = np.mean(values[rng.integers(0, len(values), size=(reps, len(values)))], axis=1)
            deltas[field] = {
                'pairs': len(values), 'meanTreatmentMinusControl': float(values.mean()),
                'sourceBootstrap95CI': [float(np.quantile(boot, .025)),
                                         float(np.quantile(boot, .975))],
            }
        else:
            deltas[field] = {'pairs': 0, 'meanTreatmentMinusControl': None,
                             'sourceBootstrap95CI': None}
    groups = set()
    for source in shared:
        groups.update(control_rows[source]['nonLizardRelicTrajectoryNllByGroup'])
        groups.update(treatment_rows[source]['nonLizardRelicTrajectoryNllByGroup'])
    relic = {}
    for group in sorted(groups):
        values = [treatment_rows[source]['nonLizardRelicTrajectoryNllByGroup'][group]
                  - control_rows[source]['nonLizardRelicTrajectoryNllByGroup'][group]
                  for source in shared
                  if group in control_rows[source]['nonLizardRelicTrajectoryNllByGroup']
                  and group in treatment_rows[source]['nonLizardRelicTrajectoryNllByGroup']]
        values = np.asarray(values, dtype=np.float64)
        if len(values):
            boot = np.mean(values[rng.integers(0, len(values), size=(reps, len(values)))], axis=1)
            relic[group] = {
                'pairs': len(values), 'meanTreatmentMinusControl': float(values.mean()),
                'sourceBootstrap95CI': [float(np.quantile(boot, .025)),
                                         float(np.quantile(boot, .975))],
            }
        else:
            relic[group] = {'pairs': 0, 'meanTreatmentMinusControl': None,
                            'sourceBootstrap95CI': None}
    return {
        'eligibleBothArmWinsWithTailRetained': len(shared),
        'method': f'{reps} paired source bootstrap draws; exploratory, not a qualification gate',
        'metrics': deltas,
        'nonLizardRelicTrajectoryNllByGroup': relic,
    }


def analyze(manifest_path: Path, output_path: Path):
    manifest, rows = validate_pair_corpus(manifest_path)
    import torch
    torch.set_num_threads(4)
    models = composed.FrozenModels('cuda' if torch.cuda.is_available() else 'cpu')
    p_death, tail_consumed, ordinary_death = [], [], []
    p_win_shifted, active_wins = [], []
    band_rows = defaultdict(lambda: {'pDeath': [], 'controlDeath': [], 'tailWin': [], 'tailConsumed': []})
    states = Counter()
    death_pairs = 0
    tail_rescues = 0
    any_treatment_rescues = 0
    fairy_first = 0
    consumed_wins = 0
    for pair in rows:
        left, right = pair['noTail'], pair['activeTail']
        control_input = left['predictorInput']
        p_win = models.survival(models.encode_visible(control_input))
        p_death.append(1.0 - p_win)
        ordinary_outcome = int(left['transition']['combatOutcome'])
        active_outcome = int(right['transition']['combatOutcome'])
        pre_hp = int(left['transition']['pre']['curHp'])
        max_hp = int(left['transition']['pre']['maxHp'])
        reserve = max_hp // 2
        shifted_input = json.loads(json.dumps(control_input))
        shifted_input['globals']['curHp'] = min(max_hp, pre_hp + reserve)
        p_win_shifted.append(models.survival(models.encode_visible(shifted_input)))
        active_wins.append(active_outcome == WIN)
        post_data = int(pair['pair']['activeTailPostData'])
        consumed = post_data == 0
        risk_band = pair['pair'].get('targetRiskBand', 'unstratified')
        band_rows[risk_band]['pDeath'].append(1.0 - p_win)
        band_rows[risk_band]['controlDeath'].append(ordinary_outcome == DEATH)
        band_rows[risk_band]['tailWin'].append(active_outcome == WIN)
        band_rows[risk_band]['tailConsumed'].append(consumed)
        rescued_by_tail = ordinary_outcome == DEATH and active_outcome == WIN and consumed
        active_pre_potions = set(right['transition']['pre']['potions'])
        active_post_potions = set(right['transition']['post']['potions'])
        fairy_id = composed.base._POTION_IDS['FAIRY_POTION']
        fairy_used = fairy_id in active_pre_potions and fairy_id not in active_post_potions and post_data == 1
        if ordinary_outcome == DEATH:
            death_pairs += 1
            any_treatment_rescues += active_outcome == WIN
            tail_rescues += rescued_by_tail
            fairy_first += fairy_used
        if consumed and active_outcome == WIN:
            consumed_wins += 1
        tail_consumed.append(consumed)
        ordinary_death.append(ordinary_outcome == DEATH)
        label = ('tail_rescued' if rescued_by_tail else 'fairy_first_lizard_retained' if fairy_used
                 else 'other_active_win_lizard_retained' if ordinary_outcome == DEATH and active_outcome == WIN
                 else 'tail_consumed_win' if consumed and active_outcome == WIN
                 else 'tail_consumed_death' if consumed else 'tail_unused')
        states[label] += 1
    pd = np.asarray(p_death, dtype=np.float64)
    consumed = np.asarray(tail_consumed, dtype=np.float64)
    observed_death = np.asarray(ordinary_death, dtype=np.float64)
    active_win_array = np.asarray(active_wins, dtype=np.float64)
    shifted_win = np.asarray(p_win_shifted, dtype=np.float64)
    consumed_win_screen = conditional_head_screen(rows, models, tail_consumed=True)
    retained_win_screen = conditional_head_screen(rows, models, tail_consumed=False)
    retained_control_screen = conditional_head_screen(
        rows, models, tail_consumed=False, arm='noTail')
    retained_paired_delta = _paired_retained_head_deltas(
        retained_control_screen, retained_win_screen)
    band_summary = {}
    for band, values in sorted(band_rows.items()):
        deaths = np.asarray(values['controlDeath'], dtype=np.float64)
        tail_wins = np.asarray(values['tailWin'], dtype=np.float64)
        consumption = np.asarray(values['tailConsumed'], dtype=np.float64)
        risk = np.asarray(values['pDeath'], dtype=np.float64)
        band_summary[band] = {
            'pairs': len(risk),
            'meanPredictedNoTailDeath': float(risk.mean()),
            'observedNoTailDeathRate': float(deaths.mean()),
            'noTailDeathBrier': float(np.mean((risk - deaths) ** 2)),
            'activeTailWinRate': float(tail_wins.mean()),
            'tailConsumptionRate': float(consumption.mean()),
        }
    summary = {
        'schema': ('lizard_tail_targeted_paired_pilot_analysis_v1'
                   if manifest['schema'] == 'lizard_tail_targeted_paired_transition_pilot_v1'
                   else 'lizard_tail_paired_pilot_analysis_v1'),
        'claimBoundary': 'descriptive pilot only; no training or runtime qualification',
        'sourceSeeds': ([int(value) for value in manifest.get('sourceSeeds', [])]
                        if 'sourceSeeds' in manifest else
                        [int(manifest['seedSpec']['start']), int(manifest['seedSpec']['start']) + len(rows) - 1]),
        'pairs': len(rows), 'states': dict(sorted(states.items())),
        'riskBands': band_summary,
        'noTailCTMDeathProbabilityVsObservedNoTailDeath': {
            'brier': float(np.mean((pd - observed_death) ** 2)),
            'meanPredictedDeath': float(pd.mean()), 'observedDeathRate': float(observed_death.mean()),
        },
        'noTailCTMDeathProbabilityVsObservedTailConsumption': {
            'brier': float(np.mean((pd - consumed) ** 2)),
            'meanPredictedDeath': float(pd.mean()), 'observedTailConsumptionRate': float(consumed.mean()),
        },
        'observedNoTailDeathCount': int(observed_death.sum()),
        'tailConsumedCount': int(consumed.sum()),
        'ordinaryDeathRescue': {
            'ordinaryDeathPairs': int(death_pairs),
            'activeTailWinsAmongOrdinaryDeaths': int(any_treatment_rescues),
            'lizardConsumedWinsAmongOrdinaryDeaths': int(tail_rescues),
            'fairyFirstLizardRetainedAmongOrdinaryDeaths': int(fairy_first),
            'rescueRateAnyActiveTailTreatment': (float(any_treatment_rescues / death_pairs) if death_pairs else None),
            'rescueRateByTailAmongOrdinaryDeaths': (float(tail_rescues / death_pairs) if death_pairs else None),
        },
        'mechanicalReserveProxy': {
            'definition': 'existing CTM P(win) re-scored after raising visible start HP by floor(maxHP/2), capped at maxHP; proxy only, not event-level lethal-crossing replay',
            'meanPredictedWin': float(shifted_win.mean()),
            'observedActiveTailWinRate': float(active_win_array.mean()),
            'brierVsActiveTailOutcome': float(np.mean((shifted_win - active_win_array) ** 2)),
            'noTailMeanPredictedWin': float(1.0 - pd.mean()),
            'meanPredictedWinDelta': float((shifted_win - (1.0 - pd)).mean()),
        },
        'existingConditionalHeads': {
            'inputTreatment': 'paired ordinary precombat input with Tail removed; active Tail post-state with Tail removed before relic scoring',
            'tailConsumedWins': consumed_win_screen,
            'tailRetainedWins': retained_win_screen,
            'tailRetainedBothArmWinPairedDelta': retained_paired_delta,
        },
        'silverPolicyDivergence': _action_trace_summary(rows),
        'sourceGroupedInterpretation': 'one pair per unique source seed; risk-stratified outcomes are descriptive and require source-clustered uncertainty for calibration claims',
        'frozenModelHashes': models.hashes,
        'producerGitSha': manifest['producerGitSha'],
        'producerExecutableSha256': manifest['producerExecutableSha256'],
        'teacherId': manifest['combatTeacher']['teacher_id'],
    }
    output_path.write_text(json.dumps(summary, indent=2) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(analyze(args.manifest, args.output), indent=2))


if __name__ == '__main__':
    main()
