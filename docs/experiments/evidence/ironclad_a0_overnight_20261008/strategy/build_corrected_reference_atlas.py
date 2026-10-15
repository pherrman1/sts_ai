#!/usr/bin/env python3
"""Read frozen wave2 Fprod evidence only; never launches a simulator or opens holdout."""
import csv
import importlib.util
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EV = ROOT / 'docs/experiments/evidence/ironclad_a0_overnight_20261008'
WAVE = ROOT / 'build/overnight_20261008/wave2'
spec = importlib.util.spec_from_file_location('trace_summary', EV / 'learning/summarize_traces.py')
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


def build():
    protocol_path = EV / 'protocols/wave2.json'
    protocol = json.loads(protocol_path.read_text())
    inputs, endpoints = [], []
    for shard in range(32):
        receipt_path = WAVE / f'Fprod_{shard}.receipt.json'
        receipt = json.loads(receipt_path.read_text())
        assert receipt['status'] == 'completed' and receipt['exit_code'] == 0
        assert receipt['arm'] == 'Fprod'
        assert receipt['manifest_sha256'] == summary.sha(protocol_path)
        assert receipt['source_sha'] == protocol['source_sha']
        assert receipt['binary_sha256'] == protocol['binary_sha256']
        assert receipt['environment']['STS_OOC_PUBLIC_FUTURES'] == '8'
        assert receipt['environment']['STS_OOC_SKIP_OPTIONAL_RECALL'] == '1'
        inputs.append({'kind': 'receipt', 'path': str(receipt_path.relative_to(ROOT)),
                       'sha256': summary.sha(receipt_path)})
        # All outputs of the three chronology shards, endpoints only elsewhere.
        roles = list(receipt['outputs']) if shard < 3 else ['csv']
        for role in roles:
            item = receipt['outputs'][role]
            path = Path(item['path'])
            assert path.parent == WAVE and path.name.startswith(f'Fprod_{shard}.')
            assert summary.sha(path) == item['sha256'] and path.stat().st_size == item['bytes']
            inputs.append({'kind': role, 'path': str(path.relative_to(ROOT)), 'sha256': item['sha256']})
        path = Path(receipt['outputs']['csv']['path'])
        rows = list(csv.DictReader(path.open()))
        assert [int(r['seed']) for r in rows] == list(range(610082000+shard*4, 610082004+shard*4))
        endpoints.extend({**{k: float(v) if k == 'sec' else int(v) for k,v in row.items()},
                          'locator': f'{path.relative_to(ROOT)}:{i+2}'} for i,row in enumerate(rows))
    assert len(endpoints) == 128 and sum(r['won'] for r in endpoints) == 101
    enum_path = ROOT / 'include/constants/MonsterEncounters.h'
    names = re.search(r'monsterEncounterEnumNames\[\]\s*=\s*\{([^}]+)', enum_path.read_text()).group(1)
    names = re.findall(r'"([A-Z0-9_]+)"', names)
    for row in endpoints:
        row['death_encounter_name'] = names[row['deathEncounter']] if row['deathEncounter'] >= 0 else None
    detail = summary.summarize([WAVE/f'Fprod_{s}.trace.jsonl' for s in range(3)],
                               [WAVE/f'Fprod_{s}.tree.jsonl' for s in range(3)])
    runs = {r['seed']: r for r in detail['runs']}
    assert sorted(runs) == list(range(610082000,610082012))
    for run in runs.values():
        run['endpoint'] = next(r for r in endpoints if r['seed'] == run['seed'])
        roots = run.pop('tree_roots')
        battles = defaultdict(list)
        for row in roots:
            battles[(row['act'],row['floor'],row['encounter'],row['combat_id'])].append(row)
        run['combat_summaries'] = [{'act':key[0], 'floor':key[1], 'encounter':key[2],
            'combat_id':key[3], 'roots':len(rows), 'first_root':rows[0], 'last_root':rows[-1],
            'max_root_turn':max(r['turn'] for r in rows),
            'simulations':sum(r['completed_simulations'] for r in rows),
            'errors':sum(bool(r['error']) for r in rows),
            'descent_aborts':sum(r['descent_aborts'] or 0 for r in rows)} for key,rows in battles.items()]
        run['strategic_decisions'] = []
        run['public_ooc_details'] = []
    for shard in range(3):
        path = WAVE/f'Fprod_{shard}.strategic.jsonl'
        with path.open() as stream:
            for line,row in enumerate(csv.DictReader(stream),2):
                seed = int(row['seed'])
                assert seed in runs
                runs[seed]['strategic_decisions'].append({'locator':f'{path.relative_to(ROOT)}:{line}', **row})
        path = WAVE/f'Fprod_{shard}.trace.jsonl'
        for line,row in summary.read_jsonl(path):
            if row['pre']['screen'] in ('REST','SHOP','BOSS_RELIC','EVENT','CARD_SELECT'):
                runs[int(row['seed'])]['public_ooc_details'].append({'locator':f'{path.relative_to(ROOT)}:{line}',**row})
    deaths = [r for r in endpoints if not r['won']]
    rest_menus = [d for r in runs.values() for d in r['strategic_decisions'] if d['screen'] == '7']
    rest_transitions = [d for r in runs.values() for d in r['public_ooc_details'] if d['pre']['screen'] == 'REST']
    endpoint_health = Counter()
    for shard in range(3):
        for _, row in summary.read_jsonl(WAVE/f'Fprod_{shard}.tree.jsonl'):
            for key, value in row['endpoints'].items():
                endpoint_health[key] += value['count']
    return {'schema':'corrected_reference_atlas_v1',
        'scope':'wave2 Fprod only; all128 endpoints; first12 fixed source-order chronology; outcome-unselected but not blinded',
        'source_sha':protocol['source_sha'], 'binary_sha256':protocol['binary_sha256'],
        'protocol_sha256':summary.sha(protocol_path), 'summarizer_sha256':summary.sha(EV/'learning/summarize_traces.py'),
        'encounter_enum_sha256':summary.sha(enum_path), 'inputs':inputs,
        'population':{'runs':128,'wins':101,'losses':27,'deaths_by_act':dict(Counter(r['act'] for r in deaths)),
                      'deaths_by_encounter':dict(Counter(r['death_encounter_name'] for r in deaths))},
        'first12_summary':{'wins':sum(r['endpoint']['won'] for r in runs.values()),
            'battles':sum(r['battle_count'] for r in runs.values()),
            'chronology_rows':sum(len(r['chronology']) for r in runs.values()),
            'tree_roots':sum(r['tree_summary']['roots'] for r in runs.values()),
            'simulations':sum(r['tree_summary']['simulations'] for r in runs.values()),
            'search_endpoints':dict(endpoint_health),
            'root_errors':sum(r['tree_summary']['errors'] for r in runs.values()),
            'descent_aborts':sum(c['descent_aborts'] for r in runs.values() for c in r['combat_summaries']),
            'rest_menus':len(rest_menus), 'full_hp_rest_roots':sum(d['pre']['hp']==d['pre']['maxHp'] for d in rest_transitions),
            'rest_transition_screens':dict(Counter(d['post']['screen'] for d in rest_transitions)),
            'recall_menus':[d for d in rest_menus if '2' in d['actionBits'].split('|')]},
        'endpoints':endpoints, 'runs':[runs[s] for s in sorted(runs)], 'limits':detail['limits'] + [
            'The first12 cohort is fixed by source order, includes wins/losses, and is not representative by outcome.',
            'No action-level public combat snapshots were captured for this cohort; tree roots do not reconstruct hands or alternatives.',
            'This is descriptive evidence, not a new adaptation, training dataset, causal counterfactual, or confirmation.']}


if __name__ == '__main__':
    result = build()
    out = EV/'strategy/CORRECTED_REFERENCE_ATLAS.json'
    with out.open('x') as stream:
        json.dump(result,stream,indent=2)
        stream.write('\n')
    print(json.dumps({'output':str(out),'sha256':summary.sha(out),'population':result['population']}))
