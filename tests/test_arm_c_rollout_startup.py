"""Seed-free native startup checks for the optional rollout and CPU controls."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    repo=Path(__file__).resolve().parents[1];binary=Path(sys.argv[1]).resolve()
    base={k:os.environ[k] for k in ('PATH','HOME') if k in os.environ}
    base.update(OMP_NUM_THREADS='1',STS_NATIVE_OOC='1',STS_OOC_MCTS='1',
                STS_OOC_MCTS_LEAF_VALUE='native',STS_OOC_MCTS_LEAF_COMBATS='3',
                STS_OOC_STRATEGIC_TOK_NN=str(repo/'selfplay/models/ooc_strategic_tok_final.native'))
    command=['bash',str(repo/'tools/seed_guard.sh'),str(binary),'oocmctsconfigselftest']
    cases=[({'STS_OOC_MCTS_CPU_SECONDS':'0.25','STS_OOC_MCTS_EARLY_STOP':'0',
              'STS_OOC_MCTS_DECISION_LOG':'/unused/rejected-before-opening'},'requires EARLY_STOP=0'),({},None),({'STS_OOC_MCTS_CPU_SECONDS':'0.25','STS_OOC_MCTS_EARLY_STOP':'0'},None),
           ({'STS_OOC_MCTS_LEAF_POLICY':'heart1'},'requires STS_OOC_HEART1'),
           ({'STS_OOC_MCTS_CPU_SECONDS':'0.25'},'requires EARLY_STOP=0'),
           ({'STS_OOC_MCTS_CPU_SECONDS':'-1'},'invalid value'),
           ({'STS_OOC_MCTS_CPU_SECONDS':'nan'},'invalid value'),
           ({'STS_OOC_MCTS_CPU_SECONDS':'0.25','STS_OOC_MCTS_EARLY_STOP':'0',
             'STS_OOC_MCTS_ROOT_LOCK_TRACE':'/unused/rejected-before-opening'},'requires EARLY_STOP=0')]
    for extra,error in cases:
        result=subprocess.run(command,cwd=repo,env={**base,**extra},text=True,capture_output=True)
        if error:assert result.returncode!=0 and error in result.stderr,(extra,result.stdout,result.stderr)
        else:
            assert result.returncode==0,(result.stdout,result.stderr)
            config=json.loads(next(line.split('] ',1)[1] for line in result.stdout.splitlines() if line.startswith('[ooc-mcts-config]')))
            assert config['cpuSeconds']==float(extra.get('STS_OOC_MCTS_CPU_SECONDS','0'))
            assert config['leafPolicy']=='v4'
    print('PASS 8 seed-free rollout/CPU startup contracts')


if __name__=='__main__':main()
