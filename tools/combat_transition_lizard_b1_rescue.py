#!/usr/bin/env python3
"""Outcome-blind B1 targeting and source-grouped q/r analysis for Lizard Tail."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

import numpy as np

from tools import combat_transition_composed as composed
from tools import combat_transition_lizard_minimal as minimal
from tools import combat_transition_lizard_pair_pilot as pilot
from tools.combat_transition_contract import sha256, validate_state
from tools.combat_predictor_input_contract import validate_predictor_input


def score_candidates(manifest_path: Path, output_path: Path, *, batch: int,
                     prior_selections: list[Path], target_count: int = 128) -> dict:
    """Rank remaining candidate fights by fixed B1 P(LOSS_CONSUMED), before outcomes."""
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    data = manifest['csv']
    candidate_path = Path(data['path'])
    if not candidate_path.is_absolute() or not candidate_path.is_file() or sha256(candidate_path) != data['sha256']:
        raise ValueError('candidate JSONL missing or hash mismatch')
    if manifest.get('integrity') != {'requestedSeeds': 128, 'completedSeeds': 128,
                                     'quarantinedSeeds': 0, 'rows': 2700}:
        raise ValueError('candidate pool integrity differs from frozen 2,700-row pool')
    used: set[tuple[int, int]] = set()
    for selection_path in prior_selections:
        prior = json.loads(selection_path.read_text())
        if prior.get('candidateJsonlSha256') != data['sha256']:
            raise ValueError('prior selection belongs to another candidate pool')
        used.update((int(x['sourceSeed']), int(x['fightIdx'])) for x in prior['targets'])

    import torch
    torch.set_num_threads(4)
    models = composed.FrozenModels('cuda' if torch.cuda.is_available() else 'cpu')
    excluded = collections.Counter()
    best_by_source: dict[int, dict] = {}
    remaining_risk_scores: list[float] = []
    for line_no, line in enumerate(candidate_path.read_text().splitlines(), 1):
        if not line:
            continue
        row = json.loads(line)
        if row.get('runValid') is not True:
            excluded['invalid'] += 1
            continue
        source, fight = int(row['sourceSeed']), int(row['fightIdx'])
        if (source, fight) in used:
            excluded['already_selected'] += 1
            continue
        predictor, pre = row['predictorInput'], row['transition']['pre']
        validate_predictor_input(predictor)
        validate_state(pre, 'candidate.pre')
        relic_ids = {int(x['relicId']) for x in predictor['relics']}
        if relic_ids.intersection({composed.base._RELIC_IDS['MARK_OF_THE_BLOOM'], 35}):
            excluded['native_exact_boundary'] += 1
            continue
        support = composed.full_support_reasons(pre, predictor, models)
        if support:
            excluded['unsupported:' + ','.join(support)] += 1
            continue
        maximum = int(predictor['globals']['maxHp'])
        reserve_input = json.loads(json.dumps(predictor))
        reserve_input['globals']['curHp'] = min(
            maximum, int(predictor['globals']['curHp']) + maximum // 2)
        p_ordinary = float(models.survival(models.encode_visible(predictor)))
        p_reserve = float(models.survival(models.encode_visible(reserve_input)))
        if p_reserve + 1e-12 < p_ordinary:
            excluded['incoherent_B1'] += 1
            continue
        if p_reserve < p_ordinary:
            p_reserve = p_ordinary
        remaining_risk_scores.append(1.0 - p_reserve)
        input_sha = hashlib.sha256(json.dumps(predictor, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        state_sha = hashlib.sha256(json.dumps(pre, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        scored = {
            'sourceSeed': source, 'fightIdx': fight, 'riskBand': 'B1_LOSS_CONSUMED',
            'pDeath': 1.0 - p_ordinary, 'pOrdinaryWin': p_ordinary,
            'pReserveWin': p_reserve, 'pLossConsumed': 1.0 - p_reserve,
            'reserveUplift': p_reserve - p_ordinary,
            'predictorInputSha256': input_sha, 'preStateSha256': state_sha,
            'predictorInput': predictor, 'preState': pre,
        }
        old = best_by_source.get(source)
        if old is None or (scored['pLossConsumed'], -fight) > (old['pLossConsumed'], -old['fightIdx']):
            best_by_source[source] = scored
    selected = sorted(best_by_source.values(), key=lambda x: (-x['pLossConsumed'], x['sourceSeed']))[:target_count]
    if not selected:
        raise ValueError('no eligible remaining candidates')
    for index, row in enumerate(selected):
        row['b1Rank'] = index + 1
    selected.sort(key=lambda x: x['sourceSeed'])
    result = {
        'schema': 'lizard_tail_risk_target_selection_v1',
        'selectionPolicy': 'outcome_blind_fixed_B1_rank_by_1_minus_pReserveWin; one_fight_per_source_per_batch',
        'candidateManifestSha256': hashlib.sha256(manifest_bytes).hexdigest(),
        'candidateJsonlSha256': data['sha256'], 'candidateProducerGitSha': manifest['producerGitSha'],
        'candidateProducerExecutableSha256': manifest['producerExecutableSha256'],
        'candidateSeedSpec': manifest['seedSpec'], 'selectionSeed': 20260924,
        'batch': batch, 'priorSelectionCount': len(used), 'targetCount': len(selected),
        'riskModel': 'fixed B1 mechanical reserve: [pOrdinaryWin, pReserveWin-pOrdinaryWin, 1-pReserveWin]',
        'riskModelHashes': models.hashes, 'riskModelDevice': str(models.device),
        'torchVersion': str(torch.__version__), 'excluded': dict(sorted(excluded.items())),
        'remainingEligibleCandidates': len(remaining_risk_scores),
        'remainingPredictedLossConsumedMass': float(sum(remaining_risk_scores)),
        'remainingMeanPredictedLossConsumed': (float(sum(remaining_risk_scores) / len(remaining_risk_scores))
                                               if remaining_risk_scores else None),
        'scoreRange': {'maxPLossConsumed': max(x['pLossConsumed'] for x in selected),
                       'minPLossConsumed': min(x['pLossConsumed'] for x in selected)},
        'targets': selected,
    }
    output_path.write_text(json.dumps(result, indent=2) + '\n')
    return result


def _source_group_bootstrap(baseline: np.ndarray, candidate: np.ndarray,
                            labels: np.ndarray, sources: np.ndarray,
                            *, reps: int = 5000, seed: int = minimal.BOOTSTRAP_SEED + 1) -> dict:
    target = np.eye(3)[labels]
    base_nll = -np.log(np.maximum(baseline[np.arange(len(labels)), labels], 1e-300))
    cand_nll = -np.log(np.maximum(candidate[np.arange(len(labels)), labels], 1e-300))
    base_brier = np.sum((baseline - target) ** 2, axis=1)
    cand_brier = np.sum((candidate - target) ** 2, axis=1)
    groups = sorted(set(int(x) for x in sources))
    row_ids = {g: np.flatnonzero(sources == g) for g in groups}
    rng = np.random.default_rng(seed)
    out = {}
    for name, delta in (('threeClassNll', cand_nll - base_nll),
                        ('multiclassBrier', cand_brier - base_brier)):
        observed = float(delta.mean())
        boot = np.empty(reps)
        for i in range(reps):
            sampled = rng.choice(groups, size=len(groups), replace=True)
            rows = np.concatenate([row_ids[int(g)] for g in sampled])
            boot[i] = delta[rows].mean()
        out[name] = {'rows': len(delta), 'sources': len(groups),
                     'meanCorrectionMinusB1': observed,
                     'sourceBootstrap95CI': [float(np.quantile(boot, .025)),
                                             float(np.quantile(boot, .975))]}
    return out


def _tail_stripped_support_reasons(pair: dict, models) -> list[str]:
    """Apply ordinary CTM support to the exact pre-state with Tail removed."""
    pre = pair['activeTail']['transition']['pre']
    predictor = pair['noTail']['predictorInput']
    return composed.full_support_reasons(
        pilot._strip_lizard(pre), pilot._strip_lizard_input(predictor), models)


def _same_combat_observation(left: dict, right: dict) -> bool:
    """Compare replay content while ignoring target-selection risk metadata."""
    def observation(pair: dict) -> dict:
        value = dict(pair)
        pair_metadata = dict(pair.get('pair', {}))
        pair_metadata.pop('targetRiskBand', None)
        value['pair'] = pair_metadata
        return value

    return observation(left) == observation(right)


def analyze(manifest_paths: list[Path], output_path: Path, *,
            support_domain: bool = False) -> dict:
    pairs = []
    manifests = []
    seen_fights = {}
    duplicate_fights = []
    for path in manifest_paths:
        manifest, rows = pilot.validate_pair_corpus(path)
        included = 0
        for pair in rows:
            key = (int(pair['pair']['sourceSeed']), int(pair['pair']['fightIdx']))
            if key in seen_fights:
                prior_pair, prior_path = seen_fights[key]
                duplicate_fights.append({
                    'sourceSeed': key[0], 'fightIdx': key[1],
                    'keptManifest': str(prior_path), 'skippedManifest': str(path),
                    'identicalCombatObservation': _same_combat_observation(prior_pair, pair),
                    'selectionRiskBandChanged': prior_pair.get('pair', {}).get('targetRiskBand')
                    != pair.get('pair', {}).get('targetRiskBand'),
                })
                continue
            seen_fights[key] = (pair, path)
            pairs.append(pair)
            included += 1
        manifests.append({'path': str(path), 'sha256': sha256(path),
                          'rawPairs': len(rows), 'includedPairs': included,
                          'duplicatePairsDropped': len(rows) - included})
    if len({m['baselineGitSha'] for m in [json.loads(p.read_text()) for p in manifest_paths]}) != 1:
        raise ValueError('paired cohorts have differing baseline SHAs')
    import torch
    torch.set_num_threads(4)
    models = composed.FrozenModels('cuda' if torch.cuda.is_available() else 'cpu')
    native_eligible = []
    support_eligible = []
    boundary_reasons = collections.Counter()
    support_reasons = collections.Counter()
    for pair in pairs:
        reasons = minimal.native_boundary_reasons(pair)
        if reasons:
            boundary_reasons.update(reasons)
            continue
        native_eligible.append(pair)
        reasons = _tail_stripped_support_reasons(pair, models)
        if reasons:
            support_reasons.update(reasons)
        else:
            support_eligible.append(pair)
    eligible = support_eligible if support_domain else native_eligible
    records = minimal._derive_features(eligible, models)
    cv = minimal._factorized_cv(records)
    labels = np.asarray([r['label'] for r in records], dtype=np.int64)
    sources = np.asarray([r['sourceSeed'] for r in records], dtype=np.int64)
    mechanical_rows = [minimal.legal_class_probabilities(r['pOrdinaryWin'], r['pReserveWin'])
                       for r in records]
    coherent = np.asarray([row is not None for row in mechanical_rows], dtype=bool)
    b1 = np.full((len(records), 3), np.nan, dtype=np.float64)
    for i, row in enumerate(mechanical_rows):
        if row is not None:
            b1[i] = row
    correction = np.asarray([r['classProbabilities'] for r in cv['correction']['outOfFoldProbabilitiesBySource']], dtype=np.float64)
    if correction.shape != b1.shape or labels.shape != (len(b1),) or sources.shape != (len(b1),):
        raise ValueError('B1, q/r, labels, and source vectors lost row alignment')
    comparison = _source_group_bootstrap(b1[coherent], correction[coherent], labels[coherent], sources[coherent])
    counts = collections.Counter(minimal.CLASS_NAMES[int(y)] for y in labels)
    per_source = collections.Counter(int(x) for x in sources)
    result = {
        'schema': 'active_lizard_b1_qr_source_grouped_diagnostic_v1',
        'classification': 'DEVELOPMENT_ONLY', 't2Treatment': 'T2_revive fixed from prior cohort; not retuned',
        'analysisDomain': ('prospective_runtime_support_domain' if support_domain
                           else 'descriptive_after_native_boundaries'),
        'tailStrippedSupportDefinition': 'composed.full_support_reasons(pre with LIZARD_TAIL removed, noTail predictor input with LIZARD_TAIL removed, frozen models) == []',
        'inputManifests': manifests, 'pairs': len(pairs), 'modeledPairs': len(eligible),
        'duplicateFightKeysDropped': len(duplicate_fights),
        'duplicateFightKeyDetails': duplicate_fights,
        'duplicateObservationsIdenticalCombat': sum(x['identicalCombatObservation'] for x in duplicate_fights),
        'duplicateObservationsWithChangedSelectionRiskBand': sum(x['selectionRiskBandChanged'] for x in duplicate_fights),
        'distinctModeledSources': len(per_source), 'rowsPerSource': {
            'min': min(per_source.values()), 'median': float(np.median(list(per_source.values()))),
            'max': max(per_source.values())},
        'classCounts': dict(counts),
        'excludedNativeExactBoundaryPairs': len(pairs) - len(native_eligible),
        'nativeExactBoundaryReasons': dict(sorted(boundary_reasons.items())),
        'excludedFullSupportPairs': len(native_eligible) - len(support_eligible),
        'fullSupportExclusionReasons': dict(sorted(support_reasons.items())),
        'folding': '5-fold source-grouped; every fight from one source stays in one fold',
        'b1VsQr': {'b1': cv['mechanicalReserve']['classMetricsOnCoherentRows'],
                   'qr': minimal._prob_metrics(correction[coherent], labels[coherent]),
                   'correctionMinusB1SourceBootstrap': comparison,
                   'coherentRows': int(coherent.sum()), 'incoherentRows': int((~coherent).sum())},
        'qMetrics': cv['qConsumption'], 'rMetrics': cv['rConditionalRescue'],
        'foldByFold': cv['correction']['foldByFold'],
        'foldCoefficients': cv['correction']['foldCoefficients'],
        'frozenModelHashes': models.hashes,
        'claimBoundary': 'descriptive research only; no model export, runtime integration, or support qualification',
    }
    output_path.write_text(json.dumps(result, indent=2) + '\n')
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    select_p = sub.add_parser('select')
    select_p.add_argument('--manifest', type=Path, required=True)
    select_p.add_argument('--output', type=Path, required=True)
    select_p.add_argument('--batch', type=int, required=True)
    select_p.add_argument('--prior-selection', type=Path, action='append', default=[])
    select_p.add_argument('--target-count', type=int, default=128)
    analyze_p = sub.add_parser('analyze')
    analyze_p.add_argument('--manifest', type=Path, action='append', required=True)
    analyze_p.add_argument('--output', type=Path, required=True)
    analyze_p.add_argument('--support-domain', action='store_true',
                           help='fit and score only Tail-stripped CTM full-support rows')
    args = parser.parse_args()
    if args.command == 'select':
        result = score_candidates(args.manifest, args.output, batch=args.batch,
                                  prior_selections=args.prior_selection,
                                  target_count=args.target_count)
    else:
        result = analyze(args.manifest, args.output, support_domain=args.support_domain)
    print(json.dumps({k: v for k, v in result.items() if k != 'targets'}, indent=2))


if __name__ == '__main__':
    main()
