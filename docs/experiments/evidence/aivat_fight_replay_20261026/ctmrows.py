import sys, tarfile, gzip, os
ds, outdir = sys.argv[1], sys.argv[2]; fh = {}
for p in open(ds + '.list').read().split():
    with tarfile.open(p) as tf:
        for m in tf.getmembers():
            n = os.path.basename(m.name)
            if not n.endswith('.ctm.jsonl.gz'): continue
            arm = n.rsplit('-', 1)[0]
            if arm not in fh: fh[arm] = open(f'{outdir}/{arm}.jsonl', 'wb')
            fh[arm].write(gzip.decompress(tf.extractfile(m).read()))
