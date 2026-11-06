"""Offline critic ceiling check (stage 0 of the act-1 critic plan): how much of a run's Heart outcome can a critic
trained offline on many recorded PPO games predict, per act, compared with the online PPO critic the actors logged?

No games are played. Inputs are recorded PPO trajectory parts (traj-NNNN-pXX.jsonl.gz, schema heart1-ppo-traj-v1).

    python3 tools/heart1/critic_ceiling.py fit-net --init net-0399.bin --train 'A/parts/traj-0*.jsonl.gz' \
        --exclude-from 'A/parts/traj-04*.jsonl.gz' --per-game 8 --epochs 3 --out critic.pt
    python3 tools/heart1/critic_ceiling.py fit-gbm --train ... --per-game 8 --out gbm.json
    python3 tools/heart1/critic_ceiling.py evaluate --test 'A/parts/traj-04*.jsonl.gz' --net critic.pt \
        --gbm gbm.json --out report.json

Estimators, each a probability of a Heart kill per net decision (sources heart1_ppo and heart1_ppo_single):
  online  the "value" each decision line carries (the actor net's value head, the critic PPO trained with),
          clipped to [EPS, 1 - EPS] for the log loss.
  net     a copy of --init (all of the actor's inputs, ppo_model.featurize) whose value head is refitted as a
          logit with binary cross-entropy on the game's outcome; trunk and head train, the policy is not used.
  gbm     xgboost on flat_features(): every record field enters (bags of ids, per-id counts and counters, map
          aggregates); RECORD_FIELDS lists each field and how it enters, and an unknown field is an error.
Training rows: per game, the first net decision of each act plus --per-game more drawn uniformly (seeded by the game
seed), so long games do not dominate; 5% of the training games (by seed hash) are the early-stopping split.

evaluate scores every net decision of the test games and reports, per act (1-4) and over all decisions: n, AUC,
log loss, Brier, EV = 1 - Var(y - v) / Var(y) against the game's outcome, and the sd of the GAE advantages
(gamma 1, terminal reward 1{Heart}) at lambda --lam and at lambda 1, computed with that estimator's values.
Differences net - online and gbm - online in act-1 and all-decision log loss and EV get a game-cluster bootstrap CI.
The decision rule (PREREG critic_ceiling_20261106) is applied in "verdict".

Bound worth keeping in mind (no code): with a 0/1 outcome, a critic's MSE against the outcome is Var(y) (1 - EV), so an
EV gain of d removes only d * Var(y) of the lambda-1 advantage variance.
"""
import argparse
import functools
import glob
import gzip
import hashlib
import json
import math
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SCHEMA = "heart1-ppo-traj-v1"
NET_SOURCES = ("heart1_ppo", "heart1_ppo_single")
EPS = 1e-4
ACTS = (1, 2, 3, 4)

# Every record field and how flat_features() uses it (an unlisted field raises: the GBM must see all inputs).
RECORD_FIELDS = {
    "obs.fixed_observation": "each entry (hp, max hp, gold, floor, boss, toSelect, ascension, 3 keys) + hp/max hp",
    "obs.act": "value",
    "obs.deck.cards": "count per card id, deck size",
    "obs.deck.upgrades": "upgraded count per card id, upgraded total",
    "obs.deck.misc": "sum and max per card id (searing blow / genetic algorithm style counters), total",
    "obs.relics.relics": "one indicator per relic id, relic count",
    "obs.relics.relic_counters": "counter per relic id",
    "obs.potions": "count per potion id (0 invalid, 1 empty slot), filled slots",
    "obs.v2.run_counters": "each entry",
    "obs.v2.fought": "count per encounter id, number fought",
    "obs.map.xs": "map aggregates (map_dag_features) with ys, roomTypes, pathXs, mapX, mapY",
    "obs.map.ys": "map aggregates",
    "obs.map.roomTypes": "count per room type among reachable nodes; elite min/max and rest distance ahead",
    "obs.map.pathXs": "map aggregates (edges)",
    "obs.mapX": "value + map aggregates",
    "obs.mapY": "value + map aggregates",
    "obs.map.burningEliteX": "burning elite reachable indicator",
    "obs.map.burningEliteY": "burning elite reachable indicator",
    "screen_state": "one indicator per value",
    "select_screen_type": "one indicator per value",
    "cards_offered.cards": "count per offered card id, number offered",
    "cards_offered.upgrades": "upgraded offered count per card id",
    "relics_offered": "indicator per offered relic id",
    "potions_offered": "count per offered potion id",
    "offer_prices": "min, max, sum of prices >= 0, number priced",
    "fixed_actions": "count per action id; gold sum; card/relic/potion ids per action",
    "paths_offered": "count; per offered path destination room type count; burning elite reach count",
}


# ---------------------------------------------------------------- reading trajectories

def _unit(seed, salt):
    h = hashlib.sha256(f"{salt}:{seed}".encode()).digest()
    return int.from_bytes(h[:8], "little") / 2.0 ** 64


def read_part(path):
    """Games of one part: [{"seed", "y", "outcome", "steps": [decision rows in idx order]}] (net decisions only).
    A decision without its game line (a part cut mid-game) is dropped; a game line with another schema raises."""
    pending, games = {}, []
    with (gzip.open(path, "rt") if path.endswith(".gz") else open(path)) as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["type"] == "decision":
                if row.get("source") in NET_SOURCES:
                    row.pop("logits", None)
                    pending.setdefault(row["seed"], []).append(row)
            elif row["type"] == "game":
                if row.get("schema") != SCHEMA:
                    raise ValueError(f"{path}: schema {row.get('schema')} is not {SCHEMA}")
                steps = sorted(pending.pop(row["seed"], []), key=lambda r: r["idx"])
                y = 1.0 if row["outcome"].get("heart_kill") else 0.0
                games.append({"seed": str(row["seed"]), "y": y, "outcome": row["outcome"], "steps": steps})
    return games


def act_of(step):
    a = step.get("act")
    if a is None:
        a = step["record"].get("obs.act", 0)
    return int(min(max(int(a), 1), 4))


def select_steps(game, per_game):
    """First net decision of each act plus per_game more drawn uniformly (seeded by the game seed)."""
    steps = game["steps"]
    keep, seen = set(), set()
    for i, s in enumerate(steps):
        a = act_of(s)
        if a not in seen:
            seen.add(a); keep.add(i)
    rest = [i for i in range(len(steps)) if i not in keep]
    rng = random.Random(int(hashlib.sha256(game["seed"].encode()).hexdigest()[:16], 16))
    keep.update(rng.sample(rest, min(per_game, len(rest))))
    return sorted(keep)


def expand(patterns):
    out = []
    for p in patterns:
        hits = sorted(glob.glob(os.path.expanduser(p)))
        if not hits:
            raise ValueError(f"no files match {p}")
        out.extend(hits)
    return sorted(set(out))


def _train_part(path, per_game, want_feat, trim_map, exclude, game_frac=1.0):
    import ppo_model
    rows = []
    for g in read_part(path):
        if g["seed"] in exclude or _unit(g["seed"], "frac") >= game_frac:
            continue
        for i in select_steps(g, per_game):
            s = g["steps"][i]
            rec = s["record"]
            rows.append({"seed": g["seed"], "y": g["y"], "act": act_of(s),
                         "feat": ppo_model.featurize(rec, trim_map) if want_feat else None,
                         "flat": None if want_feat else flat_features(rec)})
    return rows


def load_training(patterns, exclude_patterns, per_game, want_feat, trim_map=False, workers=None, game_frac=1.0):
    files = expand(patterns)
    exclude = set()
    if exclude_patterns:
        for p in expand(exclude_patterns):
            exclude.update(g["seed"] for g in read_part(p))
        files = [f for f in files if f not in set(expand(exclude_patterns))]
    fn = functools.partial(_train_part, per_game=per_game, want_feat=want_feat, trim_map=trim_map, exclude=exclude,
                           game_frac=game_frac)
    rows = []
    workers = workers or min(4, os.cpu_count() or 1)
    if workers > 1 and len(files) > 1:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(workers) as pool:
            for part in pool.imap(fn, files, chunksize=4):
                rows.extend(part)
    else:
        for f in files:
            rows.extend(fn(f))
    rows.sort(key=lambda r: (r["seed"],))
    return rows, files, exclude


# ---------------------------------------------------------------- flat features for the GBM

def flat_features(rec):
    """Every record field as named numeric features (sparse dict); see RECORD_FIELDS."""
    unknown = set(rec) - set(RECORD_FIELDS)
    if unknown:
        raise ValueError(f"record fields without a flat encoding: {sorted(unknown)}")
    import ppo_model
    x = {}

    def add(k, v=1.0):
        x[k] = x.get(k, 0.0) + float(v)

    fo = rec["obs.fixed_observation"]
    for i, v in enumerate(fo):
        add(f"fo{i}", v)
    add("hp_frac", fo[0] / max(fo[1], 1))
    add("act", rec.get("obs.act", 0))
    cards, ups = rec["obs.deck.cards"], rec["obs.deck.upgrades"]
    misc = rec.get("obs.deck.misc") or []
    for i, c in enumerate(cards):
        add(f"card{c}")
        if i < len(ups) and ups[i]:
            add(f"card_up{c}"); add("deck_up")
        m = misc[i] if i < len(misc) else 0
        if m:
            add(f"card_misc{c}", m); add("deck_misc", m)
            x[f"card_miscmax{c}"] = max(x.get(f"card_miscmax{c}", -1e9), float(m))
    add("deck_n", len(cards))
    for j, v in enumerate(ppo_model.deck_aggregates(rec)):
        add(f"x3_{j}", v)
    counters = rec.get("obs.relics.relic_counters") or []
    for i, r in enumerate(rec["obs.relics.relics"]):
        add(f"relic{r}")
        add(f"relic_ctr{r}", counters[i] if i < len(counters) else 0)
    add("relic_n", len(rec["obs.relics.relics"]))
    for p in rec["obs.potions"]:
        add(f"potion{p}")
        if p > 1:
            add("potion_n")
    for i, v in enumerate(rec.get("obs.v2.run_counters") or []):
        add(f"run{i}", v)
    for e in rec.get("obs.v2.fought") or []:
        add(f"fought{e}"); add("fought_n")
    add("mapX", rec["obs.mapX"]); add("mapY", rec["obs.mapY"])
    add(f"screen{rec['screen_state']}"); add(f"select{rec['select_screen_type']}")
    if rec["obs.map.xs"]:
        minE, maxE, dR, reach, dest, cone, burn = ppo_model.map_dag_features(rec)
        for j, ok in enumerate(reach):
            if ok:
                add(f"reach_room{rec['obs.map.roomTypes'][j]}"); add("reach_n")
        front = [c for c in cone] or [(0, 0, ppo_model.MAP_AGG_CAP)]
        add("path_minE", min(c[0] for c in front)); add("path_maxE", max(c[1] for c in front))
        add("path_dR", min(c[2] for c in front))
        for d in dest:
            add(f"path_room{d}")
        add("path_burn", sum(burn))
    add("paths_n", len(rec["paths_offered"]))
    oups = rec["cards_offered.upgrades"]
    for i, c in enumerate(rec["cards_offered.cards"]):
        add(f"offer_card{c}"); add("offer_cards_n")
        if i < len(oups) and oups[i]:
            add(f"offer_card_up{c}")
    for r in rec["relics_offered"]:
        add(f"offer_relic{r}")
    for p in rec["potions_offered"]:
        add(f"offer_potion{p}")
    prices = [p for p in (rec.get("offer_prices") or []) if p >= 0]
    if prices:
        add("price_min", min(prices)); add("price_max", max(prices)); add("price_sum", sum(prices))
    add("price_n", len(prices))
    for fa in rec["fixed_actions"]:
        add(f"fa{fa['action']}"); add("fa_gold", fa.get("gold", 0))
        for k in ("card", "relic", "potion"):
            if k in fa and fa[k] is not None and fa[k] >= 0:
                add(f"fa_{k}{fa[k]}")
    return x


def to_csr(flats, vocab):
    from scipy.sparse import csr_matrix
    data, ind, ptr = [], [], [0]
    for f in flats:
        for k, v in f.items():
            j = vocab.get(k)
            if j is not None:
                ind.append(j); data.append(v)
        ptr.append(len(ind))
    return csr_matrix((np.array(data, np.float32), np.array(ind, np.int64), np.array(ptr, np.int64)),
                      shape=(len(flats), len(vocab)))


# ---------------------------------------------------------------- fits

def split_val(rows, frac=0.05):
    tr = [r for r in rows if _unit(r["seed"], "val") >= frac]
    va = [r for r in rows if _unit(r["seed"], "val") < frac]
    return tr, va


def cmd_fit_gbm(argv):
    ap = argparse.ArgumentParser(prog="critic_ceiling.py fit-gbm")
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--exclude-from", nargs="*", default=[])
    ap.add_argument("--per-game", type=int, default=8)
    ap.add_argument("--game-frac", type=float, default=1.0, help="keep this share of training games (seed hash)")
    ap.add_argument("--rounds", type=int, default=3000)
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--eta", type=float, default=0.05)
    ap.add_argument("--min-count", type=int, default=20, help="drop flat features seen in fewer training rows")
    ap.add_argument("--threads", type=int, default=4, help="xgboost threads (keep the PC usable while LONG_C trains)")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    import xgboost as xgb
    rows, files, excl = load_training(a.train, a.exclude_from, a.per_game, want_feat=False, workers=a.workers,
                                      game_frac=a.game_frac)
    tr, va = split_val(rows)
    counts = {}
    for r in tr:
        for k in r["flat"]:
            counts[k] = counts.get(k, 0) + 1
    vocab = {k: i for i, k in enumerate(sorted(k for k, c in counts.items() if c >= a.min_count))}
    dtr = xgb.DMatrix(to_csr([r["flat"] for r in tr], vocab), label=[r["y"] for r in tr])
    dva = xgb.DMatrix(to_csr([r["flat"] for r in va], vocab), label=[r["y"] for r in va])
    params = {"objective": "binary:logistic", "eval_metric": "logloss", "max_depth": a.depth, "eta": a.eta,
              "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 20, "tree_method": "hist", "seed": 0,
              "nthread": a.threads}
    bst = xgb.train(params, dtr, a.rounds, evals=[(dva, "val")], early_stopping_rounds=100, verbose_eval=200)
    model_path = a.out + ".ubj"
    bst.save_model(model_path)
    meta = {"kind": "critic_ceiling_gbm", "model": os.path.basename(model_path), "vocab": sorted(vocab, key=vocab.get),
            "best_iteration": int(bst.best_iteration), "train_rows": len(tr), "val_rows": len(va),
            "train_files": len(files), "excluded_seeds": len(excl), "per_game": a.per_game,
            "params": params, "rounds": a.rounds, "game_frac": a.game_frac}
    json.dump(meta, open(a.out, "w"), indent=1)
    print(f"gbm: {len(tr)} train / {len(va)} val rows, {len(vocab)} features, best iteration {bst.best_iteration}")


class Gbm:
    def __init__(self, path):
        import xgboost as xgb
        self.meta = json.load(open(path))
        self.vocab = {k: i for i, k in enumerate(self.meta["vocab"])}
        self.bst = xgb.Booster()
        self.bst.load_model(os.path.join(os.path.dirname(os.path.abspath(path)), self.meta["model"]))
        self.xgb = xgb

    def predict(self, recs):
        m = self.xgb.DMatrix(to_csr([flat_features(r) for r in recs], self.vocab))
        return self.bst.predict(m, iteration_range=(0, self.meta["best_iteration"] + 1)).astype(np.float64)


def _net_logits(net, store, idx, device, amp):
    import torch
    import ppo_model
    b = ppo_model.batch_to(store.batch(idx), device)
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp and device.type == "cuda"):
        _, value, _ = net.heads_out(net.trunk(b), b)
    return value.float()


def cmd_fit_net(argv):
    ap = argparse.ArgumentParser(prog="critic_ceiling.py fit-net")
    ap.add_argument("--init", required=True, help="actor net .bin whose trunk starts the critic")
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--exclude-from", nargs="*", default=[])
    ap.add_argument("--per-game", type=int, default=8)
    ap.add_argument("--game-frac", type=float, default=1.0, help="keep this share of training games (seed hash)")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--head-lr", type=float, default=1e-3)
    ap.add_argument("--minibatch", type=int, default=256)
    ap.add_argument("--amp", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--device", default="cuda" if _cuda() else "cpu")
    ap.add_argument("--threads", type=int, default=4, help="torch CPU threads")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    import torch
    import torch.nn.functional as F
    import ppo_model
    torch.set_num_threads(a.threads)
    torch.manual_seed(a.seed)
    device = torch.device(a.device)
    net = ppo_model.PolicyNet.from_bin(a.init).to(device)
    rows, files, excl = load_training(a.train, a.exclude_from, a.per_game, want_feat=True,
                                      trim_map=net.trim_map, workers=a.workers, game_frac=a.game_frac)
    tr, va = split_val(rows)
    ybar = sum(r["y"] for r in tr) / max(len(tr), 1)
    with torch.no_grad():   # the value head becomes a logit head starting at the base rate
        net.value_head.weight.zero_()
        net.value_head.bias.fill_(math.log(max(ybar, EPS) / max(1 - ybar, EPS)))
    head = list(net.value_head.parameters()) + list(net.value_head_norm.parameters())
    hid = {id(p) for p in head}
    opt = torch.optim.Adam([{"params": [p for p in net.parameters() if id(p) not in hid], "lr": a.lr},
                            {"params": head, "lr": a.head_lr}])
    st_tr, st_va = ppo_model.FeatureStore([r["feat"] for r in tr]), ppo_model.FeatureStore([r["feat"] for r in va])
    y_tr = torch.tensor([r["y"] for r in tr], device=device)
    y_va = torch.tensor([r["y"] for r in va], device=device)

    def val_loss():
        net.eval()
        tot = 0.0
        with torch.no_grad():
            for i in range(0, len(va), 1024):
                idx = list(range(i, min(i + 1024, len(va))))
                z = _net_logits(net, st_va, idx, device, bool(a.amp))
                tot += float(F.binary_cross_entropy_with_logits(z, y_va[idx], reduction="sum"))
        return tot / max(len(va), 1)

    best, best_state, log = val_loss(), None, []
    print(f"net: {len(tr)} train / {len(va)} val rows from {len(files)} files; epoch 0 val logloss {best:.5f}")
    rng = random.Random(a.seed)
    for ep in range(1, a.epochs + 1):
        net.train()
        order = list(range(len(tr)))
        rng.shuffle(order)
        for i in range(0, len(order), a.minibatch):
            idx = order[i:i + a.minibatch]
            z = _net_logits(net, st_tr, idx, device, bool(a.amp))
            loss = F.binary_cross_entropy_with_logits(z, y_tr[idx])
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
        vl = val_loss()
        log.append({"epoch": ep, "val_logloss": vl})
        print(f"epoch {ep} val logloss {vl:.5f}")
        if vl < best:
            best, best_state = vl, {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
    if best_state is None:
        best_state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
    torch.save({"kind": "critic_ceiling_net", "init": os.path.abspath(a.init),
                "init_sha256": hashlib.sha256(open(a.init, "rb").read()).hexdigest(), "state": best_state,
                "val_logloss": best, "log": log, "train_rows": len(tr), "val_rows": len(va), "per_game": a.per_game,
                "excluded_seeds": len(excl), "args": vars(a)}, a.out)


def _cuda():
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


class Net:
    def __init__(self, path, device=None):
        import torch
        import ppo_model
        ck = torch.load(path, map_location="cpu", weights_only=False)
        self.device = torch.device(device or ("cuda" if _cuda() else "cpu"))
        self.net = ppo_model.PolicyNet.from_bin(ck["init"])
        self.net.load_state_dict(ck["state"])
        self.net.to(self.device).eval()
        self.meta = {k: v for k, v in ck.items() if k != "state"}

    def predict(self, recs):
        import torch
        import ppo_model
        out = []
        with torch.no_grad():
            for i in range(0, len(recs), 512):
                feats = [ppo_model.featurize(r, self.net.trim_map) for r in recs[i:i + 512]]
                st = ppo_model.FeatureStore(feats)
                z = _net_logits(self.net, st, list(range(len(feats))), self.device, False)
                out.append(torch.sigmoid(z).cpu().numpy().astype(np.float64))
        return np.concatenate(out) if out else np.zeros(0)


# ---------------------------------------------------------------- metrics

def gae_adv(y, v, lam):
    """GAE advantages of one game: gamma 1, reward 0 except y at the last step, value 0 after the last step."""
    n = len(v)
    adv = np.zeros(n)
    last = 0.0
    for t in range(n - 1, -1, -1):
        nxt = v[t + 1] if t + 1 < n else 0.0
        r = y if t == n - 1 else 0.0
        last = r + nxt - v[t] + lam * last
        adv[t] = last
    return adv


def auc(y, p):
    y = np.asarray(y); p = np.asarray(p)
    pos, neg = int(y.sum()), int(len(y) - y.sum())
    if pos == 0 or neg == 0:
        return None
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p)); ranks[order] = np.arange(1, len(p) + 1)
    ps = p[order]   # average ranks over ties
    i = 0
    while i < len(ps):
        j = i
        while j + 1 < len(ps) and ps[j + 1] == ps[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    return float((ranks[y == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


def logloss(y, p):
    p = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def ev(y, v):
    vy = np.var(y)
    return float(1 - np.var(y - v) / vy) if vy > 0 else None


def summarize(y, v, adv_l, adv_1):
    return {"n": int(len(y)), "heart": float(np.mean(y)) if len(y) else None, "auc": auc(y, v),
            "logloss": float(np.mean(logloss(y, v))) if len(y) else None,
            "brier": float(np.mean((y - v) ** 2)) if len(y) else None, "ev": ev(y, v) if len(y) else None,
            "sd_adv_lam": float(np.std(adv_l)) if len(y) else None, "sd_adv_1": float(np.std(adv_1)) if len(y) else None}


def game_sums(gid, y, v, G):
    """Per-game sums for the cluster bootstrap of log loss and EV: n, sum e, sum e^2, sum y, sum y^2, sum ll."""
    e = y - v
    out = np.zeros((G, 6))
    for col, w in enumerate((np.ones_like(y), e, e * e, y, y * y, logloss(y, v))):
        np.add.at(out[:, col], gid, w)
    return out


def stats_from_sums(S):
    """S (..., G, 6) weighted sums -> (log loss, EV) over the last-but-one axis."""
    n, se, se2, sy, sy2, sll = (S[..., k] for k in range(6))
    var_e = se2 / n - (se / n) ** 2
    var_y = sy2 / n - (sy / n) ** 2
    return sll / n, 1 - var_e / var_y


def bootstrap_diff(gid, y, va, vb, G, B, seed):
    """Point and percentile CI (2.5/97.5 and 1.25/98.75) of (b - a) in log loss and EV, resampling games."""
    Sa, Sb = game_sums(gid, y, va, G), game_sums(gid, y, vb, G)
    keep = Sa[:, 0] > 0
    Sa, Sb = Sa[keep], Sb[keep]
    la, ea = stats_from_sums(Sa.sum(0)); lb, eb = stats_from_sums(Sb.sum(0))
    rng = np.random.default_rng(seed)
    W = rng.multinomial(len(Sa), np.full(len(Sa), 1.0 / len(Sa)), size=B).astype(np.float64)   # (B, G')
    la_b, ea_b = stats_from_sums(np.einsum("bg,gk->bk", W, Sa))
    lb_b, eb_b = stats_from_sums(np.einsum("bg,gk->bk", W, Sb))
    dl, de = lb_b - la_b, eb_b - ea_b

    def ci(d, q):
        return [float(np.percentile(d, q)), float(np.percentile(d, 100 - q))]
    return {"games": int(len(Sa)), "logloss_diff": float(lb - la), "logloss_ci95": ci(dl, 2.5),
            "logloss_ci975": ci(dl, 1.25), "ev_diff": float(eb - ea), "ev_ci95": ci(de, 2.5), "ev_ci975": ci(de, 1.25)}


def verdict(boot, ev_margin):
    """PREREG rule: an offline estimator is BETTER on a scope when its log-loss difference vs online has a 97.5% CI
    (Bonferroni over net/gbm) entirely below 0 and its EV gain is at least ev_margin (point estimate). GO for stage 1
    when some estimator is BETTER on act 1 or on all decisions; otherwise NO_GO."""
    out = {}
    for name, scopes in boot.items():
        out[name] = {sc: ("BETTER" if b["logloss_ci975"][1] < 0 and b["ev_diff"] >= ev_margin else "NOT_BETTER")
                     for sc, b in scopes.items()}
    go = any(v == "BETTER" for d in out.values() for v in d.values())
    return {"by_estimator": out, "ev_margin": ev_margin, "decision": "GO" if go else "NO_GO"}


def cmd_evaluate(argv):
    ap = argparse.ArgumentParser(prog="critic_ceiling.py evaluate")
    ap.add_argument("--test", nargs="+", required=True)
    ap.add_argument("--net", default="")
    ap.add_argument("--gbm", default="")
    ap.add_argument("--lam", type=float, default=0.97)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--boot-seed", type=int, default=20261106)
    ap.add_argument("--ev-margin", type=float, default=0.02)
    ap.add_argument("--train-seeds-from", nargs="*", default=[], help="parts used in training: test must not share seeds")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    files = expand(a.test)
    train_seeds = set()
    for p in (expand(a.train_seeds_from) if a.train_seeds_from else []):
        train_seeds.update(g["seed"] for g in read_part(p))
    ests = {"online": None}
    if a.net:
        ests["net"] = Net(a.net)
    if a.gbm:
        ests["gbm"] = Gbm(a.gbm)
    cols = {k: [] for k in ("gid", "y", "act", "first") + tuple(ests)}
    advs = {k: {"lam": [], "one": []} for k in ests}
    seeds, gid = set(), 0
    for path in files:
        for g in read_part(path):
            if g["seed"] in seeds:
                raise ValueError(f"seed {g['seed']} twice in the test parts")
            if g["seed"] in train_seeds:
                raise ValueError(f"test seed {g['seed']} is in the training parts")
            seeds.add(g["seed"])
            if not g["steps"]:
                continue
            recs = [s["record"] for s in g["steps"]]
            vals = {"online": np.clip(np.array([float(s["value"]) for s in g["steps"]]), EPS, 1 - EPS)}
            for k, m in ests.items():
                if m is not None:
                    vals[k] = np.clip(m.predict(recs), EPS, 1 - EPS)
            n = len(recs)
            cols["gid"].extend([gid] * n); cols["y"].extend([g["y"]] * n)
            cols["act"].extend(act_of(s) for s in g["steps"]); cols["first"].extend([1] + [0] * (n - 1))
            for k in ests:
                cols[k].extend(vals[k].tolist())
                advs[k]["lam"].extend(gae_adv(g["y"], vals[k], a.lam).tolist())
                advs[k]["one"].extend(gae_adv(g["y"], vals[k], 1.0).tolist())
            gid += 1
    C = {k: np.asarray(v, dtype=np.float64) for k, v in cols.items()}
    gids = C["gid"].astype(np.int64)
    scopes = {"all": np.ones(len(C["y"]), bool), "first_decision": C["first"] == 1}
    for act in ACTS:
        scopes[f"act{act}"] = C["act"] == act
    report = {"schema": "critic-ceiling-report-v1", "test_files": len(files), "games": gid, "lam": a.lam,
              "estimators": {}, "bootstrap": {}, "meta": {}}
    for k in ests:
        A_l, A_1 = np.asarray(advs[k]["lam"]), np.asarray(advs[k]["one"])
        report["estimators"][k] = {sc: summarize(C["y"][m], C[k][m], A_l[m], A_1[m]) for sc, m in scopes.items()}
        if ests[k] is not None:
            report["meta"][k] = ests[k].meta if k == "gbm" else {x: y for x, y in ests[k].meta.items() if x != "log"}
    for k in ests:
        if k == "online":
            continue
        report["bootstrap"][k] = {sc: bootstrap_diff(gids[m], C["y"][m], C["online"][m], C[k][m], gid, a.boot,
                                                    a.boot_seed) for sc in ("act1", "all") for m in [scopes[sc]]}
    report["verdict"] = verdict(report["bootstrap"], a.ev_margin) if report["bootstrap"] else None
    json.dump(report, open(a.out, "w"), indent=1, default=str)
    for k, d in report["estimators"].items():
        print(k, " ".join(f"{sc}: auc {d[sc]['auc'] and round(d[sc]['auc'], 3)} ev {d[sc]['ev'] and round(d[sc]['ev'], 3)}"
                          for sc in ("act1", "act2", "act3", "act4", "all")))
    if report["verdict"]:
        print("verdict", report["verdict"]["decision"], report["verdict"]["by_estimator"])


def main():
    cmds = {"fit-net": cmd_fit_net, "fit-gbm": cmd_fit_gbm, "evaluate": cmd_evaluate}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(f"usage: critic_ceiling.py {{{','.join(cmds)}}} ...")
    cmds[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
