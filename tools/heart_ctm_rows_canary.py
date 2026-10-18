#!/usr/bin/env python3
"""OFF/ON parity and row check for STS_HEART_OUTCOME_CTM_ROWS (no seeds).

DIR holds one seed's off.* and ctm.* outputs of `heartoutcomegen 1 SEED
DIR/TAG.jsonl policy` from the same binary and environment, ctm.* with
STS_HEART_OUTCOME_CTM_ROWS=1, each run with
STS_OOC_DECISION_TRACE=DIR/TAG.trace.jsonl and STS_OOC_MCTS_TRACE=DIR/TAG.mcts.csv.
Prints a JSON summary; exits 1 on any difference.
"""
import json
import re
import sys
from pathlib import Path

SHA = re.compile(r'[0-9a-f]{64}')


def main(root):
    root = Path(root)
    failures = []
    for suffix in ('.trace.jsonl', '.mcts.csv.actions.jsonl'):
        off, on = [(root / (tag + suffix)).read_bytes() for tag in ('off', 'ctm')]
        if not off or off != on:
            failures.append('action/state trace differs or is empty: ' + suffix)
    off = (root / 'off.jsonl').read_text().splitlines()
    on = (root / 'ctm.jsonl').read_text().splitlines()
    header, footer = json.loads(on[0]), json.loads(on[-1])
    spec = header.pop('ctmRows', None)
    count = footer.pop('ctmRows', None)
    # Trajectory rows byte for byte; header/footer after dropping the ctmRows keys.
    if (len(off) < 2 or on[1:-1] != off[1:-1] or header != json.loads(off[0])
            or footer != json.loads(off[-1])):
        failures.append('trajectory/header/footer differ from off')
    if 'ctmRows' in json.loads(off[0]) or 'ctmRows' in json.loads(off[-1]):
        failures.append('off output has ctmRows keys')
    provenance = header.get('provenance') or {}
    artifacts = provenance.get('ctmArtifacts') or []
    if (not artifacts or any(not SHA.fullmatch(a.get('sha256', '')) for a in artifacts)
            or 'silverLeaf' not in provenance
            or provenance.get('rolloutRootTable') != provenance['silverLeaf'].get('rollout_root_table')):
        failures.append('header provenance incomplete')
    if not spec or spec.get('path') != 'ctm.jsonl.ctm.jsonl' or spec.get('rowSchemaVersion') != 'combat_transition_row_v2':
        failures.append('ctmRows header spec missing')
    rows = [json.loads(line) for line in (root / 'ctm.jsonl.ctm.jsonl').read_text().splitlines()]
    battles = [json.loads(line) for line in (root / 'ctm.trace.jsonl').read_text().splitlines()]
    battles = [b for b in battles if b.get('kind') == 'battle']
    if count != len(rows) or len(rows) != len(battles) or not rows:
        failures.append('row count %s / file %d / trace battles %d' % (count, len(rows), len(battles)))
    for i, (row, battle) in enumerate(zip(rows, battles)):
        t = row.get('transition')
        if (row.get('rowSchemaVersion') != 'combat_transition_row_v2' or row.get('fightIdx') != i
                or row.get('sourceSeed') != header['seed'] or row.get('captureStatus') != 'exactly_one'
                or row.get('runValid') is not True or t is None
                or t['pre']['curHp'] != battle['pre']['hp']
                or row['predictorInput']['globals']['curHp'] != battle['pre']['hp']
                or row['floor'] != battle['pre']['floor']
                or (t['combatOutcome'] == 1) != battle['won']):
            failures.append('row %d disagrees with the decision trace' % i)
    rooms = {}
    for row in rows:
        rooms[row['roomClass']] = rooms.get(row['roomClass'], 0) + 1
    summary = {'verdict': 'FAIL' if failures else 'PASS', 'failures': failures, 'rows': len(rows),
               'roomClasses': rooms, 'losses': sum(1 for r in rows if r['transition'] and r['transition']['combatOutcome'] != 1),
               'ctmArtifacts': [a.get('role') for a in artifacts],
               'outcome': {k: footer.get(k) for k in ('heartKilled', 'finalAct', 'finalFloor', 'finalHp')}}
    print(json.dumps(summary, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('usage: heart_ctm_rows_canary.py DIR')
    sys.exit(main(sys.argv[1]))
