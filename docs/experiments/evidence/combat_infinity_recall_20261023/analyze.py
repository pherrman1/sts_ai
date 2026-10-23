#!/usr/bin/env python3
"""Reproduce the bounded fixture ablation tables from retained raw JSONL."""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true', help='validate generated reporting without rewriting it')
args = parser.parse_args()
def emit(name, content):
 if args.check:
  assert (HERE/name).read_bytes() == content.encode(), name + ': generated reporting differs'
 else:
  (HERE/name).write_text(content)
ARMS = {'merged': 'baseline-recall.jsonl', 'exhaust_only': 'exhaust-recall.jsonl', 'exhaust_and_energy': 'energy-recall.jsonl', 'final_regressions': 'final-recall.jsonl'}
EXPECTED = {
 'minimal_dropkick': ('CERTIFIED_KILL','CERTIFIED_KILL','CERTIFIED_KILL'),
 'static_exhaust_dropkick': ('NONE','CERTIFIED_KILL','CERTIFIED_KILL'),
 'broken_dropkick': ('NONE','NONE','NONE'),
 'energy_positive_no_exhaust': ('NONE','NONE','CERTIFIED_KILL'),
 'energy_positive_exhaust': ('NONE','NONE','CERTIFIED_KILL'),
 'energy_negative_exhaust': ('NONE','NONE','NONE'),
 'time_eater': ('NONE','NONE','NONE'),
 'awakened_one_phase1': ('PRODUCTIVE_CYCLE_CANDIDATE',)*3,
 'heart_invincible_and_beat': ('NONE','NONE','NONE'),
 'heart_low_hp': ('NONE','NONE','NONE'),
}
REASONS = {'static_exhaust_dropkick': 'unqualified shuffle RNG prevents matching',
 'broken_dropkick': 'no Vulnerable: no draw/refund; no legal card after 1 play',
 'energy_positive_no_exhaust': 'energy increases; exact-energy equality prevents matching',
 'energy_positive_exhaust': 'energy increases; merged also rejects static exhaust quotient',
 'energy_negative_exhaust': 'energy declines; no legal card after 12 plays, enemy HP 116',
 'time_eater': 'Time Warp forces turn after 11 plays',
 'heart_invincible_and_beat': 'HP/Invincible remain exact; no repeat by depth 24; simulator trace dies at 40 plays, enemy HP 600',
 'heart_low_hp': 'Beat of Death kills player after 6 plays',
}
rows = {}
for arm, file in ARMS.items():
 rows[arm] = {r['fixture']: r for r in map(json.loads, (HERE/file).read_text().splitlines()) if 'fixture' in r}
 assert set(rows[arm]) == set(EXPECTED), (arm, 'fixture set')
 for name, r in rows[arm].items():
  expected = EXPECTED[name][min(list(ARMS).index(arm), 2)]
  assert r['classification'] == expected, (arm, name, r['classification'])
  assert r['caps'] == {'depth':24,'cycle_length':24,'nodes':2000,'candidates':16,'repetitions':128,'actions_per_replay':1024,'total_replay_actions':4096}
  if arm == 'final_regressions':
   # Extra guard diagnostics must not change detector/replay outcomes.
   for key in ('classification','nodes','reach_depth','cycle_length','enemy_hp_delta_per_cycle','player_hp_delta_per_cycle','energy_delta_per_cycle','replay'):
    assert r.get(key) == rows['exhaust_and_energy'][name].get(key), (name,key)
output=[]
for name in EXPECTED:
 for arm in ARMS:
  r=rows[arm][name]; replay=r.get('replay',{})
  output.append({'fixture':name,'arm':arm,'classification':r['classification'],
   'reach_depth':r.get('reach_depth'),'witness_length':r.get('cycle_length'),
   'nodes':r['nodes'],'max_depth':r['max_depth'],
   'enemy_hp_delta_per_period':r.get('enemy_hp_delta_per_cycle'),
   'player_hp_delta_per_period':r.get('player_hp_delta_per_cycle'),
   'energy_delta_per_period':r.get('energy_delta_per_cycle'),
   'replay_result':replay.get('reason','NOT_ATTEMPTED'),
   'repetitions':replay.get('repetitions'),'replay_actions':replay.get('actions',0),
   'cpu_ms':r['cpu_ms'],'reason':replay.get('reason') if replay else REASONS.get(name),
   'measured_six_play_period':{k:r.get('mechanics',{}).get(k) for k in ('energy_delta','enemy_hp_delta','sundial_start','sundial_end')} if name.startswith('energy') else None})
emit('matrix.json', json.dumps(output,indent=2)+'\n')
short={'CERTIFIED_KILL':'KILL','PRODUCTIVE_CYCLE_CANDIDATE':'CANDIDATE','NONE':'NONE'}
lines=['# Fixture ablation matrix','','KILL = CERTIFIED_KILL; CANDIDATE = PRODUCTIVE_CYCLE_CANDIDATE. All arms use the same bounds and fixture roots. Final extra diagnostics preserve every arm-B detector/replay result.','','| Fixture | Merged #839 | Exhaust only | Exhaust + energy |','| --- | --- | --- | --- |']
for name in EXPECTED:
 lines.append('| '+name+' | '+' | '.join(short[rows[a][name]['classification']] for a in list(ARMS)[:3])+' |')
lines += ['', 'Final focused-regression search metrics. CPU is one retained Release process-CPU measurement per fixture; setup, diagnostic traces and JSON output excluded. Dashes mean no candidate or witness, not an inferred zero.', '', '| Fixture | Nodes | Max depth | Reach depth | Cycle length | CPU ms |', '| --- | ---: | ---: | ---: | ---: | ---: |']
for name,r in rows['final_regressions'].items():
 fmt=lambda k: str(r.get(k,'—'))
 lines.append(f"| {name} | {r['nodes']} | {r['max_depth']} | {fmt('reach_depth')} | {fmt('cycle_length')} | {r['cpu_ms']:.3f} |")
lines += ['', 'Period deltas and replay outcomes from the same retained run:', '', '| Fixture | Enemy HP delta | Player HP delta | Energy delta | Replay result | Repetitions | Actions |', '| --- | ---: | ---: | ---: | --- | ---: | ---: |']
for name,r in rows['final_regressions'].items():
 replay=r.get('replay',{}); fmt=lambda k: str(r.get(k,'—'))
 lines.append(f"| {name} | {fmt('enemy_hp_delta_per_cycle')} | {fmt('player_hp_delta_per_cycle')} | {fmt('energy_delta_per_cycle')} | {replay.get('reason','not attempted')} | {replay.get('repetitions','—')} | {replay.get('actions','—')} |")
lines += ['','The cost-negative engine has a simulator-verified six-play period with enemy HP −42 and energy −2, but no admissible cycle candidate. It exhausts energy at 12 plays. Heart discovery has no repeated control state because player HP and Invincible change; a separate two-play forced-replay probe rejects control_state_changed. The unchanged full trace hits Invincible 0 after 29 plays and player death after 40 plays, with 600 enemy HP remaining. Low-HP Heart dies after 6 plays. Time Eater forces the turn after 11 plays. Awakened One rejects after 25 replay actions (12 complete periods plus one action).','', 'For every arm, the complete metrics, reasons and explicit nulls are in matrix.json; exact witnesses and diagnostic traces are in the raw JSONL.','']
emit('MATRIX.md', '\n'.join(lines))
print('PASS ablation classifications, fixed budgets, final/arm-B detector parity; 40 complete matrix rows' + ('; committed reporting matches raw evidence' if args.check else ''))
