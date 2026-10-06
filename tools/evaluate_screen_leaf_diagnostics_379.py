#!/usr/bin/env python3
"""Future reviewed #379 VALIDATION diagnostics only; no TEST or qualification.

STAGING: do not execute until reviewed and copied into tools in a clean commit.
Resource predictions reuse reviewed exports/S0. Sibling values use the immediate
forced semantic-action poststate, never a nearest MAP or shared predecision row.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = next(p for p in Path(__file__).resolve().parents if (p / 'tools/screen_leaf_data_379.py').is_file())
sys.path[:0] = [str(REPO), str(REPO / 'tools')]
import numpy as np
from audit_screen_leaf_379 import digest, require
from screen_leaf_data_379 import DecisionCorpus, PROVISIONAL_MASK, HEADER_SHA
from screen_leaf_model_379 import encode_state, pack_encoded, build_model, verify_feature_names
from train_screen_leaf_379 import predict
from run_screen_leaf_validation_379 import frozen_sources, clean_sha, check_hashes
from tools.vwin_refresh_evaluation import cluster_mean
from screen_leaf_import_379 import (decorate_replay, verify_decoration, post_input, bind_selection,
                                    verify_selection, verify_current, verify_projected)

X2 = Path('/home/philippherrmann/Documents/sts/artifacts/vwin-refresh-334/a3-final1024-x2b-finalist-20261003-49c28d80/tune/X2/model.ubj')
X2_SHA = '99dbac6b5b082c46fe07242d2d15d8ccc6818041cb851efa79d6b423cdcb52dd'
CORE = {'identity', 'hp_minus', 'hp_plus', 'gold_minus', 'gold_plus', 'feed_like', 'max_only'}
BRANCH_HEADER = ['sourceSeed', 'decisionIdx', 'type', 'optionKey', 'chosen', 'branchId',
                 'won', 'finalFloor', 'finalHp', 'valid']


def load(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def key(row):
    return int(row['sourceSeed']), row['branchId'], int(row['rowIdx'])


def keyed_jsonl(path):
    result = {}
    with Path(path).open() as stream:
        for line in stream:
            row = json.loads(line)
            identity = key(row)
            require(identity not in result, 'duplicate JSONL identity: ' + str(path))
            result[identity] = row
    return result


def predictions(path, identities):
    rows = keyed_jsonl(path)
    require(set(rows) == set(identities), 'prediction identity population mismatch')
    values, seeds = {}, {}
    for identity, row in rows.items():
        if row.get('s0Status') == 'S0_UNSUPPORTED':
            # Fail-closed S0 row: no value; callers exclude it pairwise.
            require(row['values'] == [] and len(row['rngSeeds']) == 1 and row.get('unsupportedReason'),
                    'invalid S0 fail-closed row')
            seeds[identity] = row['rngSeeds'][0]; continue
        require('s0Status' not in row and len(row['values']) == len(row['rngSeeds']) == 1,
                'expected one paired S0 draw')
        v = row['values'][0]
        require(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1,
                'invalid S0 probability')
        values[identity] = float(v); seeds[identity] = row['rngSeeds'][0]
    return values, seeds


def recovery_evidence(directory):
    """Verify relevant frozen custody without rerunning the legacy validator."""
    protocol, result = load(directory / 'protocol.json'), load(directory / 'result.json')
    require(result['status'] == 'PASS' and result['protocol_sha256'] == digest(directory / 'protocol.json'),
            'full recovery not complete')
    sources = frozen_sources(Path(protocol['corpus']))
    by_seed = {r['seed']: r for r in sources}
    require(len(result['results']) == 155 and {r['seed'] for r in result['results']} == set(by_seed),
            'wrong VALIDATION source population')
    require(len(protocol['sources']) == 155 and {r['seed'] for r in protocol['sources']} == set(by_seed),
            'protocol VALIDATION population mismatch')
    require({r['seed']: r for r in protocol['sources']} == by_seed, 'recovery protocol source descriptors differ from frozen corpus')
    receipts = []
    for r in result['results']:
        seed, source = r['seed'], by_seed[r['seed']]
        require(r['status'] == 'PASS' and load(directory / str(seed) / 'result.json') == r,
                'aggregate/source recovery mismatch')
        replay = Path(r['replay']['directory'])
        custody = r['replay']
        for name, field in [('receipt.json', 'receipt_sha256'), ('result.json', 'result_sha256'),
                            ('snapshots.jsonl', 'snapshots_sha256')]:
            require(digest(replay / name) == custody[field], 'replay artifact changed: ' + name)
        receipt = load(replay / 'receipt.json')
        require(receipt['seed'] == seed and receipt['split'] == 'VALIDATION'
                and receipt['source_manifest_sha256'] == source['manifest_sha256']
                and Path(receipt['source_manifest']).resolve() == Path(source['manifest']).resolve(),
                'replay source not bound to frozen component')
        temporal = replay / 'snapshots.jsonl.temporal.jsonl'
        require(digest(temporal) == custody['temporal']['temporal_sha256'], 'temporal evidence changed')
        branches = replay / 'replay.branches.csv'
        require(digest(branches) == source['outputs']['branches.csv'], 'frozen branch table changed')
        receipts.append({'seed': seed, 'source': source, 'replay': replay, 'temporal': temporal,
                         'branches': branches, 'custody': custody, 'result_sha256': digest(directory / str(seed) / 'result.json')})
    return protocol, receipts


class Scorer:
    def __init__(self, training, feature_names, full_names):
        import torch
        self.names = feature_names
        verify_feature_names(self.names)
        require(len(full_names) == 1017 and len(set(full_names)) == 1017, 'full rich order invalid')
        self.indices = [full_names.index(n) for n in self.names]
        self.prereg = load(training / 'preregistered.json')
        final, dataset = load(training / 'result.json'), load(training / 'dataset.json')
        require(final['status'] == 'TRAINING_COMPLETE_NOT_QUALIFIED', 'training incomplete')
        require(tuple(self.prereg['replacement_candidates']) == tuple(PROVISIONAL_MASK), 'model mask mismatch')
        check_hashes(self.prereg['code'])
        require(dataset['feature_names'] == self.names and digest(training / 'normalization.npz') == dataset['normalization_sha256'],
                'normalization/feature custody mismatch')
        with np.load(training / 'normalization.npz', allow_pickle=False) as archive:
            normalization = {name: archive[name].copy() for name in archive.files}
        torch.set_num_threads(1)
        self.models = {}
        self.checkpoint_hashes = {}
        for arm in ('S1', 'S2'):
            models = []
            require(len(final['arms'][arm]['individual']) == 3, 'wrong initialization population')
            for seed in (0, 1, 2):
                record = load(training / f'{arm}-seed{seed}.json')
                require(record == final['arms'][arm]['individual'][seed]
                        and record['arm'] == arm and record['seed'] == seed, 'seed receipt mismatch')
                path = training / f'{arm}-seed{seed}.pt'
                require(digest(path) == record['checkpoint_sha256'], 'checkpoint changed')
                model = build_model(arm, normalization)
                model.load_state_dict(torch.load(path, map_location='cpu', weights_only=True), strict=True)
                model.eval(); models.append(model)
                self.checkpoint_hashes[str(path)] = record['checkpoint_sha256']
            self.models[arm] = models
        require(digest(X2) == X2_SHA, 'X2-B map anchor changed')
        import xgboost as xgb
        self.xgb = xgb
        self.map_model = xgb.Booster(params={'nthread': 1}); self.map_model.load_model(X2)

    def base(self, row):
        values = [float(x) for x in row['features'].split(',')]
        require(len(values) == 1017 and all(math.isfinite(v) for v in values), 'invalid rich feature row')
        return [values[i] for i in self.indices]

    def direct(self, rows):
        if not rows: return {'S1': {}, 'S2': {}}
        identities = list(rows)
        encoded = []
        for identity in identities:
            row = rows[identity]
            require(row['screenContents']['screen'] in PROVISIONAL_MASK, 'unsupported direct model screen')
            encoded.append(encode_state(self.base(row), row['screenContents'], row['candidateKeys']))
        cache = pack_encoded(encoded)
        result = {}
        for arm, models in self.models.items():
            mean = np.mean([predict(m, cache, device='cpu') for m in models], axis=0, dtype=np.float64)
            require(mean.shape == (len(identities),) and np.isfinite(mean).all()
                    and ((mean >= 0) & (mean <= 1)).all(), 'invalid ensemble probabilities')
            result[arm] = dict(zip(identities, map(float, mean)))
        return result

    def map(self, rows):
        if not rows: return {}
        ids = list(rows)
        matrix = np.asarray([self.base(rows[i]) for i in ids], dtype=np.float32)
        value = self.map_model.predict(self.xgb.DMatrix(matrix, feature_names=self.names))
        require(value.shape == (len(ids),) and np.isfinite(value).all()
                and ((value >= 0) & (value <= 1)).all(), 'invalid X2-B map predictions')
        return dict(zip(ids, map(float, value)))

    def verify_unchanged(self):
        check_hashes(self.prereg['code']); check_hashes(self.checkpoint_hashes)
        require(digest(X2) == X2_SHA, 'X2-B changed while scoring')


def summaries(values, metadata, reps):
    result = {}
    groups = {'overall': list(values)}
    for screen in PROVISIONAL_MASK:
        groups['screen:' + screen] = [k for k in values if metadata[k]['screenContents']['screen'] == screen]
    for name, ids in groups.items():
        if not ids:
            result[name] = {'status': 'NO_APPLICABLE_STATES', 'n': 0}; continue
        result[name] = cluster_mean(np.asarray([values[k] for k in ids]),
                                   np.asarray([k[0] for k in ids]), reps, 379)
        result[name]['state_count'] = len(ids)
    return result


def resource_report(probes, recovered_protocol_path, scorer, output, reps):
    manifest = load(probes / 'variants/manifest.jsonl')
    final, receipt = load(probes / 'result.json'), load(probes / 'receipt.json')
    require(final['status'] == 'PASS' and digest(probes / 'variants/manifest.jsonl') == final['manifest_sha256'],
            'resource probes incomplete/changed')
    require(receipt['recovery_protocol_sha256'] == digest(recovered_protocol_path), 'probe/recovery protocol mismatch')
    recovery_protocol = load(recovered_protocol_path)
    require(receipt['binary_sha256'] == recovery_protocol['runtime_hashes'][recovery_protocol['s0_binary']],
            'probe binary differs from frozen actual-S0 runtime')
    selected_path = probes / 'selected.jsonl'
    require(digest(selected_path) == receipt['selected_sha256'], 'selected probe states changed')
    selected = keyed_jsonl(selected_path)
    corpus = DecisionCorpus()
    require(len(selected) == 1024 and {k[0] for k in selected} == set(corpus.expected_sources('VALIDATION')),
            'wrong probe VALIDATION population')
    require(Counter(r['screenContents']['screen'] for r in selected.values()) == Counter({s: 256 for s in PROVISIONAL_MASK}),
            'wrong probe family population')
    require(manifest['schema'] == 'screen-leaf-resource-probe-export-v1' and manifest['inputRows'] == 1024
            and manifest['split'] == 'VALIDATION', 'probe manifest contract mismatch')
    require(set(final['variants']) == set(manifest['variantRows']) and CORE <= set(final['variants']),
            'probe variant population mismatch')
    values = {'S0': {}, 'S1': {}, 'S2': {}}
    variant_states, identity_rng = {}, {}
    # Required potion populations follow distinct held IDs inside active slots.
    held = {k: set(r['snapshot']['game']['potions'][:r['snapshot']['game']['potionCapacity']]) - {1}
            for k, r in selected.items()}
    require(all(all(2 <= potion <= 43 for potion in ids) for ids in held.values()), 'invalid active potion identity')
    expected_potion_names = {'remove_potion_' + str(potion) for ids in held.values() for potion in ids}
    require(set(final['variants']) == CORE | expected_potion_names, 'missing or unexpected distinct-potion variants')
    for name in ['identity'] + sorted(set(final['variants']) - {'identity'}):
        entry = final['variants'][name]
        path, pred = probes / 'variants' / (name + '.jsonl'), probes / (name + '-S0.jsonl')
        require(digest(path) == entry['snapshot_sha256'] and digest(pred) == entry['predictions_sha256'],
                'probe numerical artifact changed')
        rows = keyed_jsonl(path)
        require(len(rows) == entry['rows'] == manifest['variantRows'][name], 'probe row count mismatch')
        if name in CORE:
            require(set(rows) == set(selected), 'incomplete core resource population')
        else:
            require(name.startswith('remove_potion_'), 'unknown resource variant')
            potion = int(name.removeprefix('remove_potion_'))
            require(set(rows) == {k for k in selected if potion in held[k]}, 'incomplete potion resource population')
        for identity, row in rows.items():
            require(row['probe']['name'] == name and row['probe']['identityPreservedForS0Rng'] is True,
                    'variant metadata mismatch')
            require(row['screenContents']['screen'] == selected[identity]['screenContents']['screen'],
                    'probe screen family changed')
        values['S0'][name], rng = predictions(pred, rows)
        if name == 'identity': identity_rng = rng
        else: require(all(rng[k] == identity_rng[k] for k in rows), 'resource RNG not paired')
        direct = scorer.direct(rows)
        for arm in ('S1', 'S2'): values[arm][name] = direct[arm]
        variant_states[name] = rows
    reports = {}
    s0 = values['S0']
    def s0_ok(identity, *names):  # Pairwise: an S0 fail-closed variant drops the state from every arm.
        return all(identity in s0[name] for name in names)
    unsupported = {name: sum(1 for k in variant_states[name] if k not in s0[name]) for name in s0}
    for arm, v in values.items():
        baseline = v['identity']
        hp, gold, feed, maximum, potion = {}, {}, {}, {}, {}
        for identity in selected:
            if s0_ok(identity, 'hp_plus', 'hp_minus'):
                hp[identity] = (v['hp_plus'][identity] - v['hp_minus'][identity]) / 10.0
            distance = variant_states['gold_plus'][identity]['probe']['actualPairDistance']
            require(distance > 0 and distance == variant_states['gold_minus'][identity]['probe']['actualPairDistance'],
                    'invalid gold denominator')
            if s0_ok(identity, 'gold_plus', 'gold_minus'):
                gold[identity] = (v['gold_plus'][identity] - v['gold_minus'][identity]) / distance
            if not s0_ok(identity, 'identity'): continue
            if s0_ok(identity, 'feed_like'): feed[identity] = v['feed_like'][identity] - baseline[identity]
            if s0_ok(identity, 'max_only'): maximum[identity] = v['max_only'][identity] - baseline[identity]
            losses = [baseline[identity] - score[identity] for name, score in v.items()
                      if name.startswith('remove_potion_') and identity in score and s0_ok(identity, name)]
            if losses: potion[identity] = float(np.mean(losses))
        reports[arm] = {name: summaries(data, selected, reps) for name, data in
                       [('hp_local_slope_fixed_denominator_10', hp), ('gold_slope_per_actual_gold', gold),
                        ('feed_like_delta', feed), ('max_hp_only_delta', maximum),
                        ('average_distinct_held_potion_loss', potion)]}
    write_new(output / 'resource-diagnostics.json', {
        'classification': 'DIAGNOSTIC_ONLY_NOT_A_QUALIFICATION_GATE', 'arms': reports,
        'hp_contract': 'clamped plus/minus5 with fixed denominator10, matching #334',
        'gold_contract': 'clamped plus/minus25 divided by actual pair distance',
        'potion_contract': 'mean over distinct held potion IDs within state, then source-cluster bootstrap',
        'exogenous_offers': 'preserved by reviewed native exporter; legal actions and duplicated inventory recomputed',
        's0_unsupported_rows_by_variant': {k: n for k, n in unsupported.items() if n},
        'states_without_potions': sum(not any(k in variant_states[n] for n in variant_states if n.startswith('remove_potion_')) for k in selected),
        'probe_result_sha256': digest(probes / 'result.json'), 'bootstrap_replicates': reps})
    return {'resource_result_sha256': digest(output / 'resource-diagnostics.json')}


def native_call(protocol, command, args, output, deadline, input_binding=None):
    remaining = int(deadline - time.monotonic())
    require(remaining > 0, 'diagnostic native wall budget exhausted')
    check_hashes(protocol['runtime_hashes'])
    binary = Path(protocol['s0_binary'])
    sha = clean_sha()
    env = dict(protocol['s0_environment']); env['STS_EXECUTABLE_GIT_SHA'] = sha
    argv = ['bash', str(REPO / 'tools/seed_guard.sh'), str(binary), command, *map(str, args)]
    input_path = Path(args[0]); input_sha = digest(input_path)
    if input_binding: verify_selection(input_binding)
    else: verify_current(input_path, input_sha)
    write_new(output / (command + '-receipt.json'), {'argv': argv, 'env': env,
              'input_sha256': input_sha, 'input_selection': input_binding,
              'helper_sha256': digest(REPO / 'tools/screen_leaf_import_379.py'),
              'coordinator_sha': sha, 'binary_sha256': digest(binary),
              'wall_budget_seconds': remaining, 'replicates': 1 if command == 'screenleafs0' else None})
    try:
        with (output / (command + '.stdout')).open('x') as out, (output / (command + '.stderr')).open('x') as err:
            subprocess.run(['timeout', '-k', '10', str(remaining), *argv], cwd=REPO, env=env,
                           stdout=out, stderr=err, check=True)
    finally:
        require(digest(input_path) == input_sha, 'native input changed during call')
        if input_binding: verify_selection(input_binding)
        else: verify_current(input_path, input_sha)
        check_hashes(protocol['runtime_hashes'])


def sibling_report(protocol, sources, scorer, output, reps, native_seconds, maximum_states):
    branch_records, inputs, excluded = {}, {}, Counter()
    total_groups = set()
    decorations = []
    for source in sources:
        seed = source['seed']
        with source['branches'].open(newline='') as stream:
            reader = csv.DictReader(stream)
            require(reader.fieldnames == BRANCH_HEADER, 'branch outcome schema mismatch')
            for r in reader:
                require(int(r['sourceSeed']) == seed, 'branch outcome has foreign source')
                branch_key = (seed, r['branchId'])
                require(branch_key not in branch_records, 'ambiguous branch label identity')
                require(r['valid'] in ('0', '1'), 'invalid branch validity')
                require(r['valid'] == '0' or r['won'] in ('0', '1'), 'nonbinary valid branch outcome')
                record = {'sourceSeed': seed, 'branchId': r['branchId'],
                          'decisionIdx': int(r['decisionIdx']), 'type': r['type'],
                          'optionKey': r['optionKey'], 'won': int(r['won']) if r['valid'] == '1' else None, 'valid': r['valid'] == '1'}
                branch_records[branch_key] = record
                total_groups.add((seed, record['decisionIdx'], record['type']))
        decoration = decorate_replay(Path(protocol['corpus']), source['source'], source['custody'],
                                      output / (str(seed) + '-temporal.jsonl'), kind='temporal')
        decorations.append(decoration)
        with Path(verify_decoration(decoration)['decorated']).open() as stream:
            for line in stream:
                trajectory = json.loads(line)
                require(trajectory['sourceSeed'] == seed and trajectory['schema'] == 'screen_leaf_temporal_v1',
                        'temporal source mismatch')
                post = trajectory['forcedPostAction']
                if post is None: continue  # source run has no forced poststate
                branch_key = (seed, trajectory['branchId'])
                require(branch_key in branch_records, 'poststate lacks exact branch label join')
                branch = branch_records[branch_key]
                require(post['branchId'] == branch_key[1] and post['sourceDecisionIdx'] == branch['decisionIdx'],
                        'forced poststate decision/branch mismatch')
                if not branch['valid']:
                    excluded[(branch['type'], 'INVALID_BRANCH_OUTCOME')] += 1; continue
                identity = (seed, branch_key[1], -1)
                require(identity not in inputs, 'duplicate forced poststate')
                inputs[identity] = post_input(trajectory)
    require(inputs and len(inputs) <= maximum_states, 'poststate population empty/over frozen bound; never truncate')
    write_new(output / 'sibling-protocol.json', {
        'definition': 'immediate after forced semantic action before resumeContinuation',
        'rowIdx': '-1 synthetic RNG identity only; never predictive feature',
        'poststate_count': len(inputs), 'maximum_states': maximum_states,
        'native_wall_budget_seconds': native_seconds,
        'routing': {'MAP': 'X2-B for all arms', 'TERMINAL': 'exact 0/1 for all arms',
                    'SUPPORTED_DECISION': 'S0 actual current evaluator; S1/S2 direct four-family else same S0',
                    'EXCLUDED_BATTLE': 'exclude', 'EXCLUDED_UNSUPPORTED': 'exclude'},
        'failure_rule': 'fail closed; no retry, no nearest-MAP or common-prestate substitute'})
    input_path = output / 'sibling-inputs.jsonl'
    with input_path.open('x') as stream:
        for row in inputs.values(): stream.write(json.dumps(row, separators=(',', ':')) + '\n')
    input_binding = bind_selection(input_path, decorations, temporal=True)
    deadline = time.monotonic() + native_seconds
    projected_path = output / 'sibling-projected.jsonl'
    native_call(protocol, 'screenleafproject', [input_path, projected_path, len(inputs)], output, deadline, input_binding)
    projected = keyed_jsonl(projected_path)
    require(set(projected) == set(inputs), 'poststate projection identity population mismatch')
    supported, maps, exact, route_counts = {}, {}, {}, Counter()
    for identity, row in projected.items():
        branch = branch_records[identity[:2]]
        verify_projected(inputs[identity], row)
        status = row['projectionStatus']; route_counts[status] += 1
        if status == 'SUPPORTED_DECISION': supported[identity] = row
        elif status == 'MAP': maps[identity] = row
        elif status == 'TERMINAL':
            require(row['terminalValue'] in (0, 1), 'nonexact terminal value'); exact[identity] = float(row['terminalValue'])
        elif status in ('EXCLUDED_BATTLE', 'EXCLUDED_UNSUPPORTED'): excluded[(branch['type'], status)] += 1
        else: raise ValueError('unknown poststate projection status')
    baseline = {}
    if supported:
        s0_input = output / 'sibling-supported.jsonl'
        with s0_input.open('x') as stream:
            for row in supported.values(): stream.write(json.dumps(row, separators=(',', ':')) + '\n')
        s0_path = output / 'sibling-S0.jsonl'
        native_call(protocol, 'screenleafs0', [s0_input, s0_path, len(supported), 1], output, deadline)
        baseline, _ = predictions(s0_path, supported)
        for identity in supported:
            if identity not in baseline:  # S0 fail-closed: drop from every arm's pairs.
                excluded[(branch_records[identity[:2]]['type'], 'S0_UNSUPPORTED')] += 1
    baseline.update(scorer.map(maps)); baseline.update(exact)
    direct_rows = {k: r for k, r in supported.items() if r['screenContents']['screen'] in PROVISIONAL_MASK}
    direct = scorer.direct(direct_rows)
    scores = {'S0': baseline}
    for arm in ('S1', 'S2'):
        scores[arm] = dict(baseline); scores[arm].update(direct[arm])
    groups = defaultdict(list)
    for identity in baseline:
        b = branch_records[identity[:2]]
        groups[(b['sourceSeed'], b['decisionIdx'], b['type'])].append(identity)
    pairs = []
    for group, identities in groups.items():
        # Duplicate options would create false sibling pairs; reject, do not dedupe.
        options = [branch_records[i[:2]]['optionKey'] for i in identities]
        require(len(options) == len(set(options)), 'duplicate sibling action within decision group')
        for a, b in itertools.combinations(identities, 2):
            ya, yb = branch_records[a[:2]]['won'], branch_records[b[:2]]['won']
            if ya != yb: pairs.append((group, a, b, ya > yb))
    reports = {}
    for arm, values in scores.items():
        metrics = {}
        # Retain every observed original decision type, even when exclusion
        # or concordant outcomes leave it with zero discordant joined pairs.
        families = sorted({b['type'] for b in branch_records.values()})
        for family in ['overall', *families]:
            chosen = [p for p in pairs if family == 'overall' or p[0][2] == family]
            if not chosen:
                metrics[family] = {'status': 'NO_DISCORDANT_JOINED_SIBLINGS', 'pairs': 0}; continue
            accuracy = [0.5 if values[a] == values[b] else float((values[a] > values[b]) == a_won)
                        for _, a, b, a_won in chosen]
            source_ids = [group[0] for group, _, _, _ in chosen]
            metrics[family] = cluster_mean(np.asarray(accuracy), np.asarray(source_ids), reps, 379)
            metrics[family]['pairs'] = len(chosen)
        reports[arm] = metrics
    # Missing poststates are explicit, not replaced by source or MAP approximations.
    for branch_key, b in branch_records.items():
        if (branch_key[0], branch_key[1], -1) not in inputs and b['valid']:
            excluded[(b['type'], 'NO_FORCED_POSTACTION_SNAPSHOT')] += 1
    write_new(output / 'sibling-diagnostics.json', {
        'classification': 'DIAGNOSTIC_ONLY_NOT_A_QUALIFICATION_GATE', 'arms': reports,
        'routing_counts': dict(route_counts), 'direct_family_states': len(direct_rows),
        'fallback_supported_states': len(supported) - len(direct_rows),
        'original_decision_groups': len(total_groups), 'scored_decision_groups': len(groups),
        'discordant_pairs': len(pairs), 'tie_credit': 0.5,
        'pairs_with_at_least_one_direct_model_state': sum(a in direct_rows or b in direct_rows for _, a, b, _ in pairs),
        'pair_projection_statuses': dict(Counter('/'.join(sorted([projected[a]['projectionStatus'], projected[b]['projectionStatus']]))
                                                  for _, a, b, _ in pairs)),
        'exclusions': {family + '/' + reason: count for (family, reason), count in excluded.items()},
        'input_sha256': digest(input_path), 'projection_sha256': digest(projected_path),
        's0_sha256': digest(output / 'sibling-S0.jsonl') if supported else None,
        'bootstrap_replicates': reps})


def run(training, recovered, probes, output, reps, native_seconds, maximum_states):
    require(Path(__file__).resolve().parent == REPO / 'tools', 'staging driver must be reviewed/copied/committed before execution')
    sha = clean_sha()
    require(reps == 2000 and native_seconds > 0 and maximum_states > 0, 'invalid frozen diagnostic bounds')
    corpus = DecisionCorpus()
    protocol, sources = recovery_evidence(recovered)
    first_manifest = load(sources[0]['source']['manifest'])
    full_header = first_manifest['stateFeatures']['header']
    import hashlib
    require(hashlib.sha256(full_header.encode()).hexdigest() == HEADER_SHA, 'full feature header identity mismatch')
    scorer = Scorer(training, corpus.feature_names, full_header.split(','))
    output.mkdir(parents=True, exist_ok=False)
    input_hashes = {str(p): digest(p) for p in [training / 'preregistered.json', training / 'result.json',
                    training / 'dataset.json', training / 'normalization.npz', recovered / 'protocol.json',
                    recovered / 'result.json', probes / 'receipt.json', probes / 'result.json']}
    write_new(output / 'protocol.json', {
        'status': 'VALIDATION_DIAGNOSTICS_ONLY', 'coordinator_sha': sha,
        'driver_sha256': digest(Path(__file__)), 'inputs': input_hashes,
        'recovery_sources': [{'seed': s['seed'], 'source_manifest_sha256': s['source']['manifest_sha256'],
                             'source_result_sha256': s['result_sha256'],
                             'temporal_sha256': digest(s['temporal']),
                             'branches_sha256': digest(s['branches'])} for s in sources],
        'replacement_mask': PROVISIONAL_MASK, 'checkpoint_hashes': scorer.checkpoint_hashes,
        'map_ubj_sha256': X2_SHA, 'bootstrap_replicates': reps,
        'native_wall_budget_seconds': native_seconds, 'maximum_sibling_states': maximum_states,
        'test_access': 'FORBIDDEN; complete frozen VALIDATION population verified first',
        'no_selection': 'No candidate selection, calibration tolerance, mask change, TEST latch or qualification'})
    resource_report(probes, recovered / 'protocol.json', scorer, output, reps)
    sibling_report(protocol, sources, scorer, output, reps, native_seconds, maximum_states)
    clean_sha(sha); check_hashes(input_hashes); scorer.verify_unchanged()
    write_new(output / 'result.json', {'status': 'VALIDATION_DIAGNOSTICS_COMPLETE_NOT_QUALIFIED',
        'resource_sha256': digest(output / 'resource-diagnostics.json'),
        'sibling_sha256': digest(output / 'sibling-diagnostics.json'),
        'protocol_sha256': digest(output / 'protocol.json')})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--training', required=True, type=Path)
    p.add_argument('--recovered', required=True, type=Path)
    p.add_argument('--probes', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--bootstrap-replicates', type=int, default=2000)
    p.add_argument('--native-seconds', type=int, default=1800)
    p.add_argument('--maximum-sibling-states', type=int, default=20000)
    a = p.parse_args()
    run(a.training.resolve(), a.recovered.resolve(), a.probes.resolve(), a.output.resolve(),
        a.bootstrap_replicates, a.native_seconds, a.maximum_sibling_states)
