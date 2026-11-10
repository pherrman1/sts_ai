#!/usr/bin/env python3
"""Fixed-size arrays from packed combat rows (combat plan stage 2, 2026-11-08).

usage: tensorize.py OUT_DIR PACKED.jsonl.gz [--every N] [--max-rows N]

Reads rows written by pack_states.py and writes one .npy per field into OUT_DIR (plus meta.json), so that training
reads memory-mapped arrays instead of JSON. Caps (rows above a cap are cut and counted in meta.json):

  cards     up to C_MAX rows x 9 ints [zone, pos, id, upgraded, cost, costForTurn, freeToPlayOnce, retain,
            specialData], ragged: cards.npy holds all rows, card_off.npy the start of each root's rows (n + 1)
  monsters  M_MAX x (4 ints [idx, id, last move, move before]) + M_MAX x M_NUM floats
  edges     up to E_MAX actions x A_LEN ints (see action_row), ragged like cards (actions.npy, act_off.npy, and
            policy.npy aligned with actions.npy); a root with more edges keeps the E_MAX most visited and
            renormalizes the policy over them (counted as cut.edges)
  pstatus   status bits as a 128-multi-hot, statusMap pairs as S_MAX x 2 ints
  queues    Q_MAX x Q_LEN ints

Floats (global, player, monster numbers) go through sign(v) * log1p(|v|). Targets: policy (visit shares over the kept
edges), chosen (index into the kept edges, -1 if cut or unknown), won, endHp / preMaxHp, preMaxHp, hpLoss1,
hpLoss2 (in HP), the row's seed (for the run-level holdout split), the root's HP and max HP, the encounter, and for
Gumbel-root rows the root prior per kept edge (prior.npy, aligned with actions.npy) and gumbelChoice. Rows with one edge are kept (value targets);
their policy is empty and `multi` is 0. Also aligned with actions.npy: each kept edge's visit count (visits.npy) and
the search's Q (q.npy, NaN for an unvisited edge), and per row the fight's Silver score (score.npy, NaN if the row has
none), so train.py can form a completed-Q policy target and t0_value_check.py can compare root Q with the outcome (fight.npy: the fight's index in its run).
"""

import argparse
import gzip
import json
import os
import sys

import numpy as np

C_MAX, M_MAX, M_NUM, E_MAX, S_MAX, Q_MAX, Q_LEN, SEL_MAX = 128, 5, 128, 96, 32, 8, 24, 10
G_LEN = 59 + 38   # wire_encoder global + player lengths; a different length fails loudly at assignment
CARD_LEN = 8   # the semantic `c` field
SEL_LEN = 3   # a selected card: id, specialData, upgraded (cardFingerprint order: id, uniqueId, specialData,
#               cost, costForTurn, upgraded, freeToPlayOnce, retain)
A_LEN = 1 + 1 + CARD_LEN + 1 + 2 + 1 + 1 + 1 + 1 + SEL_MAX * SEL_LEN


def slog(v):
    v = np.asarray(v, dtype=np.float32)
    return np.sign(v) * np.log1p(np.abs(v))


def action_row(a):
    """t, s, c[8], o, p[2], x, d, k, task, sel[SEL_MAX][id, specialData, upgraded] (zeros past the end)."""
    row = [a["t"][0] if a["t"] else 0, a["s"][0] if a["s"] else 0]
    c = list(a["c"])[:CARD_LEN]
    if len(c) > 1:
        c[1] = 0   # the card's unique id: identity only (the encoder ignores it in the state too)
    row += c + [0] * (CARD_LEN - len(c))
    row += [a["o"][0] if a["o"] else 0]
    p = list(a["p"])[:2]
    row += p + [0] * (2 - len(p))
    for k in ("x", "d", "k", "task"):
        row += [a[k][0] if a[k] else 0]
    sel = []
    for card in a["sel"][:SEL_MAX]:
        card = list(card) + [0] * (6 - len(card))
        sel += [card[0], card[2], card[5]]
    sel += [0] * (SEL_MAX * SEL_LEN - len(sel))
    return row + sel


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("packed")
    ap.add_argument("--every", type=int, default=1, help="keep every N-th row (smokes)")
    ap.add_argument("--max-rows", type=int, default=0)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)

    n = 0
    with gzip.open(args.packed, "rt") as f:
        for i, _ in enumerate(f):
            if i % args.every == 0:
                n += 1
                if args.max_rows and n >= args.max_rows:
                    break
    arr = {
        "glob": np.zeros((n, G_LEN), np.float16),
        "relics": np.zeros((n, 128), np.uint8),
        "sbits": np.zeros((n, 128), np.uint8),
        "smap": np.zeros((n, S_MAX, 2), np.int16),
        "mcat": np.zeros((n, M_MAX, 4), np.int16),
        "mnum": np.zeros((n, M_MAX, M_NUM), np.float16),
        "nmon": np.zeros(n, np.int8),
        "potions": np.zeros((n, 5), np.int16),
        "queues": np.zeros((n, Q_MAX, Q_LEN), np.int16),
        "nqueue": np.zeros(n, np.int8),
        "chosen": np.full(n, -1, np.int16),
        "multi": np.zeros(n, np.uint8),
        "won": np.zeros(n, np.uint8),
        "endFrac": np.zeros(n, np.float32),
        "preMaxHp": np.zeros(n, np.int16),
        "hpLoss1": np.zeros(n, np.float32),
        "hpLoss2": np.zeros(n, np.float32),
        "seed": np.zeros(n, np.int64),
        "hp": np.zeros(n, np.int16),
        "maxHp": np.zeros(n, np.int16),
        "encounter": np.zeros(n, np.int16),   # index into meta.json "encounters"
        "gumbelChoice": np.full(n, -1, np.int16),   # index into the kept edges; -1 = none or cut
        "score": np.full(n, np.nan, np.float32),    # the fight's Silver score (same units as the edges' q)
        "fight": np.full(n, -1, np.int16),          # the fight's index within its run (with seed: the fight id)
        "act": np.zeros(n, np.int8),
        "elite_boss": np.zeros(n, np.int8),   # 0 monster, 1 elite, 2 boss, 3 other
    }
    cut = {"cards": 0, "monsters": 0, "mnum": 0, "edges": 0, "smap": 0, "queues": 0, "qlen": 0, "sel": 0}
    room = {"MONSTER": 0, "MONSTER_ELITE": 1, "ELITE": 1, "BOSS": 2}
    # Chunked: each list holds numpy blocks of up to CHUNK roots, so RAM stays near the final array size.
    CHUNK = 20000
    cards_l, actions_l, policy_l, prior_l, visits_l, q_l = [], [], [], [], [], []
    cards_c, actions_c, policy_c, prior_c, visits_c, q_c = [], [], [], [], [], []

    def flush():
        if cards_c:
            cards_l.append(np.clip(np.asarray(cards_c, np.int64).reshape(-1, 9), -32768, 32767).astype(np.int16))
        if actions_c:
            actions_l.append(np.clip(np.asarray(actions_c, np.int64).reshape(-1, A_LEN), -32768, 32767)
                             .astype(np.int16))
        policy_l.append(np.asarray(policy_c, np.float32))
        prior_l.append(np.asarray(prior_c, np.float32))
        visits_l.append(np.asarray(visits_c, np.int32))
        q_l.append(np.asarray(q_c, np.float32))
        cards_c.clear(); actions_c.clear(); policy_c.clear(); prior_c.clear(); visits_c.clear(); q_c.clear()
    encounters = {}
    card_off, act_off = [0], [0]
    j = 0
    with gzip.open(args.packed, "rt") as f:
        for i, line in enumerate(f):
            if i % args.every:
                continue
            if j >= n:
                break
            r = json.loads(line)
            x = r["x"]
            arr["glob"][j] = slog(x["global"] + x["player"])
            for b in x["relics"]:
                arr["relics"][j, b] = 1
            pairs = []
            for s in x["pstatus"]:
                if isinstance(s, list):
                    pairs.append(s)
                else:
                    arr["sbits"][j, s] = 1
            if len(pairs) > S_MAX:
                cut["smap"] += 1
            for k, (a, b) in enumerate(pairs[:S_MAX]):
                arr["smap"][j, k] = (a, min(b, 32767))
            cards = x["cards"]
            if len(cards) > C_MAX:
                cut["cards"] += 1
            cards = cards[:C_MAX]
            cards_c.extend(cards)
            card_off.append(card_off[-1] + len(cards))
            mons = x["monsters"]
            if len(mons) > M_MAX:
                cut["monsters"] += 1
            for k, (cat, num) in enumerate(mons[:M_MAX]):
                arr["mcat"][j, k] = cat
                if len(num) > M_NUM:
                    cut["mnum"] += 1
                num = num[:M_NUM]
                arr["mnum"][j, k, :len(num)] = slog(num)
            arr["nmon"][j] = min(len(mons), M_MAX)
            arr["potions"][j, :len(x["potions"][:5])] = x["potions"][:5]
            qs = x["queues"]
            if len(qs) > Q_MAX:
                cut["queues"] += 1
            for k, q in enumerate(qs[:Q_MAX]):
                if len(q) > Q_LEN:
                    cut["qlen"] += 1
                q = q[:Q_LEN]
                arr["queues"][j, k, :len(q)] = np.clip(q, -32768, 32767)
            arr["nqueue"][j] = min(len(qs), Q_MAX)

            edges = r["edges"]
            order = list(range(len(edges)))
            if len(edges) > E_MAX:
                cut["edges"] += 1
                order = sorted(order, key=lambda e: -edges[e]["visits"])[:E_MAX]
            for e in order:
                a = edges[e]["a"]
                if len(a["sel"]) > SEL_MAX:
                    cut["sel"] += 1
                actions_c.append(action_row(a))
            act_off.append(act_off[-1] + len(order))
            vis = np.array([edges[e]["visits"] for e in order], np.float64)
            if len(edges) > 1 and vis.sum() > 0:
                policy_c.extend(vis / vis.sum())
                arr["multi"][j] = 1
            else:
                policy_c.extend([0.0] * len(order))
            prior_c += [edges[e].get("prior") if edges[e].get("prior") is not None else np.nan for e in order]
            visits_c += [edges[e]["visits"] for e in order]
            q_c += [edges[e].get("q") if edges[e].get("q") is not None and edges[e]["visits"] > 0 else np.nan
                    for e in order]
            if r.get("gumbelChoice", -1) in order:
                arr["gumbelChoice"][j] = order.index(r["gumbelChoice"])
            if r["chosen"] in order:
                arr["chosen"][j] = order.index(r["chosen"])
            v = r["value"]
            mx = max(1, v["preMaxHp"])
            arr["won"][j] = 1 if v["won"] else 0
            arr["endFrac"][j] = v["endHp"] / mx
            arr["fight"][j] = r.get("fight", -1)
            if v.get("score") is not None:
                arr["score"][j] = v["score"]
            arr["preMaxHp"][j] = v["preMaxHp"]
            arr["hpLoss1"][j] = r["aux"]["hpLoss1"]
            arr["hpLoss2"][j] = r["aux"]["hpLoss2"]
            arr["seed"][j] = r["seed"]
            arr["hp"][j] = int(x["player"][8])      # PLAYER_SCALARS: curHp
            arr["maxHp"][j] = int(x["player"][20])  # PLAYER_SCALARS: maxHp
            arr["encounter"][j] = encounters.setdefault(r["encounter"], len(encounters))
            arr["act"][j] = r["act"]
            arr["elite_boss"][j] = room.get(r["room"], 3)
            j += 1
            if j % CHUNK == 0:
                flush()
    for k, a in arr.items():
        np.save(os.path.join(args.out, k + ".npy"), a[:j])
    flush()
    np.save(os.path.join(args.out, "cards.npy"), np.concatenate(cards_l) if cards_l else np.zeros((0, 9), np.int16))
    np.save(os.path.join(args.out, "card_off.npy"), np.asarray(card_off, np.int64))
    np.save(os.path.join(args.out, "actions.npy"),
            np.concatenate(actions_l) if actions_l else np.zeros((0, A_LEN), np.int16))
    np.save(os.path.join(args.out, "act_off.npy"), np.asarray(act_off, np.int64))
    np.save(os.path.join(args.out, "policy.npy"), np.concatenate(policy_l))
    np.save(os.path.join(args.out, "prior.npy"), np.concatenate(prior_l))   # NaN = no root prior
    np.save(os.path.join(args.out, "visits.npy"), np.concatenate(visits_l))
    np.save(os.path.join(args.out, "q.npy"), np.concatenate(q_l))   # NaN = unvisited edge
    meta = {"rows": j, "encounters": sorted(encounters, key=encounters.get), "source": os.path.abspath(args.packed), "every": args.every, "cut": cut,
            "caps": {"C_MAX": C_MAX, "M_MAX": M_MAX, "M_NUM": M_NUM, "E_MAX": E_MAX, "S_MAX": S_MAX,
                     "Q_MAX": Q_MAX, "Q_LEN": Q_LEN, "SEL_MAX": SEL_MAX, "SEL_LEN": SEL_LEN, "A_LEN": A_LEN, "G_LEN": G_LEN}}
    with open(os.path.join(args.out, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print(json.dumps(meta))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
