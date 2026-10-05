#!/usr/bin/env python3
"""Narrow custody and TRAIN/VALIDATION DECISION audit; never opens TEST CSV rows.

Only frozen manifest metadata and opaque DECISION file hashes are inspected for
TEST. Does not invoke the historical corpus validator or load other sink tables.
"""
import argparse
import ast
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import time

EXPECTED = 'ae56f9633ce8da8a72e341978d707c9f145c1f1b6479afa438067af5570dfa00'
PREFIX = ['sourceSeed', 'branchId', 'deviationIdx', 'rowIdx', 'decisionIdx', 'act', 'floor', 'screen', 'teacherId']
SCREENS = {'event': 1, 'rewards': 2, 'boss_relic': 3, 'selector': 4, 'treasure': 6, 'rest': 7, 'shop': 8}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def source_split_function():
    # Use the exact maintained function without importing numerical dependencies
    # or the legacy corpus-validation access layer.
    path = Path(__file__).resolve().parent / 'vwin_refresh_dataset.py'
    tree = ast.parse(path.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'source_split')
    scope = {'hashlib': hashlib}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), scope)
    return scope['source_split'], digest(path)


def shape(value):
    if isinstance(value, dict):
        return {k: shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return {'array_element_types': sorted(set(json.dumps(shape(v), sort_keys=True) for v in value))}
    return type(value).__name__


def fresh():
    return {'sources': set(), 'observed_sources': set(), 'identities': set(), 'rows': 0, 'wins': 0, 'row_bytes': 0,
            'source_vs_branch_rows': Counter(), 'candidate_count_distribution': Counter(),
            'semantic_enumeration': Counter(), 'screenContents_schema_variants': Counter(),
            'capture_log': Counter(), 'capture_errors': Counter()}


def audit(index):
    started = time.monotonic()
    require(digest(index) == EXPECTED, 'corpus index SHA mismatch')
    corpus = json.loads(index.read_text())
    require(corpus['schemaVersion'] == 'vwin_refresh_corpus_v1', 'corpus schema mismatch')
    split, split_code_hash = source_split_function()
    seeds = corpus['sourceSeeds']
    require(len(set(seeds)) == 1024, 'source identities mismatch')
    counts = dict(Counter(split(s) for s in seeds))
    require(counts == {'TRAIN': 696, 'VALIDATION': 155, 'TEST': 173}, 'source split mismatch')
    producers = {tuple(p[k] for k in ('producerGitSha', 'producerExecutableSha256', 'teacherManifestSha256', 'teacherId')) for p in corpus['allowedProducers']}
    stats = defaultdict(fresh)
    custody = []
    access = {s: {'decision_files_hashed': 0, 'decision_bytes_hashed': 0, 'csv_headers_parsed': 0, 'csv_rows_parsed': 0} for s in ('TRAIN', 'VALIDATION', 'TEST')}
    seen_seeds = set()
    feature_header_hash = None
    for number, component in enumerate(corpus['components']):
        path = (index.parent / component['manifest']).resolve()
        require(digest(path) == component['sha256'], f'manifest hash mismatch: {path}')
        manifest = json.loads(path.read_text())
        require(manifest['schemaVersion'] == 'vwin_refresh_334_v1', 'component schema mismatch')
        require(tuple(manifest[k] for k in ('producerGitSha', 'producerExecutableSha256', 'teacherManifestSha256', 'teacherId')) in producers, 'producer mismatch')
        spec = manifest['seedSpec']
        require(spec['count'] == 1, 'single-source shards required to enforce TEST sealing')
        seed = spec['start']
        require(seed in seeds and seed not in seen_seeds, 'duplicate or unknown component source')
        seen_seeds.add(seed)
        which = split(seed)
        require(manifest['split'] == {'branchesInheritSourceSeed': True, 'domain': 'vwin-refresh-334-v1:{seed}', 'prefixBytes': 4, 'rule': 'source_seed_sha256_prefix_v1', 'trainLt': .7, 'validationLt': .85}, 'split contract mismatch')
        features = manifest['stateFeatures']
        header_hash = hashlib.sha256(features['header'].encode()).hexdigest()
        require(header_hash == features['headerSha256'], 'feature header hash mismatch')
        require(features['count'] == 1017 and len(features['header'].split(',')) == 1017, 'feature count mismatch')
        if feature_header_hash is None:
            feature_header_hash = header_hash
        require(feature_header_hash == header_hash, 'heterogeneous feature header')
        sink = manifest['decisionSink']
        require(sink['enabled'] is True and sink['schema'] == 'vwin_decision_334_v1' and sink['screenContentsEncoding'] == 'canonical_json_public_state_v1' and sink['candidatesEncoding'] == 'canonical_semantic_keys_with_chosen_v1', 'DECISION schema mismatch')
        csv_path = Path(str(path).removesuffix('.manifest.json') + '.decision.csv')
        file_hash = digest(csv_path)
        require(file_hash == manifest['outputs']['decision.csv'], f'DECISION hash mismatch: {csv_path}')
        access[which]['decision_files_hashed'] += 1
        access[which]['decision_bytes_hashed'] += csv_path.stat().st_size
        custody.append({'sourceSeed': seed, 'split': which, 'manifest': str(path), 'manifest_sha256': component['sha256'], 'decision_sha256': file_hash})
        if which == 'TEST':
            continue  # No CSV header/row parsing or TEST outcome statistics.
        logs = {}
        for trajectory in sink['trajectories']:
            require(trajectory['sourceSeed'] == seed, 'trajectory source mismatch')
            branch = trajectory['branchId']
            for item in trajectory['decisionLog']:
                st = stats[which, item['screen']]
                st['observed_sources'].add(seed)
                st['capture_log']['total'] += 1
                error = item.get('error', '')
                if error:
                    require(item['rowIdx'] == -1, 'capture error has sink row')
                    st['capture_errors'][error] += 1
                elif item['optionCount'] <= 1:
                    require(item['rowIdx'] == -1, 'singleton has sink row')
                    st['capture_log']['singleton_or_empty_not_captured'] += 1
                else:
                    ident = (branch, item['rowIdx'])
                    require(ident not in logs, 'duplicate logged identity')
                    logs[ident] = item
        seen = set()
        with csv_path.open(newline='') as stream:
            reader = csv.reader(stream)
            header = next(reader)
            access[which]['csv_headers_parsed'] += 1
            require(header == PREFIX + features['header'].split(',') + ['screenContents', 'candidates', 'won'], 'DECISION CSV header mismatch')
            for row in reader:
                access[which]['csv_rows_parsed'] += 1
                require(len(row) == len(header), 'row width mismatch')
                require(int(row[0]) == seed, 'row source mismatch')
                ident = (row[1], int(row[3]))
                require(ident in logs and ident not in seen, 'missing or duplicate row/log join')
                seen.add(ident)
                log = logs[ident]
                screen = row[7]
                require(screen == log['screen'] and int(row[4]) == log['decisionIdx'], 'decision identity mismatch')
                require(row[8] == manifest['teacherId'], 'row teacher mismatch')
                contents, candidates = json.loads(row[-3]), json.loads(row[-2])
                require(contents['screen'] == screen and contents['screenState'] == SCREENS[screen], 'contents screen mismatch')
                keys = candidates['optionKeys']
                require(len(keys) == log['optionCount'] and len(keys) > 1 and len(set(keys)) == len(keys), 'candidate identity mismatch')
                require(all(isinstance(k, str) and k.startswith('ooc:v1:') for k in keys), 'candidate key schema mismatch')
                require(candidates['supported'] is True and candidates['complete'] is True, 'incomplete sink enumeration')
                require(candidates['chosenKey'] in keys, 'unresolved chosen key')
                require(row[-1] in ('0', '1'), 'invalid binary label')
                st = stats[which, screen]
                st['sources'].add(seed)
                st['identities'].add((seed,) + ident)
                st['rows'] += 1
                st['wins'] += int(row[-1])
                st['row_bytes'] += sum(len(v.encode()) for v in row) + len(row)
                st['source_vs_branch_rows']['source' if row[1] == 'source' else 'branch'] += 1
                st['candidate_count_distribution'][len(keys)] += 1
                st['semantic_enumeration']['supported_complete'] += 1
                st['screenContents_schema_variants'][json.dumps(shape(contents), sort_keys=True, separators=(',', ':'))] += 1
        require(digest(csv_path) == file_hash, 'DECISION changed during audit')
        require(seen == set(logs), 'missing captured rows')
        require(len(seen) == sink['rows'], 'manifest row count mismatch')
        require(digest(path) == component['sha256'], 'manifest changed during audit')
        if number % 100 == 0:
            print(f'verified {number + 1}/{len(corpus["components"])} components', flush=True)
    require(seen_seeds == set(seeds), 'component coverage mismatch')
    require(digest(index) == EXPECTED, 'index changed during audit')
    result = {}
    for (which, screen), st in sorted(stats.items()):
        st['captured_source_count'] = len(st.pop('sources'))
        st['observed_source_count'] = len(st.pop('observed_sources'))
        st['unique_decision_identities'] = len(st.pop('identities'))
        st['observed_win_rate'] = st['wins'] / st['rows'] if st['rows'] else None
        st['approximate_decoded_bytes_per_row'] = st.pop('row_bytes') / st['rows'] if st['rows'] else None
        result.setdefault(which, {})[screen] = st
    return {'status': 'PASS', 'corpus_index_sha256': EXPECTED, 'source_split_counts': counts,
            'split_implementation_sha256': split_code_hash, 'feature_header_sha256': feature_header_hash,
            'components': custody, 'access_seal': access, 'by_split_screen': result, 'elapsed_seconds': time.monotonic() - started,
            'test_access': 'opaque file hashing and manifest custody metadata only; zero TEST CSV rows parsed',
            'limitations': ['Narrow DECISION custody audit; no full historical validator or runout/legacy joins repeated.',
                'Observed source counts include capture logs; captured source counts include only emitted CSV rows.',
                'Access seal bytes count the initial opaque hash pass; TRAIN/VALIDATION files are also rehashed after parsing.',
                'Win rates are row-weighted and correlated within source/branch; not model quality.',
                'Identity is (sourceSeed, branchId, rowIdx), preserving capture-only decisionIdx=-1.',
                'Missing captures are manifest-reported capture errors and row/log join checks; unlogged producer omissions cannot be inferred.',
                'Decoded bytes approximate payload, excluding CSV quoting overhead and file header.',
                'Schema variants report recursive public JSON field/type structure; empty arrays form distinct variants.',
                'No model inputs selected, no training, no S0 evaluation, no TEST outcome metrics.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'refusing to overwrite audit evidence')
    result = audit(args.corpus)
    result['audit_script_sha256'] = digest(Path(__file__))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(f'PASS: {args.output}', flush=True)


if __name__ == '__main__':
    main()
