#!/usr/bin/env python3
"""Export complete AZ gen0 / gen1b-A/B games that reach Act 4 (first act-4 state row verbatim + Heart outcome).
usage: export_az_a4.py OUT.jsonl.gz GEN0_TAR_DIR GEN1B_TAR_DIR   (each dir: w*.tar with out/units/SEED/<arm>-SEED.jsonl.gz)"""
import gzip, io, json, os, sys, tarfile, glob, collections

def games(tar_dir, campaign):
    for path in sorted(glob.glob(os.path.join(tar_dir, 'w*.tar'))):
        tf = tarfile.open(path)
        for m in tf.getmembers():
            b = os.path.basename(m.name)
            if not m.isfile() or not b.endswith('.jsonl.gz') or b.endswith(('.ctm.jsonl.gz', '.ooc.jsonl.gz')): continue
            arm = b.split('-')[0]
            camp = campaign if campaign == 'az-gen0' else f'{campaign}-{arm}'
            rows = [json.loads(l) for l in gzip.open(io.BytesIO(tf.extractfile(m).read()), 'rt')]
            yield camp, b, rows

def main():
    out, gen0, gen1b = sys.argv[1:4]; c = collections.Counter(); recs = []
    for camp, b, rows in [g for d, n in ((gen0, 'az-gen0'), (gen1b, 'az-gen1b-ab')) for g in games(d, n)]:
        c[(camp, 'files')] += 1
        o = [x for x in rows if x.get('type') == 'outcome']
        if not o or not o[-1].get('complete') or not o[-1].get('integrityPassed'): c[(camp, 'incomplete')] += 1; continue
        hdr = [x for x in rows if x.get('type') not in ('outcome', 'state', 'decision')]
        st = [x for x in rows if x.get('type') == 'state' and x.get('act') == 4]
        if not st: continue
        seed = hdr[0].get('seed') if hdr else None
        recs.append(dict(campaign=camp, seed=int(seed), game=b[:-len('.jsonl.gz')], heartKilled=bool(o[-1].get('heartKilled')), entry=st[0]))
        c[(camp, 'a4')] += 1; c[(camp, 'kills')] += recs[-1]['heartKilled']; c[(camp, 'a4_test')] += recs[-1]['seed'] % 4 == 3
    recs.sort(key=lambda r: (r['campaign'], r['seed']))
    with gzip.GzipFile(out, 'wb', mtime=0) as f:
        for r in recs: f.write((json.dumps(r, sort_keys=True) + '\n').encode())
    for k in sorted(c): print(k, c[k])
    print('total', len(recs))

if __name__ == '__main__':
    main()
