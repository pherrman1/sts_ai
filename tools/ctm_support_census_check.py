#!/usr/bin/env python3
"""#418 G14: the native runtime support predicate must match the Python support census.

`combat_transition_runtime_probe ARTIFACT CORPUS.jsonl support-only` prints one line per
corpus row ({"supported", "reason", "index"}). Over the same corpus the census
(combat_transition_final_support_census.py) hashed the supported row indices as
"{index}\\n" lines; this compares the row count, the supported count and that digest.

    python tools/ctm_support_census_check.py --runtime runtime-support-all.jsonl \\
        --census PARENT/final-support-census-v1.json [--output check.json]
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def check(runtime, census, group='all'):
    expected = json.loads(Path(census).read_text())['groups'][group]
    digest, rows, supported, reasons = hashlib.sha256(), 0, 0, Counter()
    with open(runtime, encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['index'] != rows:
                raise ValueError(f'runtime line {rows} has index {row["index"]}')
            if row['supported']:
                supported += 1
                digest.update(f'{rows}\n'.encode())
            else:
                reasons[row['reason']] += 1
            rows += 1
    result = dict(group=group, rows=rows, supported=supported, supportedIndexSha256=digest.hexdigest(),
                  censusRows=expected['counts']['rows'], censusSupported=expected['counts']['supported'],
                  censusSupportedIndexSha256=expected['supportedIndexSha256'], runtimeReasons=dict(reasons))
    result['match'] = (rows, supported, result['supportedIndexSha256']) == (
        result['censusRows'], result['censusSupported'], result['censusSupportedIndexSha256'])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--census', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    result = check(args.runtime, args.census)
    text = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.output:
        with open(args.output, 'x', encoding='utf-8') as stream:
            stream.write(text)
    print(text, end='')
    if not result['match']:
        raise SystemExit('runtime support differs from the census')


if __name__ == '__main__':
    main()
