#!/usr/bin/env python3
"""#460 offline screen: does the opening hand help a pre-combat outcome model?

Reads combat_transition_row_v2 rows and the matching `one_combat ctmopeninghands`
output (realized hand + resampled hands of the same deck under fresh seeds). Fits
gradient-boosted models with grouped (by source seed) K-fold cross-validation:

  A  pre-combat features only (what the CTM sees: globals, deck, relics, potions)
  B  A + realized opening-hand card counts

and scores on held-out folds:

  conditional  B with the realized hand            (information in the hand)
  marginal     B averaged over the resampled hands (what OOC MCTS could use: the
               hand is not yet drawn when it decides, so it must be sampled)

Targets: death (log loss) and, on wins, HP lost = pre HP - post HP (squared
error; post HP is the RAW post-combat state the CTM predicts). Deltas are B - A
(negative = better) with a 95% bootstrap CI over source seeds.

    python3 tools/ctm_opening_hand_screen.py --rows 'DIR/*/out/main-*.jsonl' \
        --hands HANDS.jsonl --out REPORT.json
"""
import argparse
import glob
import json
import sys

import numpy as np


def load(rows_glob, hands_path):
    hands = {}
    with open(hands_path) as f:
        for line in f:
            h = json.loads(line)
            hands[(h["sourceSeed"], h["fightIdx"])] = h
    rows = []
    for path in sorted(glob.glob(rows_glob)):
        with open(path) as f:
            for line in f:
                r = json.loads(line)
                t = r.get("transition")
                if t is None or not r["runValid"]:
                    continue
                if t["combatOutcome"] not in (1, 2) or t["post"]["smokeBombUsed"]:
                    continue   # victory or death only; escapes are their own CTM head
                h = hands.get((r["sourceSeed"], r["fightIdx"]))
                if h is None:
                    raise SystemExit(f"no hand for seed {r['sourceSeed']} fight {r['fightIdx']}")
                rows.append((r, h))
    return rows


def card_key(c):
    return (c["id"], bool(c["upgraded"]))


def build(rows):
    card_keys, relic_ids, potion_ids, encounters = set(), set(), set(), set()
    for r, h in rows:
        p = r["predictorInput"]
        for c in p["cards"]:
            card_keys.add((c["cardId"], bool(c["upgraded"])))
        relic_ids.update(x["relicId"] for x in p["relics"])
        potion_ids.update(x["potionId"] for x in p["potions"])
        encounters.add(p["globals"]["encounter"])
        for hand in [h["openingHand"]["cards"]] + h["resampledHands"]:
            card_keys.update(card_key(c) for c in hand)
    card_keys = sorted(card_keys)
    ck = {k: i for i, k in enumerate(card_keys)}
    rk = {k: i for i, k in enumerate(sorted(relic_ids))}
    pk = {k: i for i, k in enumerate(sorted(potion_ids))}
    ek = {k: i for i, k in enumerate(sorted(encounters))}
    gnames = ["act", "floor", "curHp", "maxHp", "gold", "roomClass", "lastRoom", "potionCount",
              "potionCapacity", "isBurningElite"]
    n = len(rows)
    nbase = len(gnames) + 1 + len(ek) + len(ck) + len(rk) + len(pk)
    base = np.zeros((n, nbase), np.float32)
    n_alt = len(rows[0][1]["resampledHands"])
    hand = np.zeros((n, len(ck) + 1), np.float32)
    alt = np.zeros((n_alt, n, len(ck) + 1), np.float32)
    death = np.zeros(n, np.float32)
    hp_lost = np.zeros(n, np.float32)
    groups = np.zeros(n, np.int64)

    def hand_vec(out, cards):
        for c in cards:
            out[ck[card_key(c)]] += 1
        out[-1] = len(cards)

    for i, (r, h) in enumerate(rows):
        p = r["predictorInput"]
        g = p["globals"]
        row = base[i]
        for j, name in enumerate(gnames):
            row[j] = float(g[name])
        row[len(gnames)] = g["curHp"] / max(1, g["maxHp"])
        o = len(gnames) + 1
        row[o + ek[g["encounter"]]] = 1
        o += len(ek)
        for c in p["cards"]:
            row[o + ck[(c["cardId"], bool(c["upgraded"]))]] += 1
        o += len(ck)
        for x in p["relics"]:
            row[o + rk[x["relicId"]]] = 1
        o += len(rk)
        for x in p["potions"]:
            row[o + pk[x["potionId"]]] += 1
        hand_vec(hand[i], h["openingHand"]["cards"])
        if len(h["resampledHands"]) != n_alt:
            raise SystemExit("resampled hand count differs between rows")
        for a, cards in enumerate(h["resampledHands"]):
            hand_vec(alt[a, i], cards)
        t = r["transition"]
        death[i] = 1.0 if t["combatOutcome"] == 2 else 0.0
        hp_lost[i] = t["pre"]["curHp"] - t["post"]["curHp"]
        groups[i] = r["sourceSeed"]
    return base, hand, alt, death, hp_lost, groups


def fit_predict(xgb, x_tr, y_tr, x_te_list, objective, seed):
    params = dict(n_estimators=400, learning_rate=0.05, max_depth=6, min_child_weight=5,
                  subsample=0.8, colsample_bytree=0.5, tree_method="hist", n_jobs=4,
                  random_state=seed)
    if objective == "binary":
        m = xgb.XGBClassifier(objective="binary:logistic", eval_metric="logloss", **params)
        m.fit(x_tr, y_tr)
        return [m.predict_proba(x)[:, 1] for x in x_te_list]
    m = xgb.XGBRegressor(objective="reg:squarederror", **params)
    m.fit(x_tr, y_tr)
    return [m.predict(x) for x in x_te_list]


def logloss(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def boot_ci(per_row, groups, reps=2000, seed=0):
    uniq, inv = np.unique(groups, return_inverse=True)
    sums = np.bincount(inv, weights=per_row, minlength=len(uniq))
    counts = np.bincount(inv, minlength=len(uniq)).astype(float)
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(reps):
        idx = rng.integers(0, len(uniq), len(uniq))
        stats.append(sums[idx].sum() / counts[idx].sum())
    return float(per_row.mean()), float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--hands", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    import xgboost as xgb

    rows = load(args.rows, args.hands)
    base, hand, alt, death, hp_lost, groups = build(rows)
    n = len(rows)
    uniq = np.unique(groups)
    rng = np.random.default_rng(args.seed)
    fold_of_seed = dict(zip(rng.permutation(uniq), np.arange(len(uniq)) % args.folds))
    fold = np.array([fold_of_seed[g] for g in groups])

    pred = {k: np.full(n, np.nan) for k in
            ["death_A", "death_B", "death_Bmarg", "hp_A", "hp_B", "hp_Bmarg"]}
    win = death == 0
    for k in range(args.folds):
        tr, te = fold != k, fold == k
        xa_tr, xa_te = base[tr], base[te]
        xb_tr = np.hstack([base[tr], hand[tr]])
        xb_te = np.hstack([base[te], hand[te]])
        xb_alt = [np.hstack([base[te], alt[a, te]]) for a in range(alt.shape[0])]
        (pred["death_A"][te],) = fit_predict(xgb, xa_tr, death[tr], [xa_te], "binary", args.seed)
        out = fit_predict(xgb, xb_tr, death[tr], [xb_te] + xb_alt, "binary", args.seed)
        pred["death_B"][te] = out[0]
        pred["death_Bmarg"][te] = np.mean(out[1:], axis=0)
        trw, tew = tr & win, te & win
        (pred["hp_A"][tew],) = fit_predict(xgb, base[trw], hp_lost[trw], [base[tew]], "reg", args.seed)
        xb_trw = np.hstack([base[trw], hand[trw]])
        out = fit_predict(xgb, xb_trw, hp_lost[trw],
                          [np.hstack([base[tew], hand[tew]])]
                          + [np.hstack([base[tew], alt[a, tew]]) for a in range(alt.shape[0])],
                          "reg", args.seed)
        pred["hp_B"][tew] = out[0]
        pred["hp_Bmarg"][tew] = np.mean(out[1:], axis=0)
        print(f"fold {k + 1}/{args.folds} done", file=sys.stderr)

    report = {"rows": int(n), "seeds": int(len(uniq)), "deaths": int(death.sum()), "wins": int(win.sum()),
              "resampledHands": int(alt.shape[0]), "folds": args.folds, "seed": args.seed,
              "features": {"base": int(base.shape[1]), "hand": int(hand.shape[1])}}
    ll = {k: logloss(pred[f"death_{k}"], death) for k in ["A", "B", "Bmarg"]}
    report["death_logloss"] = {k: float(v.mean()) for k, v in ll.items()}
    report["death_logloss_delta"] = {
        "conditional_B_minus_A": boot_ci(ll["B"] - ll["A"], groups),
        "marginal_Bmarg_minus_A": boot_ci(ll["Bmarg"] - ll["A"], groups)}
    se = {k: (pred[f"hp_{k}"][win] - hp_lost[win]) ** 2 for k in ["A", "B", "Bmarg"]}
    report["hp_lost_mse_wins"] = {k: float(v.mean()) for k, v in se.items()}
    report["hp_lost_var_wins"] = float(hp_lost[win].var())
    report["hp_lost_mse_delta"] = {
        "conditional_B_minus_A": boot_ci(se["B"] - se["A"], groups[win]),
        "marginal_Bmarg_minus_A": boot_ci(se["Bmarg"] - se["A"], groups[win])}
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
