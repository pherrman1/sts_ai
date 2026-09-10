#!/usr/bin/env python3
"""Audit the frozen 1,024-source semantic combat sidecars without fitting models.

The inherited trainer's source-seed split and 30 held-out nonambiguous death
screen are descriptive coverage checks, not a prospective statistical power
calculation. No simulator, trainer main, model export, or cloud command runs.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

# The unchanged V1 trainer imports its sibling modules as top-level modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from combat_evaluator_semantic_branch_contract import _branch, _read_csv, sha256, validate_manifest
from ooc_semantic_pipeline_contract import require
from train_combat_evaluator import stable_split
from train_ooc_semantic_probe import FAMILY_NAMES, SOURCE_NAMES

COHORT = set(range(992000, 993024))


def counts(rows):
    result = dict(total=len(rows), valid=0, wins=0, true_deaths=0,
                  nonambiguous_deaths=0, escaped=0, turn_cap=0, ambiguous=0, invalid=0)
    for row in rows:
        valid = int(row['labelValid'])
        result['valid'] += valid
        result['invalid'] += 1 - valid
        result['wins'] += valid * int(row['won'])
        result['true_deaths'] += valid * int(row['trueDeath'])
        result['nonambiguous_deaths'] += valid * int(row['trueDeath']) * (1-int(row['progressAmbiguous']))
        for output, field in [('escaped', 'escaped'), ('turn_cap', 'turnCapLoss'), ('ambiguous', 'progressAmbiguous')]:
            result[output] += int(row[field])
    result['source_seeds'] = len({int(row['sourceSeed']) for row in rows})
    return result


def quantiles(values):
    values = sorted(map(float, values))
    require(all(math.isfinite(v) for v in values), 'nonfinite label distribution')
    if not values:
        return dict(n=0, min=None, max=None, quantiles={})
    def at(p):
        position = (len(values)-1)*p
        low, high = math.floor(position), math.ceil(position)
        return values[low] + (values[high]-values[low])*(position-low)
    return dict(n=len(values), min=values[0], max=values[-1],
                quantiles={str(p): at(p) for p in (0, .01, .05, .25, .5, .75, .95, .99, 1)})


def family(row):
    source = SOURCE_NAMES[int(row['semanticSource'])]
    return FAMILY_NAMES.get(source, source)


def read_shard(path, producer_sha):
    manifest = json.loads(path.read_text())
    validation = validate_manifest(manifest)
    require(manifest['producer_git_sha'] == producer_sha, 'unexpected producer')
    semantic = json.loads(Path(manifest['semantic_manifest']['path']).read_text())
    with Path(semantic['csv']['path']).open(newline='', encoding='utf-8') as stream:
        branches = list(csv.DictReader(stream))
    require(all(int(row['valid']) == 1 for row in branches), 'quarantined semantic branch')
    rows = _read_csv(manifest['csv']['path'])
    provenance = {key: semantic[key] for key in ('producer_git_sha', 'producer_executable_sha256',
                                                'combat_teacher', 'stateFeatures', 'evaluation', 'runtime')}
    shard = dict(manifest=str(path), manifest_sha256=sha256(path),
                 combat_csv=manifest['csv'], semantic_manifest=manifest['semantic_manifest'],
                 semantic_csv=semantic['csv'], frozen_manifest=manifest['frozen_manifest'],
                 source_seeds=manifest['seed_spec']['sourceSeeds'], validation=validation)
    return rows, branches, provenance, shard


def validate_cohort(shards, semantic_rows, combat_rows):
    require(len(shards) == 64, 'confirmation requires exactly 64 combat shards')
    seen = set()
    for shard in shards:
        seeds = shard['source_seeds']
        require(len(seeds) == len(set(seeds)) == 16, 'each shard requires 16 distinct sources')
        require(not seen.intersection(seeds), 'overlapping source shards')
        seen.update(seeds)
    require(seen == COHORT, 'wrong confirmation seed cohort')
    decisions = defaultdict(set)
    branches = set()
    for row in semantic_rows:
        key = _branch(row)
        require(key not in branches, 'duplicate global semantic branch identity')
        branches.add(key)
        decisions[key[0]].add(key[1])
    require(set(decisions) == seen and all(len(v) == 1 for v in decisions.values()),
            'expected exactly one decision per source seed')
    identities = [_branch(row) + (int(row['branchFightIdx']),) for row in combat_rows]
    require(len(identities) == len(set(identities)), 'duplicate global combat identity')
    require(all(key[:-1] in branches for key in identities), 'unmatched global combat identity')
    return decisions


def classify(splits):
    support = all(splits[name]['wins'] > 0 and splits[name]['nonambiguous_deaths'] > 0
                  for name in ('train', 'validation', 'test'))
    return ('COMBAT LABELS ADEQUATE' if support and splits['test']['nonambiguous_deaths'] >= 30
            else 'COMBAT LOSS TAIL LOW POWER')


def summarize(rows, branches, source_seeds):
    split = stable_split(source_seeds)
    split_counts = {name: counts([r for r in rows if split[int(r['sourceSeed'])] == name])
                    for name in ('train', 'validation', 'test')}
    for name, value in split_counts.items():
        value['cohort_source_seeds'] = sum(v == name for v in split.values())
    distributions = {}
    for dimension in ('act', 'roomClass', 'encounter', 'semantic_family'):
        grouped = defaultdict(list)
        for row in rows:
            grouped[family(row) if dimension == 'semantic_family' else row[dimension]].append(row)
        distributions[dimension] = {str(key): counts(grouped[key]) for key in sorted(grouped)}
    valid = [r for r in rows if int(r['labelValid'])]
    winners = [r for r in valid if int(r['won'])]
    deaths = [r for r in valid if int(r['trueDeath'])]
    nonambiguous = [r for r in deaths if not int(r['progressAmbiguous'])]
    labels = {name: quantiles(r[field] for r in subset) for name, field, subset in (
        ('signedOutcome_valid', 'signedOutcome', valid),
        ('winHpFrac_winners', 'winHpFrac', winners),
        ('lossRemainingFrac_true_deaths', 'lossRemainingFrac', deaths),
        ('lossRemainingFrac_nonambiguous_deaths', 'lossRemainingFrac', nonambiguous))}
    captured = {_branch(row) for row in rows}
    missing = [row for row in branches if _branch(row) not in captured]
    require(all(int(row['silverSimulations']) == 0 for row in missing), 'missing positive-cost combat row')
    simulations = sum(int(row['silverSimulations']) for row in branches)
    decisions = {(int(row['sourceSeed']), int(row['decisionIdx'])) for row in branches}
    actions = {(int(row['sourceSeed']), int(row['decisionIdx']), row['semanticKey']) for row in branches}
    def ratio(n, d):
        return n/d if d else None
    return dict(counts=counts(rows), source_decisions=len(decisions), unique_semantic_actions=len(actions),
                semantic_branches=len(branches), unique_combat_identities=len(captured),
                branches_without_combat=dict(count=len(missing), zero_simulation_branches=len(missing),
                    reason='No fight was captured; zero simulation cost is consistent with termination before combat.',
                    reason_status='Inference from H=1 producer contract; CSV has no explicit no-combat reason field.',
                    by_semantic_family=dict(sorted(Counter(map(family, missing)).items()))),
                distributions=distributions, labels=labels, splits=split_counts,
                split_rule='Unchanged tools/train_combat_evaluator.py::stable_split(sourceSeed)',
                classification=classify(split_counts),
                classification_rule='Inherited screening heuristic: at least 30 valid nonambiguous test deaths and winners/nonambiguous deaths in all splits; not a power calculation.',
                limitations=['Correlated semantic siblings are not independent combats or independent deaths.',
                             'Adequate coverage does not establish predictive performance; no combat model was trained.',
                             'Ambiguous Awakened One deaths retain V1 signed labels but are excluded from nonambiguous death support.'],
                cost=dict(semantic_branch_silver_simulations=simulations,
                          simulations_per_source_decision=ratio(simulations, len(decisions)),
                          simulations_per_semantic_action=ratio(simulations, len(actions)),
                          combat_labels_per_million_simulations=ratio(len(rows)*1e6, simulations),
                          valid_combat_labels_per_million_simulations=ratio(len(valid)*1e6, simulations),
                          semantic_branch_cpu_seconds=sum(float(r['cpuMs']) for r in branches)/1000,
                          semantic_branch_wall_seconds_sum=sum(float(r['wallMs']) for r in branches)/1000,
                          timing_scope='Branch timer sums only; source capture/replay and elapsed parallel run wall time are excluded.'))


def analyze(manifest_paths, producer_sha):
    require(len(manifest_paths) == 64, 'confirmation requires exactly 64 combat shards')
    rows, branches, shards, frozen = [], [], [], None
    for path in sorted(manifest_paths):
        combat, semantic, provenance, shard = read_shard(path, producer_sha)
        frozen = frozen or provenance
        require(frozen == provenance, 'mixed frozen experiment provenance')
        rows.extend(combat)
        branches.extend(semantic)
        shards.append(shard)
    validate_cohort(shards, branches, rows)
    return dict(experiment='semantic_combat_label_fresh_1024_coverage', frozen=frozen,
                cohort=dict(first_seed=992000, last_seed=993023, source_seeds=1024, shards=64, seeds_per_shard=16),
                shards=shards, **summarize(rows, branches, COHORT))


def markdown(report):
    c = report['counts']
    lines = [f"**{report['classification']}**", '',
             f"{c['total']} combat rows: {c['valid']} valid, {c['wins']} wins, {c['true_deaths']} true deaths, "
             f"{c['nonambiguous_deaths']} nonambiguous deaths, {c['invalid']} invalid.", '',
             '| Split | Wins | True deaths | Nonambiguous deaths |', '| --- | ---: | ---: | ---: |']
    for name, value in report['splits'].items():
        lines.append(f"| {name} | {value['wins']} | {value['true_deaths']} | {value['nonambiguous_deaths']} |")
    lines.extend(['', report['classification_rule'], '', *report['limitations'], ''])
    return '\n'.join(lines)


def add_runner_cost(report, path):
    metadata = json.loads(path.read_text())
    stages = {}
    for name in ('capture', 'evaluate'):
        stage = metadata[name]
        require(stage['completed'] == 64 and len(stage['shards']) == 64,
                'incomplete runner stage')
        require(len({s['shard'] for s in stage['shards']}) == 64, 'duplicate runner shard')
        require(all(s['returncode'] == 0 and s['stage'] == name for s in stage['shards']),
                'failed or mismatched runner stage')
        values = [stage['wall_seconds']] + [s[k] for s in stage['shards'] for k in ('wall_seconds', 'cpu_seconds')]
        require(all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in values),
                'invalid runner timing')
        stages[name] = dict(stage_elapsed_wall_seconds=stage['wall_seconds'],
                           process_wall_seconds_sum=sum(s['wall_seconds'] for s in stage['shards']),
                           process_cpu_seconds=sum(s['cpu_seconds'] for s in stage['shards']),
                           workers=stage['workers'])
    report['cost']['runner'] = dict(metadata=dict(path=str(path), sha256=sha256(path)), stages=stages,
                                   process_cpu_seconds_total=sum(s['process_cpu_seconds'] for s in stages.values()),
                                   stage_elapsed_wall_seconds_sum=sum(s['stage_elapsed_wall_seconds'] for s in stages.values()),
                                   scope='Capture and evaluation process timings include source/replay work; stage wall sums assume sequential stages, exclude build/analysis.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifests', nargs='+', type=Path)
    parser.add_argument('--producer-sha', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--markdown', type=Path)
    parser.add_argument('--runner-metadata', type=Path,
                        help='JSON object with capture/evaluate stage completion metadata')
    args = parser.parse_args()
    report = analyze(args.manifests, args.producer_sha)
    if args.runner_metadata:
        add_runner_cost(report, args.runner_metadata)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown(report))
    print(json.dumps({key: report[key] for key in ('classification', 'counts', 'splits', 'cost')}, sort_keys=True))


if __name__ == '__main__':
    main()
