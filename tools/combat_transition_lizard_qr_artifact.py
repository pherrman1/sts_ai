#!/usr/bin/env python3
"""Freeze the accepted Lizard q/r model and select a predeclared cohort.

This module only fits the frozen development rows and scores precombat
candidate states. It does not inspect paired outcomes during selection and it
does not alter production support.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from tools import combat_transition_composed as composed
from tools import combat_transition_lizard_minimal as minimal
from tools import combat_transition_lizard_pair_pilot as pilot
from tools.combat_transition_contract import sha256, validate_state
from tools.combat_predictor_input_contract import validate_predictor_input
from tools.ooc_pipeline_contract import validate_teacher

ARTIFACT_SCHEMA = 'active_lizard_qr_frozen_artifact_v1'
SELECTION_SCHEMA = 'lizard_tail_risk_target_selection_v1'
STATE_SELECTION = 'predeclared_qr_hard96_broad32_hash_v1'
Q_FEATURES = ['logit(pDeath)', 'pReserveWin - pOrdinaryWin']
R_FEATURES = ['pReserveWin']
T2_RULE = 'T2_revive: curHp = floor(maxHP/2) for WIN_CONSUMED conditional CTM heads'
SUPPORT_DEFINITION = (
    'active Lizard Tail is removed from pre-state and predictor input; '
    'composed.full_support_reasons(stripped_pre, stripped_predictor, frozen_models) == []; '
    'exclude Fairy Potion; Mark of the Bloom remains on its existing exact path')


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _logit(value: float) -> float:
    p = float(np.clip(value, 1e-8, 1.0 - 1e-8))
    return math.log(p / (1.0 - p))


def _model_payload(model: dict) -> dict:
    return {
        'featureMean': np.asarray(model['mean'], dtype=np.float64).tolist(),
        'featureScale': np.asarray(model['scale'], dtype=np.float64).tolist(),
        'standardizedCoefficients': np.asarray(model['standardizedCoefficients'], dtype=np.float64).tolist(),
        'rawCoefficientsInterceptFirst': np.asarray(model['coefficients'], dtype=np.float64).tolist(),
        'converged': bool(model['converged']),
    }


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


def require_valid_candidate_row(row: dict, line_no: int) -> None:
    """Reject producer-integrity failures; never select around them.

    The producer's validity flag is finalized after combat. Treat it only as a
    whole-cohort integrity gate, never as a row filter that could steer which
    precombat state gets selected.
    """
    if row.get('runValid') is not True:
        raise ValueError(
            f'candidate producer emitted invalid post-combat row at line {line_no}; '
            'refusing outcome-dependent selection')


def predict_qr(p_ordinary_win: float, p_reserve_win: float, artifact: dict) -> tuple[float, float, list[float]]:
    """Evaluate q/r and return the three coherent legal outcome masses."""
    po, pr = float(p_ordinary_win), float(p_reserve_win)
    if not math.isfinite(po) or not math.isfinite(pr) or not 0 <= po <= 1 or not 0 <= pr <= 1:
        raise ValueError('survival probabilities must be finite and in [0,1]')
    # This is the frozen signed feature definition. Some supported states have
    # mechanically incoherent B1 class masses (pReserveWin < pOrdinaryWin);
    # preserve their exact signed difference here and report B1 incoherence in
    # the qualification analysis rather than clipping it during selection.
    q_features = np.asarray([[_logit(1.0 - po), pr - po]], dtype=np.float64)
    r_features = np.asarray([[pr]], dtype=np.float64)
    q = float(_model_predict(artifact['qModel'], q_features)[0])
    r = float(_model_predict(artifact['rModel'], r_features)[0])
    probs = [1.0 - q, q * r, q * (1.0 - r)]
    if any(not math.isfinite(p) or p < 0 or p > 1 for p in probs) or not math.isclose(sum(probs), 1.0, abs_tol=1e-12):
        raise ValueError('frozen q/r produced invalid class probabilities')
    return q, r, probs


def fit_qr_models(records: list[dict]) -> dict:
    """Fit the accepted q/r recipe without CV selection or recipe variation."""
    labels = np.asarray([int(row['label']) for row in records], dtype=np.int64)
    q_features, r_features = minimal.factorized_feature_arrays(records)
    q_labels = np.isin(labels, (minimal.WIN_CONSUMED, minimal.LOSS_CONSUMED)).astype(np.int64)
    consumed = np.flatnonzero(q_labels == 1)
    if not len(records) or not len(consumed):
        raise ValueError('q/r fit requires development rows and consumed-tail rows')
    r_labels = (labels[consumed] == minimal.WIN_CONSUMED).astype(np.int64)
    q_model = minimal.logistic_fit(q_features, q_labels, l2=minimal.L2)
    r_model = minimal.logistic_fit(r_features[consumed], r_labels, l2=minimal.L2)
    if not q_model['converged'] or not r_model['converged']:
        raise ValueError('frozen q/r L2 logistic fit did not converge')
    return {'qModel': _model_payload(q_model), 'rModel': _model_payload(r_model),
            'qFitRows': len(records), 'rFitRows': len(consumed)}


def load_artifact(path: Path, expected_sha256: str | None = None) -> tuple[dict, str]:
    digest = file_sha256(path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError('frozen q/r artifact SHA-256 mismatch')
    artifact = json.loads(path.read_text())
    if artifact.get('schema') != ARTIFACT_SCHEMA:
        raise ValueError('unsupported frozen q/r artifact schema')
    if artifact.get('qFeatureOrder') != Q_FEATURES or artifact.get('rFeatureOrder') != R_FEATURES:
        raise ValueError('frozen q/r feature definition mismatch')
    if artifact.get('t2Rule') != T2_RULE:
        raise ValueError('frozen q/r T2 rule mismatch')
    if artifact.get('supportDomainDefinition') != SUPPORT_DEFINITION:
        raise ValueError('frozen q/r support schema mismatch')
    if artifact.get('fitRecipe', {}).get('l2') != 1.0:
        raise ValueError('frozen q/r fit recipe mismatch')
    for key, width in (('qModel', 2), ('rModel', 1)):
        model = artifact.get(key)
        if not isinstance(model, dict):
            raise ValueError(f'missing frozen model: {key}')
        if (len(model.get('featureMean', [])) != width
                or len(model.get('featureScale', [])) != width
                or len(model.get('standardizedCoefficients', [])) != width + 1
                or len(model.get('rawCoefficientsInterceptFirst', [])) != width + 1
                or model.get('converged') is not True):
            raise ValueError(f'malformed frozen model: {key}')
        numeric = (model['featureMean'] + model['featureScale']
                   + model['standardizedCoefficients'] + model['rawCoefficientsInterceptFirst'])
        if not np.isfinite(np.asarray(numeric, dtype=np.float64)).all():
            raise ValueError(f'non-finite frozen model: {key}')
    if not isinstance(artifact.get('frozenCtmComponentHashes'), dict) or not artifact['frozenCtmComponentHashes']:
        raise ValueError('frozen CTM component hashes missing')
    return artifact, digest


def _same_observation(left: dict, right: dict) -> bool:
    def normalize(pair):
        copy_pair = copy.deepcopy(pair)
        copy_pair.get('pair', {}).pop('targetRiskBand', None)
        return copy_pair
    return normalize(left) == normalize(right)


def _load_cohorts(manifest_paths: list[Path]):
    pairs = []
    manifests = []
    seen = {}
    duplicate_count = 0
    for manifest_path in manifest_paths:
        manifest, rows = pilot.validate_pair_corpus(manifest_path)
        included = 0
        for pair in rows:
            key = (int(pair['pair']['sourceSeed']), int(pair['pair']['fightIdx']))
            if key in seen:
                if not _same_observation(seen[key], pair):
                    raise ValueError(f'conflicting duplicate development pair: {key}')
                duplicate_count += 1
                continue
            seen[key] = pair
            pairs.append(pair)
            included += 1
        manifests.append({
            'manifestPath': str(manifest_path), 'manifestSha256': sha256(manifest_path),
            'pairedJsonlSha256': manifest['jsonl']['sha256'],
            'rawPairs': len(rows), 'includedPairs': included,
            'baselineGitSha': manifest['baselineGitSha'],
            'teacherId': manifest['combatTeacher']['teacher_id'],
        })
    if len({row['baselineGitSha'] for row in manifests}) != 1:
        raise ValueError('development pair corpora have different baseline SHAs')
    if len({row['teacherId'] for row in manifests}) != 1:
        raise ValueError('development pair corpora have different teachers')
    return pairs, manifests, duplicate_count


def freeze_development(manifest_paths: list[Path], analysis_path: Path,
                       models=None, code_sha: str | None = None) -> dict:
    """Fit the one accepted q/r model on all 427 supported development rows."""
    pairs, manifests, duplicate_count = _load_cohorts(manifest_paths)
    if models is None:
        import torch
        torch.set_num_threads(4)
        models = composed.FrozenModels('cuda' if torch.cuda.is_available() else 'cpu')
    native_eligible = []
    support_eligible = []
    boundary_counts = collections.Counter()
    support_counts = collections.Counter()
    for pair in pairs:
        reasons = minimal.native_boundary_reasons(pair)
        if reasons:
            boundary_counts.update(reasons)
            continue
        native_eligible.append(pair)
        pre = pilot._strip_lizard(pair['activeTail']['transition']['pre'])
        predictor = pilot._strip_lizard_input(pair['noTail']['predictorInput'])
        reasons = composed.full_support_reasons(pre, predictor, models)
        if reasons:
            support_counts.update(reasons)
        else:
            support_eligible.append(pair)
    analysis = json.loads(analysis_path.read_text())
    if len(support_eligible) != int(analysis.get('modeledPairs', -1)):
        raise ValueError('reconstructed development support cohort row count differs from frozen analysis')
    if models.hashes != analysis.get('frozenModelHashes'):
        raise ValueError('current frozen CTM hashes differ from development analysis')
    records = minimal._derive_features(support_eligible, models)
    labels = np.asarray([row['label'] for row in records], dtype=np.int64)
    class_counts = collections.Counter(minimal.CLASS_NAMES[int(label)] for label in labels)
    source_ids = sorted({int(row['sourceSeed']) for row in records})
    if {name: int(class_counts[name]) for name in minimal.CLASS_NAMES} != analysis.get('classCounts'):
        raise ValueError('reconstructed development class counts differ from frozen analysis')
    if len(source_ids) != int(analysis.get('distinctModeledSources', -1)):
        raise ValueError('reconstructed development source count differs from frozen analysis')
    fitted = fit_qr_models(records)
    teacher = json.loads(Path(manifest_paths[0]).read_text())['combatTeacher']
    if code_sha is None:
        import subprocess
        code_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    fit_code_path = Path(__file__).resolve()
    minimal_code_path = Path(minimal.__file__).resolve()
    return {
        'schema': ARTIFACT_SCHEMA,
        'qFeatureOrder': Q_FEATURES,
        'rFeatureOrder': R_FEATURES,
        'qModel': fitted['qModel'],
        'rModel': fitted['rModel'],
        'fitRecipe': {
            'estimator': 'deterministic L2 logistic regression using tools.combat_transition_lizard_minimal.logistic_fit',
            'fitRows': {'q': fitted['qFitRows'], 'r': fitted['rFitRows']},
            'l2': float(minimal.L2), 'iterationsMax': 100,
            'featureStandardization': 'population mean/std per feature; std below 1e-8 replaced by 1',
            'intercept': 'unpenalized', 'solver': 'Newton method; stop when max absolute step < 1e-10',
            'probabilityLogitClip': [-40.0, 40.0], 'qLogitInputClip': [1e-8, 1-1e-8],
        },
        't2Rule': T2_RULE,
        'retainedWinConditionalHeads': 'T0_ordinary',
        'development': {
            'baselineGitSha': manifests[0]['baselineGitSha'],
            'currentCodeShaAtFreeze': code_sha,
            'fitImplementationSha256': file_sha256(fit_code_path),
            'logisticImplementationSha256': file_sha256(minimal_code_path),
            'sourceIds': source_ids,
            'sourceCount': len(source_ids), 'rowCount': len(records),
            'classCounts': {name: int(class_counts[name]) for name in minimal.CLASS_NAMES},
            'duplicateFightKeysDropped': duplicate_count,
            'inputManifests': manifests,
            'supportAnalysisPath': str(analysis_path),
            'supportAnalysisSha256': sha256(analysis_path),
            'boundaryExclusions': dict(sorted(boundary_counts.items())),
            'fullSupportExclusions': dict(sorted(support_counts.items())),
        },
        'frozenCtmComponentHashes': dict(models.hashes),
        'supportDomainDefinition': SUPPORT_DEFINITION,
        'teacherIdentity': teacher['teacher_id'],
        'teacherManifestSha256': json.loads(Path(manifest_paths[0]).read_text())['combatTeacherManifestSha256'],
        'teacherProvenance': teacher,
    }


def write_artifact(artifact: dict, output_path: Path) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, sort_keys=True, indent=2) + '\n')
    return file_sha256(output_path)


def select_precomputed(scored_rows: list[dict], hard_sources: list[int],
                       broad_sources: list[int], salt: str) -> list[dict]:
    """Pick HARD risk maxima and BROAD hash samples without reading outcomes."""
    if len(hard_sources) != 96 or len(broad_sources) != 32 or set(hard_sources) & set(broad_sources):
        raise ValueError('qualification assignment must contain disjoint HARD96 and BROAD32 sources')
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
    for source in hard_sources:
        rows = by_source.get(int(source), [])
        if not rows:
            raise ValueError(f'HARD96 source has no prospective-support candidate: {source}')
        selected.append(dict(min(rows, key=lambda row: (-float(row['pLossConsumed']), int(row['fightIdx']))),
                             qualificationCohort='HARD96'))
    for source in broad_sources:
        rows = by_source.get(int(source), [])
        if not rows:
            raise ValueError(f'BROAD32 source has no prospective-support candidate: {source}')
        def rank(row):
            key = f"{int(source)}:{int(row['fightIdx'])}:{salt}".encode('utf-8')
            return hashlib.sha256(key).hexdigest()
        chosen = min(rows, key=lambda row: (rank(row), int(row['fightIdx'])))
        selected.append(dict(chosen, qualificationCohort='BROAD32', broadSelectionHash=rank(chosen)))
    return sorted(selected, key=lambda row: int(row['sourceSeed']))


def select_candidates(candidate_manifest_path: Path, artifact_path: Path,
                      artifact_sha256: str, assignment_path: Path, salt: str,
                      output_path: Path) -> dict:
    artifact, actual_artifact_sha = load_artifact(artifact_path, artifact_sha256)
    assignment = json.loads(assignment_path.read_text())
    if assignment.get('schema') != 'active_lizard_qualification_source_assignment_v1':
        raise ValueError('invalid frozen source assignment')
    hard_sources = assignment.get('hard96SourceIds')
    broad_sources = assignment.get('broad32SourceIds')
    if assignment.get('broad32Salt') != salt:
        raise ValueError('BROAD32 salt differs from precollection source assignment')
    expected_sources = set(hard_sources or []) | set(broad_sources or [])
    if len(expected_sources) != 128 or len(hard_sources or []) != 96 or len(broad_sources or []) != 32:
        raise ValueError('source assignment does not contain 128 unique sources')
    manifest = json.loads(candidate_manifest_path.read_text())
    if (manifest.get('schemaVersion') != 'combat_transition_v1'
            or manifest.get('rowSchemaVersion') != 'combat_transition_row_v2'
            or manifest.get('integrity', {}).get('requestedSeeds') != 128
            or manifest.get('integrity', {}).get('completedSeeds') != 128
            or manifest.get('integrity', {}).get('quarantinedSeeds') != 0):
        raise ValueError('candidate source pool is not a complete 128-source cohort')
    teacher = manifest.get('combatTeacher', {})
    validate_teacher(teacher)
    frozen_teacher = artifact.get('teacherProvenance', {})
    if teacher.get('teacher_id') != artifact.get('teacherIdentity'):
        raise ValueError('candidate pool teacher differs from frozen artifact')
    for key in ('combat_backend', 'rng_regime', 'search_configuration', 'source_policy', 'teacher_id'):
        if teacher.get(key) != frozen_teacher.get(key):
            raise ValueError(f'candidate pool teacher contract differs from frozen artifact: {key}')
    teacher_env = dict(teacher.get('environment', {}))
    frozen_env = dict(frozen_teacher.get('environment', {}))
    teacher_env.pop('STS_EXECUTABLE_GIT_SHA', None)
    frozen_env.pop('STS_EXECUTABLE_GIT_SHA', None)
    if teacher_env != frozen_env:
        raise ValueError('candidate pool teacher environment differs from frozen artifact')
    def model_roles(spec):
        return sorted((item['role'], item['sha256']) for item in spec.get('model_artifacts', []))
    if model_roles(teacher) != model_roles(frozen_teacher):
        raise ValueError('candidate pool Silver model hashes differ from frozen artifact')
    if manifest.get('seedSpec', {}).get('count') != 128:
        raise ValueError('candidate manifest does not describe exactly 128 seeds')
    seed_start = int(manifest['seedSpec']['start'])
    if set(range(seed_start, seed_start + 128)) != expected_sources:
        raise ValueError('candidate seed block differs from predeclared HARD96/BROAD32 sources')
    candidate_path = pilot._resolve_manifest_file(manifest['csv']['path'], candidate_manifest_path.parent)
    if sha256(candidate_path) != manifest['csv']['sha256']:
        raise ValueError('candidate JSONL hash mismatch')
    import torch
    torch.set_num_threads(4)
    models = composed.FrozenModels('cuda' if torch.cuda.is_available() else 'cpu')
    if models.hashes != artifact['frozenCtmComponentHashes']:
        raise ValueError('candidate selector CTM component hashes differ from frozen q/r artifact')
    fairy = composed.base._POTION_IDS['FAIRY_POTION']
    bloom = composed.base._RELIC_IDS['MARK_OF_THE_BLOOM']
    scored = []
    excluded = collections.Counter()
    candidates = collections.defaultdict(set)
    seen = set()
    rows_read = 0
    for line_no, line in enumerate(candidate_path.read_text().splitlines(), 1):
        if not line:
            continue
        rows_read += 1
        row = json.loads(line)
        require_valid_candidate_row(row, line_no)
        source, fight = int(row['sourceSeed']), int(row['fightIdx'])
        if source not in expected_sources:
            raise ValueError(f'candidate source outside predeclared assignment at line {line_no}')
        if (source, fight) in seen:
            raise ValueError(f'duplicate candidate source/fight at line {line_no}')
        seen.add((source, fight))
        predictor, pre = row['predictorInput'], row['transition']['pre']
        validate_predictor_input(predictor)
        validate_state(pre, 'candidate.pre')
        if (any(int(item['relicId']) == bloom for item in predictor['relics'])
                or any(int(item['id']) == bloom for item in pre['relics'])):
            excluded['mark_of_the_bloom_exact_path'] += 1
            continue
        if fairy in pre['potions']:
            excluded['fairy_potion_exact_boundary'] += 1
            continue
        reasons = composed.full_support_reasons(pre, predictor, models)
        if reasons:
            excluded['unsupported:' + ','.join(reasons)] += 1
            continue
        maximum = int(predictor['globals']['maxHp'])
        reserve_input = copy.deepcopy(predictor)
        reserve_input['globals']['curHp'] = min(maximum, int(predictor['globals']['curHp']) + maximum // 2)
        p_ordinary = float(models.survival(models.encode_visible(predictor)))
        p_reserve = float(models.survival(models.encode_visible(reserve_input)))
        q, r, probs = predict_qr(p_ordinary, p_reserve, artifact)
        candidates[source].add(fight)
        scored.append({
            'sourceSeed': source, 'fightIdx': fight,
            'pOrdinaryWin': p_ordinary, 'pReserveWin': p_reserve,
            'qTailConsumed': q, 'rWinGivenConsumed': r,
            'pLossConsumed': probs[2],
            'pDeath': 1.0 - p_ordinary,
            'riskBand': 'HARD96_QR_MAX_P_LOSS_CONSUMED',
            'predictorInput': predictor, 'preState': pre,
            'predictorInputSha256': hashlib.sha256(json.dumps(predictor, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'preStateSha256': hashlib.sha256(json.dumps(pre, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        })
    if rows_read != int(manifest.get('integrity', {}).get('rows', -1)):
        raise ValueError('candidate JSONL row count differs from candidate manifest')
    covered = set(candidates)
    if covered != expected_sources:
        missing = sorted(expected_sources - covered)
        raise ValueError(f'not every assigned source has an eligible combat; missing={missing}')
    selected = select_precomputed(scored, hard_sources, broad_sources, salt)
    result = {
        'schema': SELECTION_SCHEMA,
        'selectionPolicy': 'HARD96=max frozen q*(1-r), fightIdx ascending tie-break; BROAD32=min SHA256(sourceSeed,fightIdx,fixedSalt)',
        'stateSelection': STATE_SELECTION,
        'cohortPartition': {'HARD96': [int(x) for x in hard_sources], 'BROAD32': [int(x) for x in broad_sources]},
        'broad32HashRule': {'algorithm': 'sha256', 'preimage': 'sourceSeed:fightIdx:fixedSalt', 'salt': salt,
                            'direction': 'lexicographically smallest hexadecimal digest'},
        'candidateManifestSha256': sha256(candidate_manifest_path),
        'candidateJsonlSha256': manifest['csv']['sha256'],
        'candidateProducerGitSha': manifest['producerGitSha'],
        'candidateProducerExecutableSha256': manifest['producerExecutableSha256'],
        'candidateSeedSpec': manifest['seedSpec'],
        'sourceAssignmentPath': str(assignment_path),
        'sourceAssignmentSha256': sha256(assignment_path),
        'artifactPath': str(artifact_path), 'artifactSha256': actual_artifact_sha,
        'riskModel': 'frozen q/r artifact; P(LOSS_CONSUMED)=q*(1-r)',
        'riskModelHashes': models.hashes,
        'integrity': {'assignedSources': len(expected_sources), 'eligibleSources': len(covered),
                      'eligibleCandidates': len(scored), 'selectedSources': len(selected)},
        'excluded': dict(sorted(excluded.items())),
        'targets': selected,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    freeze = sub.add_parser('freeze')
    freeze.add_argument('--manifest', type=Path, action='append', required=True)
    freeze.add_argument('--analysis', type=Path, required=True)
    freeze.add_argument('--output', type=Path, required=True)
    select = sub.add_parser('select')
    select.add_argument('--candidate-manifest', type=Path, required=True)
    select.add_argument('--artifact', type=Path, required=True)
    select.add_argument('--artifact-sha256', required=True)
    select.add_argument('--assignment', type=Path, required=True)
    select.add_argument('--salt', required=True)
    select.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'freeze':
        models = None
        import torch
        torch.set_num_threads(4)
        models = composed.FrozenModels('cuda' if torch.cuda.is_available() else 'cpu')
        artifact = freeze_development(args.manifest, args.analysis, models=models)
        digest = write_artifact(artifact, args.output)
        print(json.dumps({'artifact': str(args.output), 'sha256': digest,
                          'rows': artifact['development']['rowCount'],
                          'sources': artifact['development']['sourceCount'],
                          'classCounts': artifact['development']['classCounts']}, indent=2))
    else:
        result = select_candidates(args.candidate_manifest, args.artifact,
                                   args.artifact_sha256, args.assignment,
                                   args.salt, args.output)
        print(json.dumps({k: v for k, v in result.items() if k != 'targets'}, indent=2))


if __name__ == '__main__':
    main()
