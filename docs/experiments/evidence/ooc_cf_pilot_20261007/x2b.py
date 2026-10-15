import math
class Tree:
    def __init__(self, path):
        toks = open(path).read().split()
        i = 0
        assert toks[i] == 'nfeat'; n = int(toks[i+1]); i += 2
        self.names = []
        for _ in range(n):
            assert toks[i] == 'feat'; self.names.append(toks[i+1]); i += 2
        assert toks[i] == 'logistic'; i += 2
        assert toks[i] == 'base_score'; b = float(toks[i+1]); i += 2
        self.base = math.log(b/(1-b))
        assert toks[i] == 'ntrees'; nt = int(toks[i+1]); i += 2
        self.trees = []
        for t in range(nt):
            assert toks[i] == 'tree'; nn = int(toks[i+2]); i += 3
            nodes = []
            for _ in range(nn):
                if toks[i] == 'L': nodes.append((-1, float(toks[i+1]), 0, 0)); i += 2
                else: nodes.append((int(toks[i+1]), float(toks[i+2]), int(toks[i+3]), int(toks[i+4]))); i += 5
            self.trees.append(nodes)
    def margin(self, x):  # x: list aligned with self.names
        m = self.base
        for tr in self.trees:
            j = 0
            while tr[j][0] >= 0:
                f, th, y, no = tr[j]
                j = y if x[f] < th else no
            m += tr[j][1]
        return m
    def predict(self, x):
        return 1/(1+math.exp(-self.margin(x)))
