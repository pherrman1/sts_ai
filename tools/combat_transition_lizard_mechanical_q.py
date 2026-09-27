#!/usr/bin/env python3
"""Frozen mechanical-q / learned-r Lizard Tail research candidate.

This is an offline research scorer and selector. It does not train a model or
change production CTM support. The legacy q coefficients stay in their frozen
source artifact only for provenance; no candidate path reads them.
"""
from __future__ import annotations

import argparse
import ast
import collections
import copy
import hashlib
import inspect
import json
import math
from pathlib import Path

import numpy as np

from tools import combat_transition_composed as composed
from tools import combat_transition_lizard_pair_pilot as pilot
from tools.combat_transition_contract import sha256, validate_state
from tools.combat_predictor_input_contract import validate_predictor_input
from tools.ooc_pipeline_contract import validate_teacher

CANDIDATE_SCHEMA = 'active_lizard_mechanical_q_frozen_r_t2_candidate_v1'
FROZEN_QR_SCHEMA = 'active_lizard_qr_frozen_artifact_v1'
OLD_QR_ARTIFACT_SHA256 = '9f8fb965b24fbd8da1f9600fc9ca0f243e5e9069c47067123c88e36e9f5ebcf9'
OLD_QR_HEAD_SHA = '8e93cca5ba20befb2a471a4aed49bbc6d421e5dd'
MECHANICAL_Q_MODE = 'mechanical_b1'
FROZEN_R_MODE = 'frozen_learned_r'
TREATMENT = 'T2_revive'
STATE_SELECTION = 'predeclared_mechanical_q_hard288_broad32_hash_v1'
T2_RULE = 'T2_revive: curHp = floor(maxHP/2) for WIN_CONSUMED conditional CTM heads'
B1_FLOAT32_EPSILON = 1e-6
FRESH_BASELINE_GIT_SHA = 'dd8d3c80e26c11ab32d3faee2ae4c168ab7b0001'
FRESH_SOURCE_START = 4202000
FRESH_SOURCE_COUNT = 320
FRESH_BROAD32_SALT = 'active-lizard-mechanical-q-native-fresh-broad32-sha256-2026-09-25-v1'
PRIOR_LIZARD_SOURCE_INTERVALS = (
    (4200100, 4200210),
    (4200300, 4200427),
    (4201000, 4201127),
)


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _model_predict(payload: dict, features: np.ndarray) -> np.ndarray:
    x = np.asarray(features, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    mean = np.asarray(payload['featureMean'], dtype=np.float64)
    scale = np.asarray(payload['featureScale'], dtype=np.float64)
    beta = np.asarray(payload['standardizedCoefficients'], dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != len(mean) or scale.shape != mean.shape or beta.shape != (len(mean) + 1,):
        raise ValueError('frozen q/r model feature shape mismatch')
    if (not np.isfinite(x).all() or not np.isfinite(mean).all()
            or not np.isfinite(scale).all() or not np.isfinite(beta).all() or np.any(scale <= 0)):
        raise ValueError('non-finite frozen q/r model inputs')
    design = np.column_stack((np.ones(len(x)), (x - mean) / scale))
    z = design @ beta
    return 1.0 / (1.0 + np.exp(-np.clip(z, -40, 40)))


def _predictor_ast_sha256() -> str:
    module = ast.parse(inspect.getsource(_model_predict))
    function = next(node for node in module.body
                    if isinstance(node, ast.FunctionDef) and node.name == '_model_predict')
    return hashlib.sha256(ast.dump(function, include_attributes=False).encode('utf-8')).hexdigest()


def r_predict(artifact: dict, p_reserve_win: float) -> float:
    p = float(p_reserve_win)
    if not math.isfinite(p) or not 0.0 <= p <= 1.0:
        raise ValueError('pReserveWin must be finite and in [0,1]')
    return float(_model_predict(artifact['rModel'], np.asarray([[p]], dtype=np.float64))[0])


def predict(p_ordinary_win: float, p_reserve_win: float, artifact: dict) -> tuple[float, float, list[float]]:
    """Return mechanical q, frozen learned r, and the three outcome masses."""
    po, pr = float(p_ordinary_win), float(p_reserve_win)
    if (not math.isfinite(po) or not math.isfinite(pr)
            or not 0.0 <= po <= 1.0 or not 0.0 <= pr <= 1.0):
        raise ValueError('survival probabilities must be finite and in [0,1]')
    q = 1.0 - po
    r = r_predict(artifact, pr)
    probabilities = [po, q * r, q * (1.0 - r)]
    if (any(not math.isfinite(x) or x < 0.0 or x > 1.0 for x in probabilities)
            or not math.isclose(sum(probabilities), 1.0, rel_tol=0.0, abs_tol=1e-12)):
        raise ValueError('mechanical-q/frozen-r produced invalid class probabilities')
    return q, r, probabilities


def load_frozen_qr_artifact(path: Path, expected_sha256: str) -> tuple[dict, str]:
    digest = sha256(path)
    if digest != expected_sha256:
        raise ValueError('frozen #326 q/r artifact SHA-256 mismatch')
    artifact = json.loads(path.read_text())
    if artifact.get('schema') != FROZEN_QR_SCHEMA:
        raise ValueError('unsupported frozen #326 q/r artifact schema')
    model = artifact.get('rModel')
    if not isinstance(model, dict):
        raise ValueError('frozen #326 artifact is missing rModel')
    if (len(model.get('featureMean', [])) != 1
            or len(model.get('featureScale', [])) != 1
            or len(model.get('standardizedCoefficients', [])) != 2
            or len(model.get('rawCoefficientsInterceptFirst', [])) != 2
            or model.get('converged') is not True):
        raise ValueError('malformed frozen #326 r model')
    numeric = (model['featureMean'] + model['featureScale']
               + model['standardizedCoefficients'] + model['rawCoefficientsInterceptFirst'])
    if not np.isfinite(np.asarray(numeric, dtype=np.float64)).all():
        raise ValueError('non-finite frozen #326 r model')
    if artifact.get('rFeatureOrder') != ['pReserveWin']:
        raise ValueError('frozen #326 r feature definition mismatch')
    if artifact.get('t2Rule') != T2_RULE:
        raise ValueError('frozen #326 T2 rule mismatch')
    if not isinstance(artifact.get('frozenCtmComponentHashes'), dict):
        raise ValueError('frozen CTM component hashes missing')
    return artifact, digest


def build_candidate_manifest(artifact: dict, artifact_sha256: str,
                             *, artifact_path: str = 'frozen_qr_artifact.json') -> dict:
    if artifact_sha256 != OLD_QR_ARTIFACT_SHA256:
        raise ValueError('candidate must reference the exact frozen #326 artifact')
    teacher = artifact.get('teacherProvenance', {})
    return {
        'schema': CANDIDATE_SCHEMA,
        'candidateId': 'active-lizard-mechanical-q-learned-r-t2',
        'qMode': MECHANICAL_Q_MODE,
        'qDefinition': 'q = 1 - pOrdinaryWin; exactly the B1 mechanical consumption probability',
        'rMode': FROZEN_R_MODE,
        'rFeatureOrder': ['pReserveWin'],
        'rPredictorSource': 'tools/combat_transition_lizard_mechanical_q.py::_model_predict; byte-identical to the #326 frozen q/r predictor',
        'rPredictorAstSha256': _predictor_ast_sha256(),
        'treatment': TREATMENT,
        't2Rule': T2_RULE,
        'rArtifact': {
            'path': artifact_path,
            'sha256': artifact_sha256,
            'sourcePullRequest': 326,
            'sourceHeadSha': OLD_QR_HEAD_SHA,
            'sourceSchema': FROZEN_QR_SCHEMA,
            'rModelSha256': _canonical_sha256(artifact['rModel']),
        },
        'frozenCtmComponentHashes': artifact['frozenCtmComponentHashes'],
        'silverTeacher': {
            'identity': artifact.get('teacherIdentity'),
            'provenance': teacher,
            'manifestSha256': artifact.get('teacherManifestSha256'),
            'provenanceSha256': _canonical_sha256(teacher),
        },
        'supportDomainDefinition': artifact.get('supportDomainDefinition'),
        'productionSupportStatus': 'active_unqualified_lizard',
    }


def load_candidate(path: Path, expected_sha256: str | None = None) -> tuple[dict, dict, str]:
    candidate_sha = sha256(path)
    if expected_sha256 is not None and candidate_sha != expected_sha256:
        raise ValueError('candidate manifest SHA-256 mismatch')
    candidate = json.loads(path.read_text())
    if candidate.get('schema') != CANDIDATE_SCHEMA:
        raise ValueError('unsupported mechanical-q candidate schema')
    if (candidate.get('qMode') != MECHANICAL_Q_MODE
            or candidate.get('rMode') != FROZEN_R_MODE
            or candidate.get('treatment') != TREATMENT
            or candidate.get('t2Rule') != T2_RULE):
        raise ValueError('candidate mode or T2 rule mismatch')
    artifact_ref = candidate.get('rArtifact', {})
    artifact_path = Path(artifact_ref.get('path', ''))
    if not artifact_path.is_absolute():
        artifact_path = path.parent / artifact_path
    artifact, artifact_sha = load_frozen_qr_artifact(
        artifact_path, artifact_ref.get('sha256', ''))
    if candidate.get('frozenCtmComponentHashes') != artifact.get('frozenCtmComponentHashes'):
        raise ValueError('candidate CTM component hashes differ from frozen #326 artifact')
    if candidate.get('silverTeacher', {}).get('identity') != artifact.get('teacherIdentity'):
        raise ValueError('candidate Silver teacher differs from frozen #326 artifact')
    if candidate.get('rArtifact', {}).get('rModelSha256') != _canonical_sha256(artifact['rModel']):
        raise ValueError('candidate r model hash differs from frozen #326 artifact')
    return candidate, artifact, candidate_sha


def revive_hp(max_hp: int) -> int:
    if type(max_hp) is not int or max_hp < 2:
        raise ValueError('T2 requires integer maxHP >= 2')
    return max_hp // 2


def _candidate_has_lizard(pre: dict, predictor: dict) -> bool:
    rid = pilot.LIZARD_TAIL_ID
    return (any(int(item['id']) == rid for item in pre['relics'])
            or any(int(item['relicId']) == rid for item in predictor['relics']))


def _eligible_support(pre: dict, predictor: dict, models) -> tuple[bool, str | None]:
    """Check ordinary support after stripping Tail; exact boundaries stay excluded."""
    bloom = composed.base._RELIC_IDS['MARK_OF_THE_BLOOM']
    fairy = composed.base._POTION_IDS['FAIRY_POTION']
    if (any(int(item['id']) == bloom for item in pre['relics'])
            or any(int(item['relicId']) == bloom for item in predictor['relics'])):
        return False, 'mark_of_bloom_exact_path'
    if fairy in pre['potions']:
        return False, 'fairy_potion_exact_boundary'
    stripped_pre = pilot._strip_lizard(pre)
    stripped_predictor = pilot._strip_lizard_input(predictor)
    reasons = composed.full_support_reasons(stripped_pre, stripped_predictor, models)
    if reasons:
        return False, 'unsupported:' + ','.join(reasons)
    return True, None


def select_precomputed(scored_rows: list[dict], cohorts: dict[str, list[int]], salt: str) -> list[dict]:
    """Select HARD risk maxima and BROAD hash samples without reading outcomes."""
    hard = cohorts.get('HARD288', [])
    broad = cohorts.get('BROAD32', [])
    if len(hard) != 288 or len(broad) != 32 or set(hard) & set(broad):
        raise ValueError('qualification assignment must contain disjoint HARD288 and BROAD32 sources')
    if not isinstance(salt, str) or not salt:
        raise ValueError('BROAD32 fixed salt is required')
    by_source: dict[int, list[dict]] = collections.defaultdict(list)
    seen = set()
    for row in scored_rows:
        source, fight = int(row['sourceSeed']), int(row['fightIdx'])
        if (source, fight) in seen:
            raise ValueError('duplicate precombat candidate source/fight')
        seen.add((source, fight))
        by_source[source].append(row)
    selected = []
    target_fields = (
        'sourceSeed', 'fightIdx', 'pOrdinaryWin', 'pReserveWin', 'qTailConsumed',
        'rWinGivenConsumed', 'pLossConsumed', 'pDeath', 'predictorInputSha256',
        'preStateSha256', 'predictorInput', 'preState')
    for source in hard:
        rows = by_source.get(int(source), [])
        if not rows:
            raise ValueError(f'HARD288 source has no prospective-support candidate: {source}')
        chosen = min(rows, key=lambda row: (-float(row['pLossConsumed']), int(row['fightIdx'])))
        selected.append({**{key: chosen[key] for key in target_fields if key in chosen},
                         'qualificationCohort': 'HARD288',
                         'riskBand': 'HARD288_MECHANICAL_Q_MAX_P_LOSS_CONSUMED'})
    for source in broad:
        rows = by_source.get(int(source), [])
        if not rows:
            raise ValueError(f'BROAD32 source has no prospective-support candidate: {source}')
        def rank(row):
            preimage = f"{int(source)}:{int(row['fightIdx'])}:{salt}".encode('utf-8')
            return hashlib.sha256(preimage).hexdigest()
        chosen = min(rows, key=lambda row: (rank(row), int(row['fightIdx'])))
        selected.append({**{key: chosen[key] for key in target_fields if key in chosen},
                         'qualificationCohort': 'BROAD32',
                         'riskBand': 'BROAD32_OUTCOME_BLIND_HASH',
                         'broadSelectionHash': rank(chosen)})
    return sorted(selected, key=lambda row: int(row['sourceSeed']))


def build_fresh_source_assignment() -> dict:
    """Freeze the audited fresh native qualification source block before outcomes."""
    start, count = FRESH_SOURCE_START, FRESH_SOURCE_COUNT
    end = start + count - 1
    hard = list(range(start, start + 288))
    broad = list(range(start + 288, end + 1))
    intersections = [seed for low, high in PRIOR_LIZARD_SOURCE_INTERVALS
                     for seed in range(max(start, low), min(end, high) + 1)]
    previous_unique = sum(high - low + 1 for low, high in PRIOR_LIZARD_SOURCE_INTERVALS)
    if intersections:
        raise ValueError(f'proposed fresh Lizard source block overlaps prior evidence: {intersections}')
    return {
        'schema': 'active_lizard_mechanical_q_source_assignment_v1',
        'stage': 'C',
        'recordedBeforeCandidateOrPairCollection': True,
        'baselineGitSha': FRESH_BASELINE_GIT_SHA,
        'sourceSeedRange': {'start': start, 'endInclusive': end, 'count': count},
        'cohorts': {'HARD288': hard, 'BROAD32': broad},
        'partitionRule': 'ascending sourceSeed: first 288 HARD288, final 32 BROAD32',
        'broad32Salt': FRESH_BROAD32_SALT,
        'broad32Selection': {
            'algorithm': 'sha256',
            'direction': 'lexicographically smallest hexadecimal digest',
            'eligibility': 'prospective-support eligible combats only',
            'preimage': 'sourceSeed:fightIdx:fixedSalt',
        },
        'freshnessAudit': {
            'auditResult': 'FRESH_320_SOURCE_BLOCK',
            'candidateBlockIntersection': intersections,
            'previousLizardSourceIntervals': [list(interval)
                                              for interval in PRIOR_LIZARD_SOURCE_INTERVALS],
            'previousUniqueSourceSeeds': previous_unique,
            'searched': (
                'all docs/experiments/evidence/*lizard* JSON/JSONL sourceSeed rows and seedSpec/sourceSeeds, '
                'plus exact seven-digit seed mentions in docs/experiments/ledger-06.md and '
                'docs/knowledge-base/evaluation/current-research.md'),
        },
        'mechanicalRiskRule': (
            'HARD288 selects one prospective-support combat per source maximizing '
            '(1-pOrdinaryWin)*(1-r), with ascending fightIdx exact tie-break'),
        'outcomeBlindSelection': True,
        'teacherRequirement': 'current native_silver, exact-10k fair teacher; Stage C only',
    }


def _validate_native_candidate_pool(manifest: dict, teacher_path: Path) -> tuple[dict, str]:
    teacher = json.loads(teacher_path.read_text())
    validate_teacher(teacher)
    if teacher.get('combat_backend') != 'native_silver':
        raise ValueError('fresh candidate pool requires current native_silver teacher')
    if manifest.get('combatTeacher') != teacher:
        raise ValueError('candidate pool teacher differs from the frozen native teacher manifest')
    teacher_sha = sha256(teacher_path)
    if (manifest.get('producerGitSha') != teacher.get('git_sha')
            or manifest.get('producerExecutableSha256') != teacher.get('executable_sha256')
            or teacher.get('environment', {}).get('STS_EXECUTABLE_GIT_SHA') != teacher.get('git_sha')):
        raise ValueError('candidate pool producer is not bound to the frozen native teacher executable')
    return teacher, teacher_sha


def select_candidates(candidate_manifest_path: Path, candidate_path: Path,
                      assignment_path: Path,
                      salt: str, native_teacher_path: Path,
                      output_path: Path) -> dict:
    candidate, artifact, candidate_sha = load_candidate(candidate_path)
    assignment = json.loads(assignment_path.read_text())
    if assignment != build_fresh_source_assignment():
        raise ValueError('source assignment differs from the audited fresh HARD288/BROAD32 freeze')
    cohorts = assignment.get('cohorts', {})
    hard, broad = cohorts.get('HARD288', []), cohorts.get('BROAD32', [])
    expected_sources = set(hard) | set(broad)
    if (len(expected_sources) != 320 or len(hard) != 288 or len(broad) != 32
            or assignment.get('broad32Salt') != salt):
        raise ValueError('source assignment differs from frozen 288/32 cohort or salt')
    manifest = json.loads(candidate_manifest_path.read_text())
    teacher, native_teacher_sha = _validate_native_candidate_pool(manifest, native_teacher_path)
    count = int(manifest.get('seedSpec', {}).get('count', -1))
    start = int(manifest.get('seedSpec', {}).get('start', -1))
    integrity = manifest.get('integrity', {})
    if (manifest.get('schemaVersion') != 'combat_transition_v1'
            or manifest.get('rowSchemaVersion') != 'combat_transition_row_v2'
            or count != 320 or start != int(assignment['sourceSeedRange']['start'])
            or integrity.get('requestedSeeds') != 320
            or integrity.get('completedSeeds') != 320
            or integrity.get('quarantinedSeeds') != 0):
        raise ValueError('candidate source pool is not a complete frozen 320-source cohort')
    if set(range(start, start + count)) != expected_sources:
        raise ValueError('candidate seed block differs from predeclared source assignment')
    candidate_data_path = pilot._resolve_manifest_file(
        manifest.get('csv', manifest.get('jsonl', {})).get('path', ''), candidate_manifest_path.parent)
    data_spec = manifest.get('csv', manifest.get('jsonl', {}))
    if sha256(candidate_data_path) != data_spec.get('sha256'):
        raise ValueError('candidate-state JSONL hash mismatch')
    import torch
    torch.set_num_threads(4)
    models = composed.FrozenModels('cuda' if torch.cuda.is_available() else 'cpu')
    if models.hashes != candidate.get('frozenCtmComponentHashes'):
        raise ValueError('selector CTM component hashes differ from frozen candidate')
    scored, excluded = [], collections.Counter()
    seen, source_rows = set(), collections.defaultdict(set)
    rows_read = 0
    for line_no, line in enumerate(candidate_data_path.read_text().splitlines(), 1):
        if not line:
            continue
        rows_read += 1
        row = json.loads(line)
        if row.get('runValid') is not True:
            raise ValueError(f'invalid producer row at line {line_no}; refusing outcome-dependent filtering')
        source, fight = int(row['sourceSeed']), int(row['fightIdx'])
        if source not in expected_sources:
            raise ValueError(f'candidate source outside predeclared assignment at line {line_no}')
        if (source, fight) in seen:
            raise ValueError(f'duplicate candidate source/fight at line {line_no}')
        seen.add((source, fight))
        predictor, pre = row['predictorInput'], row['transition']['pre']
        validate_predictor_input(predictor)
        validate_state(pre, 'candidate.pre')
        if _candidate_has_lizard(pre, predictor):
            excluded['source_already_owns_lizard'] += 1
            continue
        eligible, reason = _eligible_support(pre, predictor, models)
        if not eligible:
            excluded[str(reason)] += 1
            continue
        reserve_input = copy.deepcopy(predictor)
        maximum = int(predictor['globals']['maxHp'])
        reserve_input['globals']['curHp'] = min(
            maximum, int(predictor['globals']['curHp']) + maximum // 2)
        p_ordinary = float(models.survival(models.encode_visible(predictor)))
        p_reserve = float(models.survival(models.encode_visible(reserve_input)))
        q, r, probabilities = predict(p_ordinary, p_reserve, artifact)
        source_rows[source].add(fight)
        scored.append({
            'sourceSeed': source, 'fightIdx': fight,
            'pOrdinaryWin': p_ordinary, 'pReserveWin': p_reserve,
            'qTailConsumed': q, 'rWinGivenConsumed': r,
            'pLossConsumed': probabilities[2],
            'pDeath': 1.0 - p_ordinary,
            'predictorInputSha256': _canonical_sha256(predictor),
            'preStateSha256': _canonical_sha256(pre),
            'predictorInput': predictor, 'preState': pre,
        })
    if rows_read != int(integrity.get('rows', -1)):
        raise ValueError('candidate JSONL row count differs from generator manifest')
    covered = set(source_rows)
    if covered != expected_sources:
        raise ValueError(f'not every assigned source has an eligible combat; missing={sorted(expected_sources-covered)}')
    selected = select_precomputed(scored, cohorts, salt)
    result = {
        'schema': 'lizard_tail_risk_target_selection_v1',
        'stateSelection': STATE_SELECTION,
        'selectionPolicy': (
            'HARD288=max (1-pOrdinaryWin)*(1-r), fightIdx ascending exact-tie-break; '
            'BROAD32=min SHA256(sourceSeed:fightIdx:fixedSalt)'),
        'candidateId': candidate['candidateId'],
        'candidateManifestSha256': candidate_sha,
        'rArtifactSha256': candidate['rArtifact']['sha256'],
        'candidateGeneratorManifestSha256': sha256(candidate_manifest_path),
        'candidateJsonlSha256': data_spec['sha256'],
        'candidateProducerGitSha': manifest['producerGitSha'],
        'candidateProducerExecutableSha256': manifest['producerExecutableSha256'],
        'candidateSeedSpec': manifest['seedSpec'],
        'nativeTeacherId': teacher['teacher_id'],
        'nativeTeacherManifestSha256': native_teacher_sha,
        'nativeTeacherExecutableSha256': teacher['executable_sha256'],
        'cohortPartition': {name: sorted(int(x) for x in ids) for name, ids in cohorts.items()},
        'broad32HashRule': {
            'algorithm': 'sha256', 'preimage': 'sourceSeed:fightIdx:fixedSalt',
            'salt': salt, 'direction': 'lexicographically smallest hexadecimal digest'},
        'sourceAssignmentPath': assignment_path.name,
        'sourceAssignmentSha256': sha256(assignment_path),
        'riskModel': 'mechanical q=1-pOrdinaryWin; frozen learned r; P(LOSS_CONSUMED)=q*(1-r)',
        'riskModelHashes': models.hashes,
        'eligibilityRule': (
            'exclude Mark of the Bloom, Fairy Potion, and any pre-existing Tail for paired targets; '
            'strip Tail before composed full-support check'),
        'integrity': {'assignedSources': len(expected_sources), 'eligibleSources': len(covered),
                      'eligibleCandidates': len(scored), 'selectedSources': len(selected),
                      'rowsRead': rows_read, 'excluded': dict(sorted(excluded.items()))},
        'targets': selected,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    freeze = sub.add_parser('freeze')
    freeze.add_argument('--r-artifact', type=Path, required=True)
    freeze.add_argument('--output', type=Path, required=True)
    freeze.add_argument('--r-artifact-path', default='frozen_qr_artifact.json')
    freeze_assignment = sub.add_parser('freeze-assignment')
    freeze_assignment.add_argument('--output', type=Path, required=True)
    select = sub.add_parser('select')
    select.add_argument('--candidate-manifest', type=Path, required=True,
                        help='native collector manifest for candidate JSONL')
    select.add_argument('--candidate-data', type=Path, required=True,
                        help='frozen mechanical-q candidate manifest')
    select.add_argument('--assignment', type=Path, required=True)
    select.add_argument('--salt', required=True)
    select.add_argument('--native-teacher', type=Path, required=True)
    select.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'freeze':
        artifact, digest = load_frozen_qr_artifact(args.r_artifact, OLD_QR_ARTIFACT_SHA256)
        candidate = build_candidate_manifest(artifact, digest, artifact_path=args.r_artifact_path)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(candidate, indent=2, sort_keys=True) + '\n')
        print(json.dumps({'candidateManifest': str(args.output), 'sha256': sha256(args.output),
                          'rArtifactSha256': digest, 'qMode': MECHANICAL_Q_MODE,
                          'rMode': FROZEN_R_MODE, 'treatment': TREATMENT}, indent=2))
    elif args.command == 'freeze-assignment':
        assignment = build_fresh_source_assignment()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(assignment, indent=2, sort_keys=True) + '\n')
        print(json.dumps({'sourceAssignment': str(args.output),
                          'sha256': sha256(args.output),
                          'sourceSeedRange': assignment['sourceSeedRange'],
                          'freshnessAudit': assignment['freshnessAudit']}, indent=2))
    else:
        result = select_candidates(args.candidate_manifest, args.candidate_data,
                                   args.assignment, args.salt,
                                   args.native_teacher, args.output)
        print(json.dumps({k: v for k, v in result.items() if k != 'targets'}, indent=2))


if __name__ == '__main__':
    main()
