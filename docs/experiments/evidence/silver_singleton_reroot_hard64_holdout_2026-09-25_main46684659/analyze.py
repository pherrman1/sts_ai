from pathlib import Path
import hashlib
import json

root = Path('/tmp/sts-singleton-n64-main46684659')
control = [json.loads(line) for line in (root / 'control.jsonl').read_text().splitlines() if line]
treatment = [json.loads(line) for line in (root / 'treatment.jsonl').read_text().splitlines() if line]
inputs = [json.loads(line) for line in Path('/tmp/sts-singleton-main-control-46684659/docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-holdout-snapshots.jsonl').read_text().splitlines() if line]
ids = [row['case_id'] for row in inputs]
assert len(ids) == 64 and len(set(ids)) == 64
for name, rows in [('control', control), ('treatment', treatment)]:
    assert len(rows) == 64, (name, len(rows))
    assert [r['case_id'] for r in rows] == ids, f'{name} order or identity mismatch'

control_by_id = {r['case_id']: r for r in control}
treatment_by_id = {r['case_id']: r for r in treatment}
pairs = []
for case_id in ids:
    c, t = control_by_id[case_id], treatment_by_id[case_id]
    both = c.get('status') == 'ok' and t.get('status') == 'ok'
    pairs.append({
        'case_id': case_id,
        'both_valid': both,
        'control_status': c.get('status'),
        'treatment_status': t.get('status'),
        'same_failure': c.get('status') != 'ok' and c.get('status') == t.get('status'),
        'control_won': c.get('won') if both else None,
        'treatment_won': t.get('won') if both else None,
        'outcome_flip': (c.get('won') != t.get('won')) if both else None,
        'control_hp_end': c.get('hp_end'),
        'treatment_hp_end': t.get('hp_end'),
        'control_max_hp': c.get('max_hp'),
        'treatment_max_hp': t.get('max_hp'),
        'control_simulations': c.get('simulations'),
        'treatment_simulations': t.get('simulations'),
        'control_singleton_skips': 0,
        'treatment_singleton_skips': t.get('singleton_search_skips', 0),
        'control_wall_seconds': c.get('wall_seconds'),
        'treatment_wall_seconds': t.get('wall_seconds'),
        'action_trace_equal': (c.get('action_trace_hash') == t.get('action_trace_hash')) if both else None,
    })
valid_pairs = [p for p in pairs if p['both_valid']]
valid_ids = {p['case_id'] for p in valid_pairs}
cvalid = [control_by_id[i] for i in ids if i in valid_ids]
tvalid = [treatment_by_id[i] for i in ids if i in valid_ids]
failures = [p for p in pairs if not p['both_valid']]
control_wins = sum(bool(r.get('won')) for r in cvalid)
treatment_wins = sum(bool(r.get('won')) for r in tvalid)
control_sims = sum(r.get('simulations', 0) for r in cvalid)
treatment_sims = sum(r.get('simulations', 0) for r in tvalid)
control_wall = sum(r.get('wall_seconds', 0.0) for r in cvalid)
treatment_wall = sum(r.get('wall_seconds', 0.0) for r in tvalid)
mean_hp_c = sum(r.get('hp_end', 0) for r in cvalid) / len(cvalid) if cvalid else None
mean_hp_t = sum(r.get('hp_end', 0) for r in tvalid) / len(tvalid) if tvalid else None
trace_equal = sum(bool(p['action_trace_equal']) for p in valid_pairs)
flips = sum(bool(p['outcome_flip']) for p in valid_pairs)
common_failures = [p for p in failures if p['same_failure']]
input_sha = hashlib.sha256(Path('/tmp/sts-singleton-main-control-46684659/docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-holdout-snapshots.jsonl').read_bytes()).hexdigest()

summary = {
    'cohort': 'hard64-holdout',
    'n_attempted': 64,
    'n_valid_pairs': len(valid_pairs),
    'budget_per_searched_decision': 10000,
    'simulation_mode': 'fixed exact budget per searched root; singleton treatment roots add zero simulations',
    'reuse_cap': 32768,
    'reuse_mode': 'allocated',
    'adaptive': False,
    'exact_visit_lock': False,
    'rho_racing': False,
    'omp_num_threads': 4,
    'snapshot_sha256': input_sha,
    'control_sha': '46684659a0d56729d7af1f8ae2ce9eeab39a6934',
    'treatment_sha': 'be47b2a1502013b04dcdd923b6d14c1c22c7dde1',
    'control_binary_sha256': hashlib.sha256(Path('/tmp/sts-singleton-main-control-46684659/build/linux-gcc-release/silver_hard_combat_replay').read_bytes()).hexdigest(),
    'treatment_binary_sha256': hashlib.sha256(Path('/home/philippherrmann/.codex/worktrees/e796/sts_lightspeed/build/linux-gcc-release/silver_hard_combat_replay').read_bytes()).hexdigest(),
    'control': {
        'valid_cases': len(cvalid), 'wins': control_wins,
        'simulations': control_sims,
        'wall_seconds_sum': control_wall,
        'mean_hp_end_losses_zero': mean_hp_c,
        'replay_failures': sum(r.get('status') != 'ok' for r in control),
        'singleton_search_skips': 0,
    },
    'treatment': {
        'valid_cases': len(tvalid), 'wins': treatment_wins,
        'simulations': treatment_sims,
        'wall_seconds_sum': treatment_wall,
        'mean_hp_end_losses_zero': mean_hp_t,
        'replay_failures': sum(r.get('status') != 'ok' for r in treatment),
        'singleton_search_skips': sum(r.get('singleton_search_skips', 0) for r in tvalid),
    },
    'paired': {
        'control_only_wins': sum(p['both_valid'] and p['control_won'] and not p['treatment_won'] for p in pairs),
        'treatment_only_wins': sum(p['both_valid'] and p['treatment_won'] and not p['control_won'] for p in pairs),
        'outcome_flips_valid_pairs': flips,
        'action_trace_equal_valid_pairs': trace_equal,
        'mean_hp_end_delta_treatment_minus_control': mean_hp_t - mean_hp_c if valid_pairs else None,
        'simulation_change_percent_valid_pairs': (treatment_sims / control_sims - 1.0) * 100.0 if control_sims else None,
        'wall_change_percent_valid_pairs': (treatment_wall / control_wall - 1.0) * 100.0 if control_wall else None,
        'common_failure_count': len(common_failures),
        'technical_failures': failures,
    },
}
(root / 'paired.jsonl').write_text('\n'.join(json.dumps(p, sort_keys=True) for p in pairs) + '\n')
(root / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
print(json.dumps(summary, indent=2, sort_keys=True))
