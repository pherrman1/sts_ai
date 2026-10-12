import numpy as np, sys
sys.path.insert(0, '/home/user/sts_ai')
from tools.analysis.vwin_tree_utils import load_trees


class Forest:
    """Vectorized evaluator for the compact native tree format (same '<' routing)."""
    def __init__(self, path):
        self.feats, trees, self.lg, _, self.bm = load_trees(path)
        T = len(trees); M = max(len(t) for t in trees)
        self.fi = np.zeros((T, M), np.int32); self.thr = np.zeros((T, M), np.float32)
        self.yes = np.zeros((T, M), np.int32); self.no = np.zeros((T, M), np.int32)
        self.leaf = np.zeros((T, M), np.float64)
        for t, nodes in enumerate(trees):
            for k, n in enumerate(nodes):
                if n[0] == 'L':
                    self.leaf[t, k] = n[1]; self.yes[t, k] = k; self.no[t, k] = k
                    self.thr[t, k] = np.inf
                else:
                    _, f, th, y, nn = n
                    self.fi[t, k] = f; self.thr[t, k] = th; self.yes[t, k] = y; self.no[t, k] = nn
        def d(nodes, i):
            return 0 if nodes[i][0] == 'L' else 1 + max(d(nodes, nodes[i][3]), d(nodes, nodes[i][4]))
        self.depth = max(d(t, 0) for t in trees); self.T = T
        self.trees = trees

    def margin(self, X, chunk=2000):
        X = np.asarray(X, np.float32); out = np.empty(len(X))
        tix = np.arange(self.T)[None, :]
        for a in range(0, len(X), chunk):
            x = X[a:a + chunk]; n = len(x)
            idx = np.zeros((n, self.T), np.int32); r = np.arange(n)[:, None]
            for _ in range(self.depth):
                v = x[r, self.fi[tix, idx]]
                idx = np.where(v < self.thr[tix, idx], self.yes[tix, idx], self.no[tix, idx])
            out[a:a + n] = self.bm + self.leaf[tix, idx].sum(1)
        return out

    def predict(self, X):
        m = self.margin(X)
        return 1 / (1 + np.exp(-m)) if self.lg else m
