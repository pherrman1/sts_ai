"""#1058: compact root rows and wire rows from the §797 budget-ladder unit tars (share budget-ladder-roots/units).

usage: python3 tools/turn_plan/extract_roots.py UNITS_DIR OUT_DIR
Writes OUT_DIR/roots_compact.jsonl.gz (root rows without `wire`) and OUT_DIR/roots_wire.jsonl.gz (rows with `wire`,
input of `one_combat turnplanenum`). Every root row of every tar is kept; filter_eval.py applies the row rules.
"""
import glob, gzip, json, sys, tarfile

src, out = sys.argv[1], sys.argv[2]
out_c = gzip.open(out + '/roots_compact.jsonl.gz', 'wt')
out_w = gzip.open(out + '/roots_wire.jsonl.gz', 'wt')
n = 0
for t in sorted(glob.glob(src + '/*.tar')):
    with tarfile.open(t) as tf:
        for m in tf.getmembers():
            if not m.name.endswith('.jsonl.gz'): continue
            for line in gzip.decompress(tf.extractfile(m).read()).decode().splitlines():
                if not line: continue
                r = json.loads(line)
                if r.get('kind') != 'root': continue
                w = r.pop('wire', None)
                out_c.write(json.dumps(r) + '\n')
                if w is not None:
                    r['wire'] = w
                    out_w.write(json.dumps(r) + '\n')
                n += 1
out_c.close(); out_w.close()
print('rows', n)
