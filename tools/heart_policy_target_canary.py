#!/usr/bin/env python3
"""OFF/ON/policy byte-parity check for `heartoutcomegen ... policy` (no seeds).

DIR holds one seed's off.*, on.* and policy.* outputs of the same binary and
environment, each run with STS_OOC_DECISION_TRACE=DIR/TAG.trace.jsonl and
STS_OOC_MCTS_TRACE=DIR/TAG.mcts.csv. Prints a JSON summary; exits 1 on any
difference.
"""
import json
import sys
from pathlib import Path

POLICY_HEADER = ('policyTargets', 'decisionSchema')
POLICY_FOOTER = ('decisions', 'searchedDecisions')


def main(root):
    root = Path(root)
    failures = []
    for suffix in ('.trace.jsonl', '.mcts.csv.actions.jsonl'):
        files = [(root / (tag + suffix)).read_bytes() for tag in ('off', 'on', 'policy')]
        if not files[0] or files.count(files[0]) != 3:
            failures.append('action/state trace differs or is empty: ' + suffix)
    on = (root / 'on.states.jsonl').read_text().splitlines()
    lines = (root / 'policy.states.jsonl').read_text().splitlines()
    rows = [json.loads(line) for line in lines]
    header, footer = rows[0], rows[-1]
    if header.get('policyTargets') is not True or header.get('decisionSchema') != 'ooc-policy-target-v1':
        failures.append('policy header keys missing')
    for key in POLICY_HEADER:
        header.pop(key, None)
    for key in POLICY_FOOTER:
        footer.pop(key, None)
    decisions = [r for r in rows if r.get('type') == 'decision']
    # State rows must match byte for byte; header/footer after dropping the policy keys.
    kept = [line for line, r in zip(lines[1:-1], rows[1:-1]) if r.get('type') != 'decision']
    if (len(on) < 2 or kept != on[1:-1] or header != json.loads(on[0])
            or footer != json.loads(on[-1])):
        failures.append('policy states/header/footer differ from on')
    searched = [d for d in decisions if d.get('searched')]
    if [d['decisionIndex'] for d in decisions] != list(range(len(decisions))):
        failures.append('decision indices are not 0..n-1')
    for d in searched:
        root_row = d['root']
        visits = sum(c['visits'] for c in root_row['candidates'])
        if (visits != root_row['rootVisits'] or root_row['maxVisits'] != max(c['visits'] for c in root_row['candidates'])
                or (d['executed'] and d['selectedKey'] not in {c['key'] for c in root_row['candidates']})):
            failures.append('inconsistent root at decision %d' % d['decisionIndex'])
    # STS_OOC_MCTS_FULL_BUDGET_FRACTION: every root carries the flag or none does,
    # and a flagged root completed its budget without an early stop.
    roots = [d['root'] for d in searched if d.get('root')]
    flagged = [r for r in roots if 'fullBudget' in r]
    if flagged and len(flagged) != len(roots):
        failures.append('fullBudget missing on some roots')
    full = [r for r in flagged if r['fullBudget']]
    for r in full:
        if r['singleton'] or (not r['aborted'] and (
                r['completedSimulations'] != r['requestedSimulations'] or r['earlyStopLock'] or r['earlyStopGap20'])):
            failures.append('full-budget root stopped early or is a singleton')
            break
    mcts_owned = sum(1 for line in (root / 'policy.mcts.csv.actions.jsonl').read_text().splitlines()
                     if json.loads(line).get('executed'))
    summary = {'verdict': 'FAIL' if failures else 'PASS', 'failures': failures,
               'decisions': len(decisions), 'searched': len(searched),
               'executedBySearch': sum(1 for d in decisions if d.get('by') == 'mcts'),
               'mctsActionTraceExecuted': mcts_owned,
               'v4Fallbacks': sum(1 for d in decisions if d.get('v4Fallback')),
               'singletons': sum(1 for d in searched if d['root']['singleton']),
               'earlyStopLocks': sum(1 for d in searched if d['root']['earlyStopLock']),
               'aborted': sum(1 for d in searched if d['root']['aborted']),
               'fullBudget': len(full) if flagged else None,
               'fullBudgetEligible': sum(1 for r in flagged if not r['singleton']) if flagged else None,
               'heart1Encoded': sum(1 for d in searched if d.get('heart1Record') is not None),
               'outcome': {k: footer.get(k) for k in ('heartKilled', 'finalAct', 'finalFloor', 'finalHp')}}
    if summary['executedBySearch'] != mcts_owned:
        failures.append('decision rows disagree with the MCTS action trace')
        summary['verdict'] = 'FAIL'
    print(json.dumps(summary, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('usage: heart_policy_target_canary.py DIR')
    sys.exit(main(sys.argv[1]))
