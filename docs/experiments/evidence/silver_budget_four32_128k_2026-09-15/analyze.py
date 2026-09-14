"""Seed-free verification and descriptive analysis of the fixed four-arm packet."""
import csv
import gzip
import json
import math
import re
import statistics
from collections import Counter
from itertools import combinations
from pathlib import Path

packet_dir = Path(__file__).resolve().parent
arms = {
    'flat1k': (1000, 1000, 1000),
    'tier1_2_5k': (1000, 2000, 5000),
    'flat10k': (10000, 10000, 10000),
    'tier10_20_50k': (10000, 20000, 50000),
}
seeds = set(range(16, 48))

def read_text(name):
    path = packet_dir / name
    return path.read_text() if path.exists() else gzip.decompress(Path(str(path) + '.gz').read_bytes()).decode()

def read_rows(name):
    return list(csv.DictReader(read_text(name).splitlines()))

summary = {'arms': {}, 'pairs': {}}
results = {}
reference_config = reference_models = None
provenance = json.loads((packet_dir / 'provenance.json').read_text())
assert set(provenance['seeds']) == seeds
for name, budgets in arms.items():
    record = provenance['arms'][name]
    assert record['exit_code'] == 0
    assert tuple(record['budgets'][key] for key in ('normal', 'elite', 'boss')) == budgets
    for key, value in zip(('STS_SIMS_NORMAL', 'STS_SIMS_ELITE', 'STS_SIMS_BOSS'), budgets):
        assert record['environment'][key] == str(value)
    rows = read_rows(name + '.csv')
    assert len(rows) == 32 and {int(row['seed']) for row in rows} == seeds
    assert len({row['seed'] for row in rows}) == 32
    results[name] = {int(row['seed']): row for row in rows}
    diag = read_rows(name + '-decisions.csv')
    assert {int(row['run_seed']) for row in diag} == seeds
    assert all(row['configured_cap'] == '131072' and row['configured_cap_mode'] == 'allocated'
               and row['configured_simulations'] == row['simulations_added'] for row in diag)
    histogram = Counter(int(row['configured_simulations']) for row in diag)
    assert set(histogram) == set(budgets), (name, histogram)
    metadata = json.loads(read_text(name + '.csv.meta.json'))
    assert (metadata['sims'], metadata['nSeeds'], metadata['asc'], metadata['threads']) == (budgets[0], 32, 0, 4)
    assert metadata['seedBlock'] == {'lo': 16, 'hi': 47}
    config = metadata['config']
    assert config['executableGitSha'] == provenance['handoff_sha']
    assert config['silverReuseCap'] == 131072 and config['silverReuseCapMode'] == 'allocated'
    assert config['silverExactRootBudgets'] and not config['silverAdaptiveEnabled'] and config['fairPlay']
    config.pop('silverScalingDiagnosticFile')
    if reference_config is None:
        reference_config, reference_models = config, metadata['models']
    assert config == reference_config and metadata['models'] == reference_models
    log = read_text(name + '.log')
    assert f'[tiered sims: normal={budgets[0]} elite={budgets[1]} boss={budgets[2]}' in log
    telemetry = [line for line in log.splitlines() if line.startswith('[silver-combat]')]
    assert telemetry and all(not re.search(r'(?:conversion_failures|semantic_resolution_failures|transaction_failures|knowledge_failures)=[1-9]', line) for line in telemetry)
    assert not re.search(r'(?:simulatorHealthFailures|fatalFailures)=[1-9]', log)
    timing = read_text(name + '-time.txt')
    assert 'Exit status: 0' in timing
    rss = int(re.search(r'Maximum resident set size \(kbytes\): (\d+)', timing)[1])
    pressure = [row for row in diag if row['exact_candidate_found'] == '1' and int(row['allocated_nodes_before_root']) >= 131072]
    summary['arms'][name] = {
        'budgets': budgets,
        'wins': sum(int(row['won']) for row in rows),
        'mean_floor': statistics.mean(int(row['floor']) for row in rows),
        'mean_final_hp': statistics.mean(int(row['hpEnd']) for row in rows),
        'mean_seconds': statistics.mean(float(row['sec']) for row in rows),
        'total_added_simulations': sum(int(row['simulations_added']) for row in diag),
        'decision_records': len(diag),
        'budget_histogram': dict(sorted(histogram.items())),
        'exact_reroots': sum(int(row['exact_reroot']) for row in diag),
        'cap_pressure_candidates': len(pressure),
        'pressure_candidates_rescued': sum(row['exact_reroot'] == '1' for row in pressure),
        'allocated_cap_fallbacks': sum(row['fallback_reason'] == 'allocated_cap' for row in diag),
        'max_allocated_nodes': max(int(row['allocated_nodes_after_search']) for row in diag),
        'max_active_nodes': max(int(row['active_nodes_after_search']) for row in diag),
        'peak_process_rss_kib': rss,
        'cpu_user_seconds': float(re.search(r'User time \(seconds\): ([\d.]+)', timing)[1]),
        'silver_combat_records': len(telemetry),
        'bridge_failures': 0,
    }
for a_name, b_name in combinations(arms, 2):
    a, b = results[a_name], results[b_name]
    a_only = [seed for seed in sorted(seeds) if a[seed]['won'] == '1' and b[seed]['won'] == '0']
    b_only = [seed for seed in sorted(seeds) if b[seed]['won'] == '1' and a[seed]['won'] == '0']
    n, k = len(a_only) + len(b_only), min(len(a_only), len(b_only))
    p_value = min(1, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1
    summary['pairs'][a_name + '_vs_' + b_name] = {
        'a_only_wins': a_only, 'b_only_wins': b_only,
        'delta_win_pp': (len(b_only) - len(a_only)) * 100 / 32,
        'exact_p': p_value, 'bonferroni_6_pairs_p': min(1, 6 * p_value),
    }
combined = []
for seed in sorted(seeds):
    row = {'seed': seed}
    for name in arms:
        row.update({name + '_' + key: results[name][seed][key] for key in ('won', 'floor', 'hpEnd', 'sec')})
    combined.append(row)
with (packet_dir / 'paired-seeds.csv').open('w') as handle:
    writer = csv.DictWriter(handle, fieldnames=combined[0], lineterminator='\n')
    writer.writeheader()
    writer.writerows(combined)
(packet_dir / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
