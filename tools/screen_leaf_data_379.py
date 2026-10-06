#!/usr/bin/env python3
"""Narrow #379 TRAIN/VALIDATION DECISION access; TEST has no access path.

Feature payloads exclude chosen actions, source identifiers and outcomes. Identity
and label are separate record members used only for grouping/evaluation. This
module does not import or invoke the expensive historical corpus validator.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

if __package__:
    from .audit_screen_leaf_379 import EXPECTED, PREFIX, SCREENS, digest, require, source_split_function
else:
    from audit_screen_leaf_379 import EXPECTED, PREFIX, SCREENS, digest, require, source_split_function

ROOT = Path('/home/philippherrmann/Documents/sts/artifacts/vwin-refresh-334')
DEFAULT_INDEX = ROOT / 'a2a-scale-1024-extra512-8175c9dc-20261002/corpus-mixed-1024.json'
DEFAULT_PREDICTOR = ROOT / 'a3-final1024-x2b-finalist-20261003-49c28d80/tune/X2/predictor.json'
DEFAULT_AUDIT = Path(__file__).resolve().parents[1] / 'docs/experiments/evidence/screen_leaf_379_preflight_20261005/audit.json'
PREDICTOR_SHA = '1bfe52f18862ee5b56f3a65ebaee7acfe06a1d4141e04e9ddffe05408d67039a'
HEADER_SHA = 'd8fdd003636fc00e537320f0406a2c36f890d8ba16edc10cc7c2b0fbdf7ed836'
PROVISIONAL_MASK = ('boss_relic', 'rest', 'shop', 'treasure')
CACHE_SCHEMA = 'screen_leaf_train_validation_rows_v2'


def allowed_split(split):
    # Must be called before even opening a table header or resolving a table.
    require(split in ('TRAIN', 'VALIDATION'), 'DECISION TEST is sealed: only TRAIN/VALIDATION allowed')


def join_availability():
    return {
        'decision_to_map': {
            'status': 'UNAVAILABLE_WITHOUT_VERIFIED_REPLAY_JOIN',
            'reason': 'DECISION rowIdx and MAP rowIdx are separate counters, not a shared timeline. '
                      'MAP has no decisionIdx or predecessor identity. decisions.csv can align the MAP '
                      'subsequence and may prove restricted same-floor joins, but must exclude act transitions and '
                      'unlocated omitted singleton/unresolved DECISION captures; no such join is implemented here.',
            'source': 'apps/one_combat/combat_datasets.cpp: VwinCollector, vwinMapHeader, vwinObservePolicyStep',
        },
        'sibling_post_action': {
            'status': 'UNAVAILABLE_WITHOUT_VERIFIED_REPLAY_JOIN',
            'reason': 'branches.csv identifies sibling groups by sourceSeed+decisionIdx and outcomes, '
                      'but has no immediate post-action state identity. Forced-branch DECISION capture '
                      'starts from the common pre-decision snapshot; its first row is not evidence of '
                      'the requested post-action state. Do not score the common pre-state for ranking.',
            'source': 'apps/one_combat/combat_datasets.cpp: playRun forced branch and vwinCaptureForcedDecision',
        },
    }


class DecisionCorpus:
    def __init__(self, index=DEFAULT_INDEX, audit=DEFAULT_AUDIT, predictor=DEFAULT_PREDICTOR):
        self.index = Path(index).resolve()
        require(digest(self.index) == EXPECTED, 'frozen corpus index identity mismatch')
        corpus = json.loads(self.index.read_text())
        require(corpus['schemaVersion'] == 'vwin_refresh_corpus_v1', 'corpus schema mismatch')
        self.split_fn, self.split_code_sha = source_split_function()
        self.predictor = Path(predictor).resolve()
        require(digest(self.predictor) == PREDICTOR_SHA, 'frozen X2-B feature contract identity mismatch')
        self.feature_names = json.loads(self.predictor.read_text())['feature_names']
        require(len(self.feature_names) == 461 and len(set(self.feature_names)) == 461,
                'X2-B selected feature ordering invalid')
        audit_path = Path(audit).resolve()
        self.audit_sha = digest(audit_path)
        audited = json.loads(audit_path.read_text())
        require(audited['corpus_index_sha256'] == EXPECTED, 'audit corpus mismatch')
        require(audited['feature_header_sha256'] == HEADER_SHA, 'audit feature identity mismatch')
        by_manifest = {str((self.index.parent / c['manifest']).resolve()): c['sha256']
                       for c in corpus['components']}
        self.components = audited['components']
        self.audited_counts = audited['by_split_screen']
        require(len(self.components) == len(by_manifest) == 1024, 'component count mismatch')
        seeds = set()
        paths = set()
        counts = {'TRAIN': 0, 'VALIDATION': 0, 'TEST': 0}
        for c in self.components:
            seed, path = c['sourceSeed'], str(Path(c['manifest']).resolve())
            require(seed not in seeds and path not in paths, 'duplicate audited source/component')
            seeds.add(seed); paths.add(path)
            split = self.split_fn(seed)
            require(c['split'] == split, 'audit source split mismatch')
            counts[split] += 1
            require(by_manifest.get(path) == c['manifest_sha256'], 'audit manifest custody mismatch')
        require(seeds == set(corpus['sourceSeeds']), 'audited source set mismatch')
        require(counts == {'TRAIN': 696, 'VALIDATION': 155, 'TEST': 173}, 'source split counts mismatch')
        self.producers = {tuple(p[k] for k in ('producerGitSha', 'producerExecutableSha256',
                          'teacherManifestSha256', 'teacherId')) for p in corpus['allowedProducers']}

    def expected_sources(self, split):
        allowed_split(split)
        return tuple(sorted(c['sourceSeed'] for c in self.components if c['split'] == split))

    def expected_counts(self, split, screens=PROVISIONAL_MASK):
        allowed_split(split)
        require(set(screens) <= set(PROVISIONAL_MASK), 'unqualified count mask')
        return {screen: int(self.audited_counts[split][screen]['rows']) for screen in screens}

    def _manifest(self, component, split):
        allowed_split(split)
        require(component['split'] == split and self.split_fn(component['sourceSeed']) == split,
                'component split authorization mismatch')
        path = Path(component['manifest'])
        require(digest(path) == component['manifest_sha256'], 'component manifest hash mismatch')
        m = json.loads(path.read_text())
        require(m['schemaVersion'] == 'vwin_refresh_334_v1', 'component schema mismatch')
        require(m['seedSpec']['count'] == 1 and m['seedSpec']['start'] == component['sourceSeed'],
                'single-source component identity mismatch')
        require(tuple(m[k] for k in ('producerGitSha', 'producerExecutableSha256',
                      'teacherManifestSha256', 'teacherId')) in self.producers, 'producer mismatch')
        features = m['stateFeatures']
        require(features['headerSha256'] == HEADER_SHA and
                hashlib.sha256(features['header'].encode()).hexdigest() == HEADER_SHA,
                'rich feature header identity mismatch')
        require(features['count'] == 1017, 'rich feature count mismatch')
        sink = m['decisionSink']
        require(sink['enabled'] is True and sink['schema'] == 'vwin_decision_334_v1' and
                sink['screenContentsEncoding'] == 'canonical_json_public_state_v1' and
                sink['candidatesEncoding'] == 'canonical_semantic_keys_with_chosen_v1',
                'DECISION encoding mismatch')
        require(m['outputs']['decision.csv'] == component['decision_sha256'], 'audit DECISION identity mismatch')
        return path, m

    def iter_rows(self, split, screens=PROVISIONAL_MASK, source_limit=None):
        allowed_split(split)
        screens = frozenset(screens)
        require(screens and screens <= set(PROVISIONAL_MASK), 'unqualified screen requested')
        if source_limit is not None:
            require(isinstance(source_limit, int) and source_limit > 0, 'invalid source limit')
        selected = [c for c in self.components if c['split'] == split]
        if source_limit is not None: selected = selected[:source_limit]
        for c in selected:
            path, m = self._manifest(c, split)
            table = Path(str(path).removesuffix('.manifest.json') + '.decision.csv')
            require(digest(table) == c['decision_sha256'], 'DECISION table hash mismatch')
            rich_names = m['stateFeatures']['header'].split(',')
            require(len(rich_names) == len(set(rich_names)) == 1017, 'ambiguous rich header')
            indices = [len(PREFIX) + rich_names.index(n) for n in self.feature_names]
            logs = {}
            for trajectory in m['decisionSink']['trajectories']:
                require(trajectory['sourceSeed'] == c['sourceSeed'], 'trajectory source mismatch')
                for log in trajectory['decisionLog']:
                    if log['rowIdx'] >= 0:
                        identity = (trajectory['branchId'], log['rowIdx'])
                        require(identity not in logs, 'duplicate logged DECISION identity')
                        logs[identity] = log
            seen = set()
            with table.open(newline='') as stream:
                reader = csv.reader(stream)
                header = next(reader)
                require(header == PREFIX + rich_names + ['screenContents', 'candidates', 'won'],
                        'DECISION column contract mismatch')
                for raw in reader:
                    require(len(raw) == len(header), 'DECISION row width mismatch')
                    require(int(raw[0]) == c['sourceSeed'] and raw[8] == m['teacherId'], 'row producer/source mismatch')
                    key = (raw[1], int(raw[3]))
                    require(key not in seen and key in logs, 'row/log identity mismatch')
                    seen.add(key)
                    log = logs[key]
                    require(raw[7] == log['screen'] and int(raw[4]) == log['decisionIdx'], 'row/log decision mismatch')
                    if raw[7] not in screens: continue
                    contents, candidates = json.loads(raw[-3]), json.loads(raw[-2])
                    require(contents['screen'] == raw[7] and contents['screenState'] == SCREENS[raw[7]], 'screen mismatch')
                    keys = candidates['optionKeys']
                    require(candidates['supported'] is True and candidates['complete'] is True,
                            'incomplete semantic enumeration')
                    require(len(keys) == log['optionCount'] and len(keys) > 1 and len(set(keys)) == len(keys)
                            and all(isinstance(k, str) and k.startswith('ooc:v1:') for k in keys), 'invalid option keys')
                    # Chosen key is checked only for custody, never returned.
                    require(candidates['chosenKey'] in keys, 'unresolved chosen action')
                    require(raw[-1] in ('0', '1'), 'nonbinary outcome')
                    base = [float(raw[i]) for i in indices]
                    require(all(math.isfinite(x) for x in base), 'nonfinite base feature')
                    identity = {'sourceSeed': c['sourceSeed'], 'branchId': raw[1],
                                'deviationIdx': int(raw[2]), 'rowIdx': int(raw[3]),
                                'decisionIdx': int(raw[4]), 'act': int(raw[5]), 'floor': int(raw[6])}
                    yield {'identity': identity, 'screen': raw[7], 'label': int(raw[-1]),
                           'base461': base, 'screenContents': contents, 'optionKeys': sorted(keys)}
            require(seen == set(logs) and len(seen) == m['decisionSink']['rows'], 'DECISION row coverage mismatch')
            require(digest(table) == c['decision_sha256'] and digest(path) == c['manifest_sha256'],
                    'input changed during row read')

    def build_cache(self, directory, split, screens=PROVISIONAL_MASK, source_limit=None):
        allowed_split(split)
        require(set(screens) == set(PROVISIONAL_MASK), 'cache requires complete frozen replacement mask')
        directory = Path(directory)
        # A new directory is the write-once unit. Failed partial caches remain
        # visibly incomplete and cannot be silently reused or overwritten.
        directory.mkdir(parents=True, exist_ok=False)
        rows_path = directory / 'rows.jsonl'
        count = 0
        with rows_path.open('x') as stream:
            for row in self.iter_rows(split, screens, source_limit):
                stream.write(json.dumps(row, separators=(',', ':'), allow_nan=False) + '\n')
                count += 1
        record = {'schema': CACHE_SCHEMA, 'split': split, 'screens': sorted(screens),
                  'rows': count, 'source_limit': source_limit,
                  'corpus_sha256': EXPECTED, 'audit_sha256': self.audit_sha,
                  'predictor_sha256': PREDICTOR_SHA, 'feature_names': self.feature_names,
                  'feature_header_sha256': HEADER_SHA, 'split_code_sha256': self.split_code_sha,
                  'loader_sha256': digest(Path(__file__)), 'rows_sha256': digest(rows_path),
                  'expected_all_sources': list(self.expected_sources(split)),
                  'expected_all_counts': self.expected_counts(split, screens),
                  'join_availability': join_availability()}
        (directory / 'manifest.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
        return record


def read_cache(directory, split):
    allowed_split(split)
    directory = Path(directory)
    metadata = json.loads((directory / 'manifest.json').read_text())
    require(metadata['schema'] == CACHE_SCHEMA and metadata['split'] == split, 'cache split/schema mismatch')
    require(metadata['corpus_sha256'] == EXPECTED and metadata['predictor_sha256'] == PREDICTOR_SHA,
            'cache provenance mismatch')
    require(metadata['loader_sha256'] == digest(Path(__file__)), 'stale cache loader identity')
    split_fn, split_sha = source_split_function()
    require(metadata['split_code_sha256'] == split_sha, 'stale cache split implementation')
    require(metadata['feature_header_sha256'] == HEADER_SHA, 'cache feature header mismatch')
    require(digest(DEFAULT_PREDICTOR) == PREDICTOR_SHA, 'predictor feature identity mismatch')
    expected_features = json.loads(DEFAULT_PREDICTOR.read_text())['feature_names']
    require(metadata['feature_names'] == expected_features, 'cache selected-feature order mismatch')
    require(metadata['screens'] == sorted(PROVISIONAL_MASK), 'cache replacement mask mismatch')
    require(metadata['audit_sha256'] == digest(DEFAULT_AUDIT), 'cache audit identity mismatch')
    rows = directory / 'rows.jsonl'
    require(digest(rows) == metadata['rows_sha256'], 'cache payload hash mismatch')
    count = 0
    with rows.open() as stream:
        for line in stream:
            record = json.loads(line)
            require(split_fn(record['identity']['sourceSeed']) == split, 'cache source split mismatch')
            require(set(record) == {'identity', 'screen', 'label', 'base461', 'screenContents', 'optionKeys'},
                    'unexpected/leaking cache field')
            require(record['screen'] in PROVISIONAL_MASK, 'cache row screen outside mask')
            require(len(record['base461']) == 461 and all(math.isfinite(x) for x in record['base461']),
                    'cache base feature shape/value mismatch')
            require(record['label'] in (0, 1), 'cache label mismatch')
            count += 1
            yield record
    require(count == metadata['rows'], 'cache row count mismatch')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--split', required=True, choices=['TRAIN', 'VALIDATION'])
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--source-limit', type=int)
    a = p.parse_args()
    print(json.dumps(DecisionCorpus().build_cache(a.output, a.split, source_limit=a.source_limit), indent=2))

if __name__ == '__main__':
    main()
