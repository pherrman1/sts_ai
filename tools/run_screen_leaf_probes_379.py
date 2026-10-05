#!/usr/bin/env python3
"""Bounded VALIDATION resource counterfactuals with paired actual-S0 values."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

from audit_screen_leaf_379 import digest
from screen_leaf_import_379 import (decorate_replay, verify_decoration, bind_selection,
                                    verify_selection, verify_current)
from screen_leaf_data_379 import DecisionCorpus, PROVISIONAL_MASK
from run_screen_leaf_validation_379 import verify_replay, clean_sha, check_hashes, frozen_sources

REPO = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def identity(row):
    return row['sourceSeed'], row['branchId'], row['rowIdx']


def run(recovered, output):
    sha = clean_sha()
    protocol, result = load(recovered / 'protocol.json'), load(recovered / 'result.json')
    if result['status'] != 'PASS' or result['protocol_sha256'] != digest(recovered / 'protocol.json'):
        raise ValueError('full VALIDATION recovery required')
    sources = frozen_sources(Path(protocol['corpus']))
    by_seed = {s['seed']: s for s in sources}
    if len(result['results']) != 155 or {r['seed'] for r in result['results']} != set(by_seed):
        raise ValueError('wrong full VALIDATION source set')
    output.mkdir(parents=True, exist_ok=False)
    decorations = []
    candidates = defaultdict(lambda: defaultdict(list))
    for item in result['results']:
        if item['status'] != 'PASS': raise ValueError('failed source in aggregate')
        seed = item['seed']
        replay = Path(item['replay']['directory'])
        if verify_replay(replay, by_seed[seed]) != item['replay']:
            raise ValueError('recovery custody changed')
        binding = decorate_replay(Path(protocol['corpus']), by_seed[seed], item['replay'],
                                   output / (str(seed) + '-snapshots.jsonl'))
        decorations.append(binding)
        with Path(verify_decoration(binding)['decorated']).open() as stream:
            for line in stream:
                row = json.loads(line)
                family = row['screenContents']['screen']
                if family not in PROVISIONAL_MASK: continue
                if row['sourceSeed'] != seed: raise ValueError('snapshot source mismatch')
                identity_material = f"{seed}:{row['branchId']}:{row['rowIdx']}"
                rank = hashlib.sha256(('screen-leaf-379-resource-v1:' + identity_material).encode()).hexdigest()
                candidates[family][seed].append((rank, line))
    selected = []
    for family in PROVISIONAL_MASK:
        groups = candidates[family]
        if set(groups) != set(by_seed): raise ValueError('probe family misses VALIDATION source')
        for rows in groups.values(): rows.sort()
        family_rows, depth = [], 0
        while len(family_rows) < 256:
            previous = len(family_rows)
            for seed in sorted(groups):
                if depth < len(groups[seed]) and len(family_rows) < 256:
                    family_rows.append(groups[seed][depth][1])
            if len(family_rows) == previous: raise ValueError('insufficient probe states')
            depth += 1
        selected.extend(family_rows)
    input_path = output / 'selected.jsonl'
    input_path.write_text(''.join(selected))
    input_binding = bind_selection(input_path, decorations)
    selected_rows = {identity(r): r for r in map(json.loads, selected)}
    if len(selected_rows) != 1024: raise ValueError('duplicate selected probe identity')
    binary = Path(protocol['s0_binary'])
    check_hashes(protocol['runtime_hashes'])
    env = dict(protocol['s0_environment'])
    env['STS_EXECUTABLE_GIT_SHA'] = sha
    variants = output / 'variants'
    argv = ['bash', str(REPO / 'tools/seed_guard.sh'), str(binary), 'screenleafprobes', str(input_path), str(variants), '1024']
    write_new(output / 'receipt.json', {'source_sha': sha, 'recovery_protocol_sha256': digest(recovered / 'protocol.json'),
              'input_selection': input_binding, 'helper_sha256': digest(REPO / 'tools/screen_leaf_import_379.py'),
              'binary_sha256': digest(binary), 'selected_sha256': digest(input_path), 'states': 1024,
              'states_per_family': 256, 'source_count_per_family': 155, 'argv': argv, 'env': env,
              'per_source_counts': {str(seed): sum(key[0] == seed for key in selected_rows) for seed in sorted(by_seed)},
              'wall_budget_seconds': 1800, 'replicates': 1,
              'purpose': 'Diagnostic resource sensitivity; exogenous offers fixed, duplicate inventory and legal actions recomputed',
              'failure_rule': 'Stop on any error; no retries, filtering or quality gates; TEST forbidden'})
    start = time.monotonic()
    verify_selection(input_binding)
    try:
        with (output / 'export.stdout').open('x') as out, (output / 'export.stderr').open('x') as err:
            subprocess.run(['timeout', '-k', '10', '300', *argv], env=env, cwd=REPO, stdout=out, stderr=err, check=True)
    finally:
        verify_selection(input_binding)
        check_hashes(protocol['runtime_hashes'])
    manifest = load(variants / 'manifest.jsonl')
    core = {'identity', 'hp_minus', 'hp_plus', 'gold_minus', 'gold_plus', 'feed_like', 'max_only'}
    if manifest['schema'] != 'screen-leaf-resource-probe-export-v1' or manifest['split'] != 'VALIDATION' or manifest['inputRows'] != 1024:
        raise ValueError('probe export manifest differs')
    if not core <= set(manifest['variantRows']) or any(manifest['variantRows'][key] != 1024 for key in core):
        raise ValueError('incomplete core probe variants')
    export_manifest_sha = digest(variants / 'manifest.jsonl')
    exported_inputs = {name: digest(variants / (name + '.jsonl')) for name in manifest['variantRows']}
    for name, expected in exported_inputs.items(): verify_current(variants / (name + '.jsonl'), expected)
    write_new(output / 'export-result.json', {'input_selection': input_binding,
              'manifest_sha256': export_manifest_sha, 'variant_sha256': exported_inputs,
              'binary_sha256': digest(binary), 'source_sha': sha})
    results = {}
    paired_seeds = {}
    order = ['identity'] + sorted(set(manifest['variantRows']) - {'identity'})
    for name in order:
        count = manifest['variantRows'][name]
        remaining = int(1800 - (time.monotonic() - start))
        if remaining <= 0: raise ValueError('probe wall budget exhausted')
        path = variants / (name + '.jsonl')
        input_sha = exported_inputs[name]
        verify_current(path, input_sha)
        states = {}
        for line in path.open():
            row = json.loads(line)
            key = identity(row)
            if key in states or key not in selected_rows or row['probe']['name'] != name:
                raise ValueError('incorrect variant snapshot identity/name')
            if name not in core:
                if not name.startswith('remove_potion_'): raise ValueError('unknown probe variant')
                potion_id = int(name.removeprefix('remove_potion_'))
                if row['probe']['potionId'] != potion_id or potion_id not in selected_rows[key]['snapshot']['game']['potions']:
                    raise ValueError('potion probe metadata differs from original held inventory')
            states[key] = row
        if len(states) != count or (name in core and set(states) != set(selected_rows)):
            raise ValueError('incorrect variant snapshot population')
        target = output / (name + '-S0.jsonl')
        argv = ['bash', str(REPO / 'tools/seed_guard.sh'), str(binary), 'screenleafs0', str(path), str(target), str(count), '1']
        write_new(output / (name + '-S0-receipt.json'), {'argv': argv, 'env': env,
                  'input_sha256': input_sha, 'binary_sha256': digest(binary),
                  'export_manifest_sha256': export_manifest_sha,
                  'export_result_sha256': digest(output / 'export-result.json'),
                  'historical_input_selection': input_binding, 'replicates': 1})
        verify_current(path, input_sha)
        if digest(variants / 'manifest.jsonl') != export_manifest_sha: raise ValueError('export manifest changed')
        check_hashes(protocol['runtime_hashes'])
        try:
            with (output / (name + '.stdout')).open('x') as out, (output / (name + '.stderr')).open('x') as err:
                subprocess.run(['timeout', '-k', '10', str(remaining), *argv], cwd=REPO, env=env, stdout=out, stderr=err, check=True)
        finally:
            verify_current(path, input_sha)
            if digest(variants / 'manifest.jsonl') != export_manifest_sha: raise ValueError('export manifest changed')
            check_hashes(protocol['runtime_hashes'])
        rows = [json.loads(line) for line in target.open()]
        if len(rows) != count: raise ValueError('incomplete probe S0')
        observed = set()
        for row in rows:
            key = identity(row)
            if key not in states or key in observed: raise ValueError('incorrect S0 probe identity')
            observed.add(key)
            if len(row['values']) != 1 or len(row['rngSeeds']) != 1 or not math.isfinite(row['values'][0]) or not 0 <= row['values'][0] <= 1:
                raise ValueError('invalid S0 probe prediction')
            if name == 'identity': paired_seeds[key] = row['rngSeeds']
            elif row['rngSeeds'] != paired_seeds[key]: raise ValueError('unpaired S0 RNG')
        if observed != set(states): raise ValueError('missing S0 probe states')
        results[name] = {'rows': count, 'snapshot_sha256': input_sha, 'predictions_sha256': digest(target),
                         's0_receipt_sha256': digest(output / (name + '-S0-receipt.json'))}
    check_hashes(protocol['runtime_hashes'])
    write_new(output / 'result.json', {'status': 'PASS', 'variants': results, 'wall_seconds': time.monotonic() - start,
              'manifest_sha256': export_manifest_sha, 'input_selection': input_binding,
              'export_result_sha256': digest(output / 'export-result.json')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recovered', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.recovered.resolve(), args.output.resolve())
