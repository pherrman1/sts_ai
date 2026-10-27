"""How learnable are expert picks? LightGBM lambdarank per decision type, split by run (80/20, 3 folds).
usage: learnability.py decisions.jsonl an_rows.jsonl"""
import collections, hashlib, json, math, sys
import numpy as np, lightgbm as lgb

dec_path, rows_path = sys.argv[1:3]
recs = {}
for l in open(dec_path):
    d = json.loads(l)
    recs.setdefault((d["run"], d["floor"], d["type"], json.dumps(sorted(set(d["labels"])))), d["record"])
rows = [json.loads(l) for l in open(rows_path)]

def deck_feats(rec):
    cards = rec["obs.deck.cards"]
    return [len(cards), cards.count(321), cards.count(104), sum(rec["obs.deck.upgrades"])]

vocab = {}
def vid(s): return vocab.setdefault(s, len(vocab))

def feats(r, i, lab, rec):
    fo = rec["obs.fixed_observation"]
    base = lab.split("+")[0]
    copies = 0
    for c, u in zip(rec["obs.deck.cards"], rec["obs.deck.upgrades"]):
        pass
    return [vid(base), "+" in lab, fo[0] / max(1, fo[1]), fo[1], fo[2], fo[3], rec["obs.act"]] + deck_feats(rec) + \
           [sum(1 for l in r["labels"] if l.split("+")[0] == base) - 1]

TYPES = {"card": lambda t: t.startswith("card_reward"), "rest": lambda t: t == "rest",
         "boss_relic": lambda t: t == "boss_relic", "smith": lambda t: t == "smith", "map": lambda t: t == "map"}
for name, pred in TYPES.items():
    rs = [r for r in rows if pred(r["type"])]
    X, Xs, y, grp, runs, stu = [], [], [], [], [], []
    for r in rs:
        rec = recs.get((r["run"], r["floor"], r["type"], json.dumps(sorted(set(r["labels"])))))
        if rec is None: continue
        for i, lab in enumerate(r["labels"]):
            f = feats(r, i, lab, rec)
            X.append(f); Xs.append(f + [math.log(max(r["p"][i], 1e-6))]); y.append(int(i == r["expert"]))
        grp.append(len(r["labels"])); runs.append(r["run"]); stu.append(r["argmax"] == r["expert"])
    X = np.array(X, float); Xs = np.array(Xs, float); y = np.array(y); grp = np.array(grp)
    starts = np.concatenate([[0], np.cumsum(grp)[:-1]])
    res = collections.defaultdict(list)
    for fold in range(3):
        test = np.array([int(hashlib.md5((u + str(fold)).encode()).hexdigest(), 16) % 5 == 0 for u in runs])
        for tag, M in (("no_student", X), ("with_student", Xs)):
            def sel(mask):
                idx = np.concatenate([np.arange(s, s + g) for s, g, m in zip(starts, grp, mask) if m])
                return M[idx], y[idx], grp[mask]
            Xtr, ytr, gtr = sel(~test); Xte, yte, gte = sel(test)
            ds = lgb.Dataset(Xtr, ytr, group=gtr, categorical_feature=[0])
            m = lgb.train({"objective": "lambdarank", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 20,
                           "verbose": -1, "lambdarank_truncation_level": 3, "eval_at": [1]}, ds, num_boost_round=300)
            sc = m.predict(Xte); o = 0; hit = 0
            for g in gte:
                hit += yte[o + int(np.argmax(sc[o:o + g]))]; o += g
            res[tag].append(hit / len(gte))
        res["student"].append(float(np.mean(np.array(stu)[test])))
    print(name, "decisions", len(grp), {k: round(float(np.mean(v)), 3) for k, v in res.items()}, flush=True)
