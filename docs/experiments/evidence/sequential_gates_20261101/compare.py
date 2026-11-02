#!/usr/bin/env python3
"""Part B of PREREG.md: compare replayed §727 arm-A games with the stored records.
usage: compare.py OUT_DIR [OUT_JSON]
Stored: /mnt/project-files/value-chooser-ab/units/<seed>.w*.tar -> A-<seed>.jsonl.gz.
Every state, decision and outcome row is compared exactly, in order (the stored records carry no wall-clock fields).
The header row (configuration and provenance) is compared leaf by leaf; the only allowed differences are
`.producerSha` and a `.policy.model_artifacts[i].path` whose old and new values both end in `/student_sel.bin`
(the run directory differs). The `A-<seed>.ctm.jsonl.gz` rows are compared exactly too.
A game is IDENTICAL only if all three hold. The per-campaign sentinel uses the same rule."""
import glob, gzip, json, os, sys, tarfile

SEEDS = range(111312000, 111312032)
def flat(x, p=''):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from flat(v, f'{p}.{k}')
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from flat(v, f'{p}[{i}]')
    else:
        yield p, x


def header_diffs(ha, hb):
    """Leaf paths that differ, minus the allowlist."""
    fa, fb = dict(flat(ha)), dict(flat(hb))
    out = []
    for k in sorted(set(fa) | set(fb)):
        va, vb = fa.get(k, '<absent>'), fb.get(k, '<absent>')
        if va == vb or k == '.producerSha':
            continue
        if k.startswith('.policy.model_artifacts[') and k.endswith('].path') and str(va).endswith('/student_sel.bin') \
                and str(vb).endswith('/student_sel.bin'):
            continue
        out.append(k)
    return out


def ctm_equal(seed, out):
    old = None
    for p in glob.glob(f'/mnt/project-files/value-chooser-ab/units/{seed}.w*.tar'):
        with tarfile.open(p) as t:
            for m in t.getmembers():
                if m.name.endswith(f'/A-{seed}.ctm.jsonl.gz'):
                    old = t.extractfile(m).read()
    newp = os.path.join(out, f'A-{seed}.ctm.jsonl.gz')
    if old is None or not os.path.exists(newp):
        return None
    return gzip.decompress(old).splitlines() == gzip.decompress(open(newp, 'rb').read()).splitlines()


def rows(blob):
    return [json.loads(l) for l in gzip.decompress(blob).splitlines() if l.strip()]


def stored(seed):
    for p in glob.glob(f'/mnt/project-files/value-chooser-ab/units/{seed}.w*.tar'):
        with tarfile.open(p) as t:
            for m in t.getmembers():
                if m.name.endswith(f'/A-{seed}.jsonl.gz'):
                    return t.extractfile(m).read()
    return None


def main(out, js=None):
    res = {'identical': 0, 'different': 0, 'missing': 0, 'games': {}}
    for s in SEEDS:
        old, newp = stored(s), os.path.join(out, f'A-{s}.jsonl.gz')
        done = open(os.path.join(out, f'A-{s}.done')).read() if os.path.exists(os.path.join(out, f'A-{s}.done')) else ''
        if not old or not os.path.exists(newp) or ' rc=0 ' not in done + ' ':
            res['missing'] += 1; res['games'][s] = {'status': 'missing', 'done': done.strip()}; continue
        ra, rb = rows(old), rows(open(newp, 'rb').read())
        ha = [r for r in ra if r.get('type') == 'header']; hb = [r for r in rb if r.get('type') == 'header']
        hdiff = header_diffs(ha[0], hb[0]) if ha and hb else ['missing header']
        ctm = ctm_equal(s, out)
        a = [r for r in ra if r.get('type') != 'header']; b = [r for r in rb if r.get('type') != 'header']
        first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
        if first is None and len(a) == len(b) and not hdiff and ctm:
            res['identical'] += 1; res['games'][s] = {'status': 'identical', 'rows': len(a)}
        else:
            res['different'] += 1
            i = first if first is not None else min(len(a), len(b))
            keys = sorted({k for k in set(a[i]) | set(b[i]) if a[i].get(k) != b[i].get(k)}) if i < min(len(a), len(b)) else []
            i = None if first is None and len(a) == len(b) else i
            oa = [r for r in a if r.get('type') == 'outcome'][-1:]; ob = [r for r in b if r.get('type') == 'outcome'][-1:]
            res['games'][s] = {'status': 'different', 'rows_old': len(a), 'rows_new': len(b), 'first_diff_row': i,
                               'row_type': None if i is None else (a[i] if i < len(a) else b[i]).get('type'), 'diff_keys': keys[:20],
                               'outcome_equal': oa == ob,
                               'heart_old': oa and oa[0].get('heartKilled'), 'heart_new': ob and ob[0].get('heartKilled'),
                               'header_diff_keys': hdiff[:20], 'ctm_equal': ctm}
    print(json.dumps({k: res[k] for k in ('identical', 'different', 'missing')}))
    for s, g in res['games'].items():
        if g['status'] != 'identical':
            print(s, g)
    if js:
        json.dump(res, open(js, 'w'), indent=1)


if __name__ == '__main__':
    main(*sys.argv[1:])
