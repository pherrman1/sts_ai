"""python3 -I compare.py OUT_DIR AB_UNITS SEED...: identity of the M0-default games against the value-level A/B arms.
def (unset) and exp (explicit calibration) against arm M, off (=0) against arm A: every record after the header, and
every CTM row."""
import gzip, sys
from pathlib import Path

out, ab = Path(sys.argv[1]), Path(sys.argv[2])


def lines(p):
    if p.exists():
        return p.read_text().splitlines()
    return gzip.decompress(p.with_name(p.name + '.gz').read_bytes()).decode().splitlines()


ok = True
for seed in sys.argv[3:]:
    for mine, arm in (('def', 'M'), ('exp', 'M'), ('off', 'A'), ('def', 'A')):
        for kind in ('jsonl', 'ctm.jsonl'):
            a = lines(out / f'{mine}-{seed}.{kind}')
            b = lines(ab / seed / f'{arm}-{seed}.{kind}')
            skip = 1 if kind == 'jsonl' else 0
            same = a[skip:] == b[skip:]
            first = next((i for i, (x, y) in enumerate(zip(a[skip:], b[skip:])) if x != y), None)
            print(f'{seed} {mine} vs {arm} {kind}: {len(a)} vs {len(b)} lines, identical={same}'
                  + ('' if same else f' (first difference at record {first})'))
            if (mine, arm) != ('def', 'A'):
                ok &= same
print('PASS' if ok else 'FAIL')
