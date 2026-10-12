import csv, glob, sys, numpy as np
sys.path.insert(0, '/home/user/sts_ai')
from tools.vwin_refresh_dataset import source_split
from tools.vwin_refresh_contract import MAP_PREFIX
def load(root='/tmp/claude-0/a401'):
    X=[]; y=[]; seeds=[]; splits=[]; names=None
    for mp in sorted(glob.glob(f'{root}/c*/vwin334-cloud/shards/seed-*.map.csv')):
        ro = mp.replace('.map.csv', '.runout.csv')
        lab = {}
        for r in csv.DictReader(open(ro)):
            if r['trajectoryValid'] == '1' and r['finalWon'] in ('0','1'):
                lab[(r['sourceSeed'], r['branchId'])] = int(r['finalWon'])
        rd = csv.reader(open(mp)); h = next(rd)
        st = len(MAP_PREFIX); en = h.index('fmDElite') if 'fmDElite' in h else len(h)
        hn = h[st:]
        if names is None: names = hn
        assert hn == names
        for row in rd:
            k = (row[0], row[1])
            if k not in lab: continue
            sp = source_split(int(row[0]))
            if sp == 'TEST': continue          # never open TEST
            X.append(np.asarray(row[st:], dtype=np.float32)); y.append(lab[k]); seeds.append(int(row[0])); splits.append(sp)
    return np.vstack(X), np.array(y, np.float32), np.array(seeds), np.array(splits), names
if __name__ == '__main__':
    X, y, s, sp, n = load()
    print(X.shape, y.mean(), len(set(s)), {k:(sp==k).sum() for k in set(sp)}, {k:len(set(s[sp==k])) for k in set(sp)})
    print(n[:5], n[-14:])
    np.savez_compressed('/tmp/claude-0/a401/work/a0.npz', X=X, y=y, seeds=s, splits=sp, names=np.array(n))
