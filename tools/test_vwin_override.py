#!/usr/bin/env python3
"""Seed-free checks of native v_win selection, rejection, and name projection."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
B0 = 'models/v_win_trees.txt'
CANDIDATE = 'models/candidates/v_win_x2b_trees.txt'
PUBLIC = 'models/candidates/v_win_x2b_public_trees.txt'
MODEL = ('nfeat 2\nfeat floor\nfeat act\nlogistic 1\nbase_score 0.5\n'
         'ntrees 1\ntree 0 3\nS 0 5 1 2\nL -1\nL 1\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary')
    args = parser.parse_args()
    binary = str(Path(args.binary).resolve())
    identity = json.loads((ROOT / 'models/candidates/v_win_x2b_identity.json').read_text())
    assert identity['source_sha256'] == '99dbac6b5b082c46fe07242d2d15d8ccc6818041cb851efa79d6b423cdcb52dd'
    assert identity['native_sha256'] == 'a251b33d4f71c1aa3fca529801da23ea9740dd0ded58abfb1a90fe69da7c9acf'
    assert hashlib.sha256((ROOT / CANDIDATE).read_bytes()).hexdigest() == identity['native_sha256']
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('STS_', 'STRATEGIC_'))}
    env.update(STS_NATIVE_OOC='1', STS_OOC_MCTS='0')

    def run(label, override=None, *, success=True, message='', mode=None, mcts=False):
        case_env = env.copy()
        if mcts:
            case_env.update(STS_OOC_MCTS='1', STS_OOC_MCTS_SIMS='128',
                            STS_OOC_STRATEGIC_TOK_NN=str(ROOT / 'selfplay/models/ooc_strategic_tok_final.native'))
        if override is not None:
            case_env['STS_WIN_NET'] = override
        result = subprocess.run([binary] + (mode or ['oocmctsconfigselftest']),
                                cwd=ROOT, env=case_env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=60)
        assert (result.returncode == 0) == success, (label, result.returncode, result.stdout)
        assert message in result.stdout, (label, message, result.stdout)
        if not success:
            assert 'explicit STS_WIN_NET failed' in result.stdout, (label, result.stdout)
            assert f'from {B0}]' not in result.stdout, (label, 'silently loaded B0', result.stdout)
            assert 'PASS live OOC MCTS configuration startup' not in result.stdout
        print(f'PASS {label} rc={result.returncode}')
        return result.stdout

    run('unset uses B0', message=f'from {B0}]')
    run('legacy 1 uses B0', '1', message=f'from {B0}]')
    candidate_output = run('explicit X2-B', CANDIDATE, message=f'from {CANDIDATE}]')
    assert f'from {B0}]' not in candidate_output, candidate_output
    # Live OOC MCTS without STS_WIN_NET uses the public X2-B (§449, ADR-0029).
    public_output = run('OOC MCTS unset uses public X2-B', mcts=True, message=f'from {PUBLIC}]')
    assert f'from {B0}]' not in public_output, public_output
    assert f'[OOC MCTS default win model: {PUBLIC}]' in public_output, public_output
    b0_output = run('OOC MCTS legacy 1 uses B0', '1', mcts=True, message=f'from {B0}]')
    assert f'from {PUBLIC}]' not in b0_output and 'default win model' not in b0_output, b0_output
    run('OOC MCTS explicit X2-B', CANDIDATE, mcts=True, message=f'from {CANDIDATE}]')
    with tempfile.TemporaryDirectory(prefix='vwin-override-') as temporary:
        directory = Path(temporary)
        run('missing model', str(directory / 'missing.txt'), success=False)
        run('empty explicit path', '', success=False)
        malformed = {
            'truncated': 'nfeat 2\nfeat floor\n',
            'unknown_feature': MODEL.replace('feat floor', 'feat incompatible_vwin_feature'),
            'duplicate_feature': MODEL.replace('feat act', 'feat floor'),
            'bad_logistic_keyword': MODEL.replace('logistic 1', 'wrong 1'),
            'bad_base_keyword': MODEL.replace('base_score', 'wrong'),
            'bad_logistic_value': MODEL.replace('logistic 1', 'logistic 2'),
            'negative_split': MODEL.replace('S 0 5 1 2', 'S -1 5 1 2'),
            'bad_split_index': MODEL.replace('S 0 5 1 2', 'S 2 5 1 2'),
            'bad_child_index': MODEL.replace('S 0 5 1 2', 'S 0 5 1 3'),
            'overflow_leaf': MODEL.replace('L -1', 'L 1e100'),
            'trailing_token_eof': MODEL + 'garbage',
        }
        for label, content in malformed.items():
            path = directory / f'{label}.txt'
            path.write_text(content)
            run(label, str(path), success=False)
        projected = directory / 'projected.txt'
        projected.write_text(MODEL)
        rows = directory / 'projection.csv'
        # richIdxMap begins ascension,act,floor; selected feature 0 is floor,
        # raw index 2. Using selected indices as raw indices reverses the results.
        rows.write_text('chosen,ascension,act,floor,won\n0,9,1,2,0\n0,0,1,7,0\n')
        output = run('feature name projection', str(projected),
                     mode=['winnettest', str(projected), str(rows), '2'],
                     message='WINNET TEST: 2 rows')
        predictions = [(int(i), float(value)) for i, value in
                       re.findall(r'^(\d+),([0-9.]+)$', output, re.MULTILINE)]
        expected = [(0, 1 / (1 + math.exp(1))), (1, 1 / (1 + math.exp(-1)))]
        assert len(predictions) == 2, output
        for actual, target in zip(predictions, expected):
            assert actual[0] == target[0] and abs(actual[1] - target[1]) < 1e-8, output
        print('PASS projected predictions match independent logistic calculation')


if __name__ == '__main__':
    main()
