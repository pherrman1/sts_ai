#!/usr/bin/env python3
"""Validate frozen input/output custody and regenerate the natural pilot report."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from statistics import median
from prepare import E, ROOT, DECISIONS

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true')
args = parser.parse_args()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def emit(name, value):
    content = value if isinstance(value, str) else json.dumps(value, indent=2) + '\n'
    if args.check:
        assert (E / name).read_bytes() == content.encode(), name + ': reporting differs'
    else:
        (E / name).write_text(content)

manifest = json.loads((E / 'manifest.json').read_text())
assert [x['source_decision'] for x in manifest['selection']] == DECISIONS
expected_caps = {'depth':24, 'cycle_length':24, 'nodes':2000, 'candidates':16,
                 'repetitions':128, 'actions_per_replay':1024, 'total_replay_actions':4096}
rows, receipts, inputs = [], [], []
for batch in range(4):
    input_bytes = (E / f'inputs-{batch}.jsonl').read_bytes()
    assert sha(input_bytes) == manifest['input_files_sha256'][f'inputs-{batch}.jsonl']
    source = [json.loads(x) for x in input_bytes.splitlines()]
    receipt = json.loads((E / f'output-{batch}.receipt.json').read_text())
    raw = (E / f'output-{batch}.jsonl').read_bytes()
    stderr = (E / f'output-{batch}.stderr.txt').read_bytes()
    assert receipt['returncode'] == 0 and not stderr
    assert receipt['output_sha256'] == sha(raw) and receipt['stderr_sha256'] == sha(stderr)
    assert receipt['command'][:4] == ['timeout', '30s', 'bash', 'tools/seed_guard.sh']
    assert receipt['frozen_protocol_sha'].startswith('28c28eecd')
    assert receipt['wall_seconds'] < 30
    data = [json.loads(x) for x in raw.splitlines()]
    assert len(data) == 5 and data[-1]['roots'] == 4 and data[-1]['root_cap'] == 4
    assert data[-1]['annotated_roots'] == sum(r['status'] == 'ANNOTATED' for r in data[:-1])
    receipts.append(receipt)
    for local, r in enumerate(data[:-1]):
        assert r['root_index'] == local and r['K'] == 4
        index = batch * 4 + local
        assert sha(json.dumps(source[local], sort_keys=True).encode()) == manifest['selection'][index]['input_sha256']
        s = source[local]['public_wire']['state']
        assert source[local]['oracle_no_prismatic_shard'] is True
        assert s['isolatedSearchSeed'] == 0 and s['observedGeneration'] == 0
        assert not s['fullDrawOrderObserved'] and not s['drawPile']['fullOrderObserved']
        worlds = r['worlds']
        assert len(worlds) == 4 and [w['k'] for w in worlds] == list(range(4))
        pile = s['drawPile']
        physical = sorted((c['id'], c['uniqueId']) for z in ('knownTop','unknown','knownBottom') for c in pile[z])
        for w in worlds:
            expected = hashlib.sha256(f"combat-infinity-public-world-v1:{r['public_root_sha256']}:{w['k']}".encode()).hexdigest()
            assert w['sample_seed'] == str(int(expected[:16], 16))
            assert sorted((c['id'], c['physical_id']) for c in w['sampled_draw_bottom_first']) == physical
            o = w['oracle']
            assert o['caps'] == expected_caps
            assert o['nodes'] <= 2000 and o['max_depth'] <= 24 and len(o['candidates']) <= 16
            assert o['replay_actions'] <= 4096
        supported = sum(w['oracle']['supported'] for w in worlds)
        cert = sum(w['oracle']['classification'] == 'CERTIFIED_KILL' for w in worlds)
        candidate = sum(any(c['classification'] != 'STALL_LOOP' for c in w['oracle']['candidates']) for w in worlds)
        assert r['supported_worlds'] == supported
        if r['status'] == 'ANNOTATED':
            assert supported == 4 and r['certified_fraction'] == cert/4 and r['candidate_fraction'] == candidate/4
        else:
            assert r['certified_fraction'] is None and r['candidate_fraction'] is None
        search = [w['oracle'] for w in worlds]
        witnesses = [c for o in search for c in o['candidates'] if c['classification'] != 'STALL_LOOP']
        assert r['minimum_reach_depth'] == min((c['reach_depth'] for c in witnesses), default=None)
        row = {'index':index, 'source_decision':DECISIONS[index], 'turn':s['turn'],
               'status':r['status'], 'reason':r['reason'], 'supported_samples':supported,
               'certified_kill_samples':cert, 'candidate_samples':candidate,
               'certified_fraction':r['certified_fraction'], 'candidate_fraction':r['candidate_fraction'],
               'minimum_reach_depth':r['minimum_reach_depth'],
               'node_cap_samples':sum(o['node_cap_hit'] for o in search),
               'depth_cap_samples':sum(o['depth_cap_hit'] for o in search),
               'candidate_cap_samples':sum(len(o['candidates']) >= 16 for o in search),
               'total_replay_actions':sum(o['replay_actions'] for o in search),
               'nodes_min':min(o['nodes'] for o in search), 'nodes_max':max(o['nodes'] for o in search),
               'nodes_total':sum(o['nodes'] for o in search), 'max_depth':max(o['max_depth'] for o in search),
               'oracle_cpu_ms':round(sum(o['cpu_ms'] for o in search), 3),
               'distinct_draw_orders':len({json.dumps(w['sampled_draw_bottom_first'], sort_keys=True) for w in worlds}),
               'distinct_classifications':sorted({o['classification'] for o in search}),
               'distinct_search_diagnostics':len({(o['nodes'],o['max_depth'],o['node_cap_hit'],o['depth_cap_hit']) for o in search}),
               'representative_witness':next(iter(witnesses),None),
               'interpretation':'INCONCLUSIVE_NODE_CAP' if any(o['node_cap_hit'] for o in search) else 'NO_CANDIDATE_IN_BOUNDED_SUPPORTED_SEARCH'}
        rows.append(row)
        inputs.append(s)
worlds = [w['oracle'] for batch in range(4) for r in [json.loads(x) for x in (E / f'output-{batch}.jsonl').read_text().splitlines()][:-1] for w in r['worlds']]
summary = {'schema':'infinity_natural_pilot_result_v1', 'annotation_feasibility':'PASS' if all(r['status']=='ANNOTATED' for r in rows) else 'PARTIAL_OR_UNSUPPORTED',
           'scientific_usefulness':'NOT_ESTABLISHED', 'K':4, 'natural_roots':16,
           'eligible_natural_roots':sum(r['status']=='ANNOTATED' for r in rows),
           'unsupported_natural_roots':sum(r['status']!='ANNOTATED' for r in rows),
           'annotated_natural_worlds':sum(r['supported_samples'] for r in rows),
           'classifications':dict(Counter(o['classification'] for o in worlds)),
           'certified_worlds':sum(r['certified_kill_samples'] for r in rows),
           'candidate_worlds':sum(r['candidate_samples'] for r in rows),
           'node_cap_worlds':sum(r['node_cap_samples'] for r in rows),
           'node_cap_roots':sum(r['node_cap_samples']>0 for r in rows),
           'depth_cap_worlds':sum(r['depth_cap_samples'] for r in rows),
           'candidate_cap_worlds':sum(r['candidate_cap_samples'] for r in rows),
           'replay_actions':sum(r['total_replay_actions'] for r in rows),
           'classification_disagreement_roots':sum(len(r['distinct_classifications'])>1 for r in rows),
           'draw_order_disagreement_roots':sum(r['distinct_draw_orders']>1 for r in rows),
           'search_diagnostic_disagreement_roots':sum(r['distinct_search_diagnostics']>1 for r in rows),
           'nodes_total':sum(o['nodes'] for o in worlds), 'max_depth':max(o['max_depth'] for o in worlds),
           'oracle_cpu_ms_total':round(sum(o['cpu_ms'] for o in worlds),3),
           'oracle_cpu_ms_median':median(o['cpu_ms'] for o in worlds),
           'oracle_cpu_ms_max':max(o['cpu_ms'] for o in worlds),
           'batch_wall_seconds_total':sum(r['wall_seconds'] for r in receipts),
           'batch_child_cpu_seconds_total':sum(r['child_user_seconds']+r['child_system_seconds'] for r in receipts),
           'max_batch_wall_seconds':max(r['wall_seconds'] for r in receipts),
           'source_encounters':1, 'ascension':0, 'new_gameplay_runs':0}
emit('RESULT.json', summary)
emit('expanded-sidecars.json', rows)
lines = ['# Historical A0 Champ: K=4 annotation matrix', '',
         'Fractions describe bounded sampled searches. Capped NONE is inconclusive; other NONE rows are not proofs of absence.', '',
         '| Decision | Turn | Supported | Certified / candidate fraction | Nodes/world min–max | Max depth | Node/depth caps | Draw orders | CPU ms/root | Reach / witness |',
         '|---|---:|---:|---|---:|---:|---|---:|---:|---|']
for r in rows:
    lines.append(f"| {r['source_decision']} | {r['turn']} | {r['supported_samples']}/4 | {r['certified_fraction']} / {r['candidate_fraction']} | {r['nodes_min']}–{r['nodes_max']} | {r['max_depth']} | {r['node_cap_samples']} / {r['depth_cap_samples']} | {r['distinct_draw_orders']} | {r['oracle_cpu_ms']:.3f} | {r['minimum_reach_depth']} / {'none' if r['representative_witness'] is None else 'see sidecar'} |")
emit('MATRIX.md', '\n'.join(lines) + '\n')
text = (ROOT / 'include/constants/Cards.h').read_text()
start = text.index('cardEnumStrings')
names = re.findall(r'"([A-Z_0-9]+)"', text[start:text.index('};',start)])
examples = []
for index in (0,8,15):
    s = inputs[index]
    cards = s['hand'][:]
    for z in ('drawPile','discardPile','exhaustPile'):
        cards.extend(c for section in ('knownTop','unknown','knownBottom') for c in s[z][section])
    name = lambda c: names[c['id']] + ('+' if c['upgraded'] else '')
    examples.append({'source_decision': DECISIONS[index], 'turn':s['turn'], 'energy':s['player']['energy'],
                     'player_hp':s['player']['curHp'], 'enemy_hp':s['monsters'][0]['curHp'],
                     'hand':[name(c) for c in s['hand']], 'cards_by_public_zone':dict(Counter(name(c) for c in cards)),
                     'note':'public hand/draw/discard/exhaust inventory; not hidden order or oracle replay'})
emit('manual-examples.json', examples)
print(json.dumps(summary, sort_keys=True))
print('PASS fixed inputs/receipts/64 world records/budgets/public seed and multiset checks; generated reporting matches' if args.check else 'PASS generated reporting from preserved raw output; no worlds rerun')
