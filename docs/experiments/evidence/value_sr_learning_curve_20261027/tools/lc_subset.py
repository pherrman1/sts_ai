"""SR head data learning curve (../PLAN.md): nested source subsets of SR_crn_r2's training data.

usage: lc_subset.py K OUT_DIR GROUPS.jsonl.gz ROWS_FILE...
Keeps a training source when int(sha256("lc:<seed>")) % 4 < K (K = 1: 25 %, 2: 50 %, 4: everything), so the 25 %
subset is inside the 50 % subset. The rule is applied to
- the row files distill.py trains on (seed % 8 not 7 = validation and not 6 = selection fold); validation and
  selection files are always kept, so every run is scored on the same folds;
- the sibling-ranking groups whose source seed % 8 != 6; the in-training holdout (seed % 8 == 6) is always kept.
Writes OUT_DIR/rows.txt (one row file per line), OUT_DIR/groups.jsonl.gz and OUT_DIR/subset.json (counts, sha256).
"""
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path


def keep(seed, k):
    return int(hashlib.sha256(f'lc:{seed}'.encode()).hexdigest(), 16) % 4 < k


def seed_of(f):  # distill.py: seed from "-<seed>.capture" in the name
    return int(re.search(r'-(\d+)\.capture', Path(f).name).group(1))


def main(k, out, groups, *rows):
    k, out = int(k), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rep = {'K': k, 'rowFiles': {'train': [0, 0], 'heldOut': 0}, 'groups': {'train': [0, 0], 'holdout': 0}}
    kept = []
    for f in sorted(rows):
        s = seed_of(f)
        if s % 8 in (6, 7):
            rep['rowFiles']['heldOut'] += 1; kept.append(f)
        else:
            rep['rowFiles']['train'][1] += 1
            if keep(s, k):
                rep['rowFiles']['train'][0] += 1; kept.append(f)
    (out / 'rows.txt').write_text(''.join(f + '\n' for f in kept))
    with gzip.open(groups, 'rt') as src, gzip.open(out / 'groups.jsonl.gz', 'wt', compresslevel=6) as dst:
        for line in src:
            s = json.loads(line)['seed']
            if s % 8 == 6:
                rep['groups']['holdout'] += 1; dst.write(line)
            else:
                rep['groups']['train'][1] += 1
                if keep(s, k):
                    rep['groups']['train'][0] += 1; dst.write(line)
    rep['groupsSha256'] = hashlib.sha256((out / 'groups.jsonl.gz').read_bytes()).hexdigest()
    rep['groupsInSha256'] = hashlib.sha256(Path(groups).read_bytes()).hexdigest()
    rep['rowsTxtSha256'] = hashlib.sha256((out / 'rows.txt').read_bytes()).hexdigest()
    (out / 'subset.json').write_text(json.dumps(rep, indent=1) + '\n')
    print(json.dumps(rep))


if __name__ == '__main__':
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])
