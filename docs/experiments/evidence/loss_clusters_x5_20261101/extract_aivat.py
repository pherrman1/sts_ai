"""Per-fight replay outcomes from the §698 AIVAT replay of the §676 guard (read-only).
usage: extract_aivat.py /mnt/project-files/aivat-replay-676 OUT.pkl
Row per (seed, arm, fightIdx): encounter, act, room, entry HP (from rows), recorded outcome (replicate 0, identity
checked by the campaign), and outcome/post HP/cpu of replicates 1..4 (fresh combat draws, same entry state)."""
import sys, os, json, gzip, tarfile, pickle, collections
def main(d, outp):
    R = collections.defaultdict(dict)
    for t in sorted(os.listdir(os.path.join(d, 'units'))):
        if not t.endswith('.tar'): continue
        tf = tarfile.open(os.path.join(d, 'units', t))
        for m in tf.getmembers():
            n = os.path.basename(m.name)
            if not (n.startswith('replay-') and n.endswith('.jsonl.gz')): continue
            for line in gzip.decompress(tf.extractfile(m).read()).splitlines():
                if not line.strip(): continue
                r = json.loads(line); k = (r['sourceSeed'], r['arm'], r['fightIdx'])
                R[k]['enc'] = r['encounter']; R[k]['act'] = r['act']; R[k]['room'] = r['roomClass']; R[k]['floor'] = r['floor']
                R[k][r['replicate']] = (r['combatOutcome'], r['post']['curHp'], r.get('cpuSeconds'), r.get('turns'))
    pickle.dump(dict(R), open(outp, 'wb')); print(len(R), 'fights')
if __name__ == '__main__': main(*sys.argv[1:])
