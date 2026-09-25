#!/usr/bin/env python3
"""Seed-free startup contract checks; optional qualified artifact for ON success."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def assert_sampled_configuration(output):
    prefix = '[ooc-mcts-config] '
    configs = [json.loads(line[len(prefix):]) for line in output.splitlines()
               if line.startswith(prefix)]
    if len(configs) != 1 or configs[0].get('noncombatOutcomes') != 'sampled':
        raise AssertionError(f'enabled live configuration must sample noncombat outcomes: {configs}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('binary')
    parser.add_argument('--artifact')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    env = {k: v for k, v in os.environ.items() if not k.startswith(('STS_', 'STRATEGIC_'))}
    env.update(STS_NATIVE_OOC='1', STS_OOC_STRATEGIC_TOK_NN=str(root / 'selfplay/models/ooc_strategic_tok_final.native'))
    command = ['bash', str(root / 'tools/seed_guard.sh'), str(Path(args.binary).resolve()), 'oocmctsselftest']
    bad = str(root / 'build/absent-ooc-mcts-startup-artifact.native')
    cases = [
        ('default OFF', {}, True, ''),
        # The reuse cap is fixed; the vendored override was removed (ADR-0022).
        ('removed cap override rejects', {'STS_OOC_MCTS': '1', 'STS_SILVER_REUSE_CAP': '131072'}, False, 'not supported by the native Silver backend'),
        ('OFF ignores combat artifact and sims', {'STS_OOC_MCTS': '0', 'STS_OOC_MCTS_COMBAT_MODEL': bad, 'STS_OOC_MCTS_SIMS': 'invalid'}, True, ''),
        ('invalid enable flag', {'STS_OOC_MCTS': '2'}, False, 'must be 0 or 1'),
        ('missing V4', {'STS_OOC_MCTS': '1', 'STS_OOC_STRATEGIC_TOK_NN': bad}, False, 'requires native V4'),
        ('missing native win', {'STS_OOC_MCTS': '1', 'STS_NATIVE_OOC': '0'}, False, 'requires native v_win'),
        ('explicit bad win rejects default retry', {'STS_OOC_MCTS': '1', 'STS_WIN_NET': bad}, False, 'explicit STS_WIN_NET failed'),
        ('missing combat artifact', {'STS_OOC_MCTS': '1'}, False, 'requires STS_OOC_MCTS_COMBAT_MODEL'),
        ('bad combat artifact', {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_COMBAT_MODEL': bad}, False, 'startup failure'),
        ('zero simulations', {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_SIMS': '0'}, False, 'must be positive'),
        ('malformed simulations', {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_SIMS': '-1'}, False, 'positive integer'),
        ('malformed gap stop', {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_GAP_STOP_20': 'true'}, False, 'STS_OOC_MCTS_GAP_STOP_20 invalid value'),
    ]
    if args.artifact:
        with tempfile.TemporaryDirectory() as temporary:
            trace = str(Path(temporary) / 'checkpoints.jsonl')
            result = subprocess.run(command, env=env | {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_SIMS': '2048',
                'STS_OOC_MCTS_COMBAT_MODEL': str(Path(args.artifact).resolve()),
                'STS_OOC_MCTS_CHECKPOINT_TRACE': trace}, cwd=root, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
            if result.returncode or 'live_policy_unchanged=1' not in result.stdout:
                raise AssertionError(result.stdout)
            assert_sampled_configuration(result.stdout)
            print('PASS checkpoint shadow startup rc=0')
        cases.append(('checkpoint wrong budget', {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_SIMS': '512',
            'STS_OOC_MCTS_CHECKPOINT_TRACE': bad, 'STS_OOC_MCTS_COMBAT_MODEL': str(Path(args.artifact).resolve())},
            False, 'checkpoint shadow requires 2048'))
        cases.append(('checkpoint rejects full-budget live observer', {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_SIMS': '2048',
            'STS_OOC_MCTS_ROOT_LOCK_TRACE': bad, 'STS_OOC_MCTS_CHECKPOINT_TRACE': bad,
            'STS_OOC_MCTS_COMBAT_MODEL': str(Path(args.artifact).resolve())}, False, 'checkpoint shadow requires 2048'))
        cases.append(('ON loads qualified artifact', {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_SIMS': '128', 'STS_OOC_MCTS_COMBAT_MODEL': str(Path(args.artifact).resolve())}, True, '"earlyStop":true'))
        cases.append(('ON rollback disables stopping', {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_EARLY_STOP': '0', 'STS_OOC_MCTS_COMBAT_MODEL': str(Path(args.artifact).resolve())}, True, '"earlyStop":false'))
        cases.append(('ON rejects malformed stopping', {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_EARLY_STOP': 'true', 'STS_OOC_MCTS_COMBAT_MODEL': str(Path(args.artifact).resolve())}, False, 'STS_OOC_MCTS_EARLY_STOP invalid value'))
        cases.append(('ON accepts 20% gap stop', {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_SIMS': '2048',
            'STS_OOC_MCTS_GAP_STOP_20': '1', 'STS_OOC_MCTS_COMBAT_MODEL': str(Path(args.artifact).resolve())},
            True, '"gapStop20":true'))
        cases.append(('20% gap stop requires 2048', {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_SIMS': '512',
            'STS_OOC_MCTS_GAP_STOP_20': '1', 'STS_OOC_MCTS_COMBAT_MODEL': str(Path(args.artifact).resolve())},
            False, 'STS_OOC_MCTS_GAP_STOP_20 requires 2048'))
    for name, override, success, message in cases:
        result = subprocess.run(command, env=env | override, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        if (result.returncode == 0) != success or message not in result.stdout:
            raise AssertionError(f'{name}: rc={result.returncode}\n{result.stdout}')
        if success and override.get('STS_OOC_MCTS') == '1':
            assert_sampled_configuration(result.stdout)
        print(f'PASS {name} rc={result.returncode}')
    print(f'PASS {len(cases)} live OOC MCTS startup cases')


if __name__ == '__main__':
    main()
