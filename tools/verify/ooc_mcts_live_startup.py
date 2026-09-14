#!/usr/bin/env python3
"""Seed-free startup contract checks; optional qualified artifact for ON success."""
import argparse
import os
from pathlib import Path
import subprocess


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
        ('invalid cap rejects ON', {'STS_OOC_MCTS': '1', 'STS_SILVER_REUSE_CAP': '0'}, False, 'must be 32768 or experimental 131072'),
        ('malformed cap rejects ON', {'STS_OOC_MCTS': '1', 'STS_SILVER_REUSE_CAP': 'invalid'}, False, 'must be a nonnegative integer'),
        ('experimental cap rejects ON', {'STS_OOC_MCTS': '1', 'STS_SILVER_SEARCH': '1', 'STS_SILVER_REUSE_CAP': '131072'}, False, 'requires frozen Silver reuse cap 32768'),
        ('OFF ignores combat artifact and sims', {'STS_OOC_MCTS': '0', 'STS_OOC_MCTS_COMBAT_MODEL': bad, 'STS_OOC_MCTS_SIMS': 'invalid'}, True, ''),
        ('invalid enable flag', {'STS_OOC_MCTS': '2'}, False, 'must be 0 or 1'),
        ('missing V4', {'STS_OOC_MCTS': '1', 'STS_OOC_STRATEGIC_TOK_NN': bad}, False, 'requires native V4'),
        ('missing native win', {'STS_OOC_MCTS': '1', 'STS_NATIVE_OOC': '0'}, False, 'requires native v_win'),
        ('explicit bad win rejects default retry', {'STS_OOC_MCTS': '1', 'STS_WIN_NET': bad}, False, 'explicit STS_WIN_NET failed'),
        ('missing combat artifact', {'STS_OOC_MCTS': '1'}, False, 'requires STS_OOC_MCTS_COMBAT_MODEL'),
        ('bad combat artifact', {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_COMBAT_MODEL': bad}, False, 'startup failure'),
        ('zero simulations', {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_SIMS': '0'}, False, 'must be positive'),
        ('malformed simulations', {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_SIMS': '-1'}, False, 'positive integer'),
    ]
    if args.artifact:
        cases.append(('ON loads qualified artifact', {'STS_OOC_MCTS': '1', 'STS_OOC_MCTS_SIMS': '128', 'STS_OOC_MCTS_COMBAT_MODEL': str(Path(args.artifact).resolve())}, True, 'live OOC MCTS ON'))
    for name, override, success, message in cases:
        result = subprocess.run(command, env=env | override, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        if (result.returncode == 0) != success or message not in result.stdout:
            raise AssertionError(f'{name}: rc={result.returncode}\n{result.stdout}')
        print(f'PASS {name} rc={result.returncode}')
    print(f'PASS {len(cases)} live OOC MCTS startup cases')


if __name__ == '__main__':
    main()
