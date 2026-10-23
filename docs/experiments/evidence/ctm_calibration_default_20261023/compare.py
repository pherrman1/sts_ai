"""python3 -I compare.py OLD NEW EXP SEED...: identity of the guard's arms across the default change.
OLD holds ../ctm_calibration_20261023/run_unit.sh units as of main a103a9b7 on its binary (A unset = raw CTM, C the
explicit table), NEW the same seeds with this change's run_unit.sh and binary (A =0, C unset = the default), EXP the
new binary with C's environment and the explicit table. Compares every record after the header, and every CTM row, and
requires every game to end with a complete, integrity-passed outcome footer."""
import gzip
import json
import sys
from pathlib import Path

old, new, exp = (Path(p) for p in sys.argv[1:4])


def lines(p):
    if p.exists():
        return p.read_text().splitlines()
    return gzip.decompress(p.with_name(p.name + '.gz').read_bytes()).decode().splitlines()


def complete(rows):
    try:
        foot = json.loads(rows[-1])
    except (IndexError, ValueError):
        return False
    return foot.get('type') == 'outcome' and bool(foot.get('complete')) and bool(foot.get('integrityPassed'))


ok = True
for seed in sys.argv[4:]:
    for name, d in (('old', old), ('new', new)):
        for arm in 'AC':
            done = complete(lines(d / f'{arm}-{seed}.jsonl'))
            print(f'{seed} {name} {arm} complete={done}')
            ok &= done
    done = complete(lines(exp / f'C-{seed}.jsonl'))
    print(f'{seed} exp complete={done}')
    ok &= done
    # (left, right, must be identical)
    pairs = (('new A', new / f'A-{seed}', 'old A', old / f'A-{seed}', True),
             ('new C', new / f'C-{seed}', 'old C', old / f'C-{seed}', True),
             ('exp', exp / f'C-{seed}', 'new C', new / f'C-{seed}', True),
             ('new C', new / f'C-{seed}', 'new A', new / f'A-{seed}', False))
    for ln, lp, rn, rp, must in pairs:
        for kind in ('jsonl', 'ctm.jsonl'):
            a = lines(lp.with_name(f'{lp.name}.{kind}'))
            b = lines(rp.with_name(f'{rp.name}.{kind}'))
            skip = 1 if kind == 'jsonl' else 0  # the header holds paths and the git sha
            same = a[skip:] == b[skip:]
            first = next((i for i, (x, y) in enumerate(zip(a[skip:], b[skip:])) if x != y), None)
            print(f'{seed} {ln} vs {rn} {kind}: {len(a)} vs {len(b)} lines, identical={same}'
                  + ('' if same else f' (first difference at record {first})'))
            if must:
                ok &= same
print('PASS' if ok else 'FAIL')
