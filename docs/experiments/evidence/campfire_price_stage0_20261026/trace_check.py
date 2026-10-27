"""trace_check.py [--prefix] REPLAY.jsonl[.gz] SOURCE.jsonl[.gz] -- exit 0 when the replay's game equals the source game.

--prefix: the replay was stopped early (at act 4); it must equal the source's first rows.

Compares every state row's public record and every decision's (by, selectedKey) and the outcome row's result fields.
The campfire-price observer must not change the run (it prices in a forked child)."""
import gzip, json, sys

def rows(path):
    with (gzip.open(path, 'rt') if path.endswith('.gz') else open(path)) as f:
        for line in f:
            try: r = json.loads(line)
            except json.JSONDecodeError:
                if '--prefix' in sys.argv: return   # the stopped game's last line may be cut
                raise
            if r['type'] == 'state':
                yield ('state', r['index'], r['floor'], json.dumps(r['record'], sort_keys=True))
            elif r['type'] == 'decision':
                yield ('decision', r.get('stateIndex'), r.get('by'), r.get('selectedKey'))
            elif r['type'] == 'outcome':
                yield ('outcome',) + tuple(r.get(k) for k in ('heartKilled', 'finalAct', 'finalFloor', 'complete'))

prefix = '--prefix' in sys.argv
args = [x for x in sys.argv[1:] if x != '--prefix']
a, b = list(rows(args[0])), list(rows(args[1]))
for i, (x, y) in enumerate(zip(a, b)):
    if x != y:
        print(f'MISMATCH at row {i}: replay {str(x)[:200]} vs source {str(y)[:200]}'); sys.exit(1)
if len(a) > len(b) or (not prefix and len(a) != len(b)) or not a:
    print(f'LENGTH replay {len(a)} vs source {len(b)}'); sys.exit(1)
print(f'MATCH {len(a)} of {len(b)} rows'); sys.exit(0)
