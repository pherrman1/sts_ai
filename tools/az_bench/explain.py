#!/usr/bin/env python3
"""Decision explainability, offline prototype (2026-11-21): what does AmberNet's policy prior at a card reward owe to
single cards / relics the player owns? No search, no simulator, CPU only: the script reads positions from a replay
window saved by selfplay.py (--replay-save, without --compact-samples), edits their tokens and runs the net.

Measure, for an offered card a and an owned item k (s = the position, s \\ k = the same position without k):

    delta_k(a) = log pi(a | s) - log pi(a | s \\ k)        (pi = softmax of the policy logits over the legal actions)

Token edits (AmberGameEncoder.cpp's layout; only out-of-combat positions):
  - remove a deck card: its CARD token goes, later deck cards' index (CARD 11) moves down by one, RUN 29 (deck size
    / 30) drops; a stack of merged copies (--merge-cards, CARD 41 = (copies - 1) / 10) loses one copy instead;
  - remove a relic: its RELIC token goes, later relics' order (RELIC 2) moves down, RUN 30 (relics / 20) drops;
  - add a deck card / relic: the inverse, with a token of that card / relic copied from another position of the
    window (never synthesised);
  - offer card a: an offered card's token is replaced by a reward token of a from another position, keeping its
    reward slots (CARD 11, 39, 40), so its action stays valid.
Only the item changes: what a relic already did to the state (max HP, gold) stays.

Modes:
  table  per sampled card reward: for each offered card the owned items with the largest |delta|.
  pairs  2x2 test of named pairs "OFFERED<KIND:OWNED": the offered card is put into real card rewards, the owned
         item added or not; control = the same with other owned cards (--controls). Reports the mean delta, the
         control's, their paired difference with a run-clustered bootstrap interval, and the specificity (delta of
         a minus the mean delta of the other offered cards).

usage: explain.py --ckpt CKPT --replay DIR --mode table|pairs [--pairs ...] [--controls ...] [--out FILE.json]
"""

import argparse
import json
import os
import re
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import amber_net  # noqa: E402

RUN, CARD, RELIC = 0, 4, 5
CHOOSE_CARD, SKIP = 12, 13
F_DECK, F_INDEX, F_UPG, F_COPIES, F_REWARD = 10, 11, 12, 41, 38
KEEP_REWARD = (11, 39, 40)


def enum_strings(header, name):
    text = open(os.path.join(ROOT, "include", "constants", header)).read()
    m = re.search(name + r"\s*\[\]\s*=?\s*\{(.*?)\};", text, re.S)
    return re.findall(r'"([^"]*)"', m.group(1))


def id_names():
    cards = enum_strings("Cards.h", "cardEnumStrings")
    relics = enum_strings("Relics.h", "relicEnumNames")
    relic_base = len(cards)   # kAmberRelicBase = 1 + ZAP - 1 + ... = CardId::ZAP + 1 - 1 + 1 (ZAP = len - 1)
    names = {i: c for i, c in enumerate(cards) if i}
    names.update({relic_base + i: "relic:" + r for i, r in enumerate(relics)})
    return names, {v: k for k, v in names.items()}


class Row:
    """One position: tokens (type, ids, f) and legal actions, as arrays the edits below copy."""

    def __init__(self, tt, ids, f, a_type, a_src, a_tgt, a_f):
        self.tt, self.ids, self.f = tt, ids, f
        self.a_type, self.a_src, self.a_tgt, self.a_f = a_type, a_src, a_tgt, a_f

    def copy(self):
        return Row(*(x.copy() for x in (self.tt, self.ids, self.f, self.a_type, self.a_src, self.a_tgt, self.a_f)))

    def deck(self):
        return np.flatnonzero((self.tt == CARD) & (self.f[:, F_DECK] == 1))

    def offered(self):
        return np.flatnonzero((self.tt == CARD) & (self.f[:, F_REWARD] == 1))

    def relics(self):
        return np.flatnonzero(self.tt == RELIC)

    def action_of(self, tok):
        hit = np.flatnonzero((self.a_type == CHOOSE_CARD) & (self.a_src == tok))
        return int(hit[0]) if len(hit) else -1

    def _drop(self, i):
        for a in (self.a_src, self.a_tgt):
            if (a == i).any():
                raise ValueError("an action names the removed token")
            a[a > i] -= 1
        self.tt, self.ids, self.f = (np.delete(x, i, 0) for x in (self.tt, self.ids, self.f))

    def _insert(self, i, tt, ids, f):
        for a in (self.a_src, self.a_tgt):
            a[a >= i] += 1
        self.tt = np.insert(self.tt, i, tt)
        self.ids = np.insert(self.ids, i, ids, 0)
        self.f = np.insert(self.f, i, f, 0)

    def _bump(self, slot, per, by):
        self.f[0, slot] = np.float16((round(float(self.f[0, slot]) * per) + by) / per)

    def remove_card(self, i):
        """One copy of deck card token i."""
        if round(float(self.f[i, F_COPIES]) * 10) > 0:
            self.f[i, F_COPIES] = np.float16((round(float(self.f[i, F_COPIES]) * 10) - 1) / 10)
        else:
            idx = round(float(self.f[i, F_INDEX]) * 10)
            for j in self.deck():
                k = round(float(self.f[j, F_INDEX]) * 10)
                if k > idx:
                    self.f[j, F_INDEX] = np.float16((k - 1) / 10)
            self._drop(i)
        self._bump(29, 30, -1)

    def remove_relic(self, i):
        order = round(float(self.f[i, 2]) * 20)
        for j in self.relics():
            k = round(float(self.f[j, 2]) * 20)
            if k > order:
                self.f[j, 2] = np.float16((k - 1) / 20)
        self._drop(i)
        self._bump(30, 20, -1)

    def add_card(self, ids, f):
        """A deck card from a template token (another position's deck token of that card, one copy)."""
        deck = self.deck()
        g = f.copy()
        g[F_INDEX] = g[F_COPIES] = 0
        for j in deck:
            h = self.f[j].copy()
            h[F_INDEX] = h[F_COPIES] = 0
            if (self.ids[j] == ids).all() and (h == g).all():   # merged stack: one more copy
                self.f[j, F_COPIES] = np.float16((round(float(self.f[j, F_COPIES]) * 10) + 1) / 10)
                self._bump(29, 30, 1)
                return
        n = round(float(self.f[0, 29]) * 30)
        g[F_INDEX] = np.float16(n / 10)
        cards = np.flatnonzero(self.tt == CARD)
        at = int(deck[-1]) + 1 if len(deck) else (int(cards[0]) if len(cards) else int(np.searchsorted(self.tt, CARD)))
        self._insert(at, CARD, ids, g)
        self._bump(29, 30, 1)

    def add_relic(self, ids, f):
        rel = self.relics()
        g = f.copy()
        g[2] = np.float16(len(rel) / 20)
        at = int(rel[-1]) + 1 if len(rel) else int(np.searchsorted(self.tt, RELIC))
        self._insert(at, RELIC, ids, g)
        self._bump(30, 20, 1)

    def offer(self, tok, ids, f):
        g = f.copy()
        for s in KEEP_REWARD:
            g[s] = self.f[tok, s]
        self.ids[tok], self.f[tok] = ids, g


def load_replay(path):
    """The saved window's samples as (rows, meta); run = index of the run a sample belongs to (samples arrive run by
    run; a new run starts where the floor falls)."""
    st = json.load(open(os.path.join(path, "state.json")))
    if st["layout"]["compact"]:
        raise SystemExit("explain.py reads windows saved without --compact-samples")
    ld = lambda k: np.load(os.path.join(path, k + ".npy"), mmap_mode="r")   # noqa: E731
    tt, ids, f = ld("tok_type"), ld("ids"), ld("f")
    a = {k: ld(k) for k in ("a_type", "a_src", "a_tgt", "a_f")}
    ts, nt, as_, na = ld("tok_start"), ld("ntok"), ld("act_start"), ld("nact")
    floor, combat = ld("meta.floor"), ld("meta.combat")
    cs, ct, ca = len(nt), len(tt), len(a["a_type"])
    rows, meta, run, last = [], [], -1, 10 ** 9
    for s in range(st["scalars"]["s_tail"], st["scalars"]["s_head"]):
        j = s % cs
        fl = int(floor[j])
        if fl < last:
            run += 1
        last = fl
        ti = (int(ts[j]) + np.arange(int(nt[j]))) % ct
        ai = (int(as_[j]) + np.arange(int(na[j]))) % ca
        rows.append(Row(np.asarray(tt[ti], np.int64), np.asarray(ids[ti], np.int64), np.asarray(f[ti], np.float16),
                        np.asarray(a["a_type"][ai], np.int64), np.asarray(a["a_src"][ai], np.int64),
                        np.asarray(a["a_tgt"][ai], np.int64), np.asarray(a["a_f"][ai], np.float16)))
        meta.append({"floor": fl, "combat": int(combat[j]), "run": run})
    return rows, meta


def load_net(ckpt):
    sd = torch.load(ckpt, map_location="cpu", weights_only=False)["net"]
    d = sd["type_emb.weight"].shape[1]
    layers = 1 + max(int(k.split(".")[2]) for k in sd if k.startswith("trunk.layers."))
    net = amber_net.AmberNet(d=d, layers=layers, hp_floors=sd["hp_floor.2.weight"].shape[0],
                             soft_policy=any(k.startswith("pol_soft.") for k in sd))
    net.load_state_dict(sd)
    net.sdpa = True
    return net.eval()


@torch.no_grad()
def evaluate(net, rows, batch=256):
    """Per row: log pi over its actions [A_r] and P(win)."""
    out = []
    for s in range(0, len(rows), batch):
        chunk = rows[s:s + batch]
        B, T, A = len(chunk), max(len(r.tt) for r in chunk), max(len(r.a_type) for r in chunk)
        b = {"tok_type": torch.zeros(B, T, dtype=torch.long), "ids": torch.zeros(B, T, 4, dtype=torch.long),
             "f": torch.zeros(B, T, 64), "mask": torch.zeros(B, T, dtype=torch.bool),
             "a_type": torch.zeros(B, A, dtype=torch.long), "a_src": torch.full((B, A), -1, dtype=torch.long),
             "a_tgt": torch.full((B, A), -1, dtype=torch.long), "a_f": torch.zeros(B, A, 8),
             "a_mask": torch.zeros(B, A, dtype=torch.bool)}
        for i, r in enumerate(chunk):
            n, m = len(r.tt), len(r.a_type)
            b["tok_type"][i, :n] = torch.from_numpy(r.tt)
            b["ids"][i, :n] = torch.from_numpy(r.ids)
            b["f"][i, :n] = torch.from_numpy(r.f.astype(np.float32))
            b["mask"][i, :n] = True
            b["a_type"][i, :m] = torch.from_numpy(r.a_type)
            b["a_src"][i, :m] = torch.from_numpy(r.a_src)
            b["a_tgt"][i, :m] = torch.from_numpy(r.a_tgt)
            b["a_f"][i, :m] = torch.from_numpy(r.a_f.astype(np.float32))
            b["a_mask"][i, :m] = True
        o = net(b)
        lp = torch.log_softmax(o[0].float(), -1).numpy()
        pw = torch.softmax(o[1].float(), -1)[:, 0].numpy()
        out += [(lp[i, :len(r.a_type)].copy(), float(pw[i])) for i, r in enumerate(chunk)]
    return out


def templates(rows, meta):
    """Tokens to copy: deck[(id, upgraded)] (a single-copy deck token), reward[(id, upgraded)], relic[id]."""
    deck, reward, relic = {}, {}, {}
    for r, m in zip(rows, meta):
        if m["combat"]:
            continue
        for i in r.deck():
            if r.f[i, F_COPIES] == 0 and not r.f[i, [32, 35, 36]].any():   # not bottled / selectable / picked
                deck.setdefault((int(r.ids[i, 0]), int(r.f[i, F_UPG])), (r.ids[i].copy(), r.f[i].copy()))
        for i in r.offered():
            reward.setdefault((int(r.ids[i, 0]), int(r.f[i, F_UPG])), (r.ids[i].copy(), r.f[i].copy()))
        for i in r.relics():
            relic.setdefault(int(r.ids[i, 0]), (r.ids[i].copy(), r.f[i].copy()))
    return deck, reward, relic


def card_rewards(rows, meta):
    return [i for i, (r, m) in enumerate(zip(rows, meta)) if not m["combat"] and len(r.offered())
            and all(r.action_of(t) >= 0 for t in r.offered())]


def boot_ci(x, run, rng, n=2000):
    """Mean and a 95 % interval from a bootstrap over runs (positions of one run are not independent)."""
    x, run = np.asarray(x, float), np.asarray(run)
    ids = np.unique(run)
    sums = np.array([x[run == i].sum() for i in ids])
    cnt = np.array([(run == i).sum() for i in ids])
    pick = rng.integers(0, len(ids), (n, len(ids)))
    m = sums[pick].sum(1) / cnt[pick].sum(1)
    return float(x.mean()), float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975))


def mode_table(net, rows, meta, names, args, rng):
    cr = card_rewards(rows, meta)
    pick = rng.choice(cr, min(args.states, len(cr)), replace=False)
    report = []
    for si in pick:
        r = rows[si]
        owned = [("card", i) for i in r.deck()] + [("relic", i) for i in r.relics()]
        variants = []
        for kind, i in owned:
            v = r.copy()
            (v.remove_card if kind == "card" else v.remove_relic)(int(i))
            variants.append(v)
        ev = evaluate(net, [r] + variants)
        base = ev[0][0]
        offers = []
        for t in r.offered():
            a = r.action_of(t)
            # the action list is unchanged by a removal (no action names a removed token), so index a stays valid
            d = [(float(base[a] - e[0][a]), names.get(int(r.ids[i, 0]), "?") + ("+" if kind == "card" and r.f[i, F_UPG] else ""))
                 for (kind, i), e in zip(owned, ev[1:])]
            d.sort()
            offers.append({"card": names.get(int(r.ids[t, 0]), "?") + ("+" if r.f[t, F_UPG] else ""),
                           "prior": float(np.exp(base[a])), "supports": d[::-1][:args.top], "opposes": d[:args.top]})
        report.append({"sample": int(si), "floor": meta[si]["floor"], "p_win": ev[0][1], "deck": len(r.deck()),
                       "offers": offers})
        print(f"\nfloor {meta[si]['floor']}  P(win) {ev[0][1]:.3f}  deck tokens {len(r.deck())}")
        for o in offers:
            print(f"  {o['card']:<22} prior {o['prior']:.3f}")
            print("     + " + ", ".join(f"{n} {d:+.2f}" for d, n in o["supports"]))
            print("     - " + ", ".join(f"{n} {d:+.2f}" for d, n in o["opposes"]))
    return report


def mode_pairs(net, rows, meta, names, ids_of, args, rng):
    deck_t, reward_t, relic_t = templates(rows, meta)
    cr = card_rewards(rows, meta)
    built = set()

    def owned_template(spec):
        if spec.startswith("relic:"):
            return ("relic", relic_t.get(ids_of[spec]))
        t = deck_t.get((ids_of[spec], 0))
        if t is None and (ids_of[spec], 0) in reward_t:
            # No position owns this card: its deck token is the id plus the floats every plain deck card of its
            # cost has (checked: one float pattern per cost among the window's plain deck tokens).
            cost = reward_t[(ids_of[spec], 0)][1][13]
            same = set()
            for (_, u), (_, f) in deck_t.items():
                if u == 0 and f[13] == cost and f[33] == 1:
                    g = f.copy()
                    g[F_INDEX] = 0
                    same.add(g.tobytes())
            if len(same) == 1:
                ids = np.zeros(4, np.int64)
                ids[0] = ids_of[spec]
                t = (ids, np.frombuffer(same.pop(), np.float16).copy())
                built.add(spec)
        return ("card", t)

    def add(row, kind, tpl):
        v = row.copy()
        (v.add_relic if kind == "relic" else v.add_card)(*tpl)
        return v

    controls = [(c, owned_template(c)) for c in args.controls.split(",") if c]
    controls = [(c, t) for c, t in controls if t[1] is not None]
    report = []
    for pair in args.pairs.split(","):
        a_name, k_name = pair.split("<")
        a_tpl = reward_t.get((ids_of[a_name], 0))
        k_kind, k_tpl = owned_template(k_name)
        if a_tpl is None or k_tpl is None:
            print(f"{pair}: no template in the window ({'offered' if a_tpl is None else 'owned'} side), skipped")
            report.append({"pair": pair, "skipped": True})
            continue
        a_id, k_id = ids_of[a_name], ids_of[k_name]
        ctl = [(c, t) for c, t in controls if c not in (a_name, k_name) and c not in args.partners.get(a_name, ())]
        batch, index = [], []
        for si in cr:
            r = rows[si]
            have = {int(x) for x in r.ids[np.concatenate([r.deck(), r.offered(), r.relics()]), 0]}
            if a_id in have or k_id in have or len(r.offered()) < 2 or len(r.offered()) > 4:
                continue
            s0 = r.copy()
            tok = int(rng.choice(s0.offered()))
            s0.offer(tok, *a_tpl)
            others = [s0.action_of(t) for t in s0.offered() if t != tok]
            cs = [add(s0, t[0], t[1]) for c, t in ctl
                  if ids_of[c] not in have]
            index.append((si, len(batch), s0.action_of(tok), others, len(cs)))
            batch += [s0, add(s0, k_kind, k_tpl)] + cs
        if not index:
            print(f"{pair}: no base position")
            continue
        ev = evaluate(net, batch)
        d_k, d_c, spec, p0, p1, runs = [], [], [], [], [], []
        for si, at, a, others, nc in index:
            l0, l1 = ev[at][0], ev[at + 1][0]
            d_k.append(l1[a] - l0[a])
            d_c.append(np.mean([ev[at + 2 + j][0][a] - l0[a] for j in range(nc)]) if nc else np.nan)
            spec.append((l1[a] - l0[a]) - np.mean([l1[o] - l0[o] for o in others]))
            p0.append(np.exp(l0[a]))
            p1.append(np.exp(l1[a]))
            runs.append(meta[si]["run"])
        d_k, d_c = np.array(d_k), np.array(d_c)
        ok = ~np.isnan(d_c)
        res = {"pair": pair, "n": len(d_k), "runs": len(set(runs)), "prior_without": float(np.mean(p0)),
               "prior_with": float(np.mean(p1)), "delta": boot_ci(d_k, runs, rng),
               "delta_control": boot_ci(d_c[ok], np.array(runs)[ok], rng),
               "delta_minus_control": boot_ci((d_k - d_c)[ok], np.array(runs)[ok], rng),
               "specificity": boot_ci(spec, runs, rng)}
        report.append(res)
        f3 = lambda t: f"{t[0]:+.3f} [{t[1]:+.3f}, {t[2]:+.3f}]"   # noqa: E731
        res["owned_token_built"] = k_name in built
        print(f"{pair:<34} n {res['n']:4d} runs {res['runs']:2d}  prior {res['prior_without']:.3f} -> "
              f"{res['prior_with']:.3f}  delta {f3(res['delta'])}  control {f3(res['delta_control'])}  "
              f"delta-control {f3(res['delta_minus_control'])}  specificity {f3(res['specificity'])}")
    return report


DEFAULT_PAIRS = ("CORRUPTION<DARK_EMBRACE,CORRUPTION<FEEL_NO_PAIN,CORRUPTION<relic:DEAD_BRANCH,"
                 "DARK_EMBRACE<CORRUPTION,FEEL_NO_PAIN<CORRUPTION,"
                 "BARRICADE<ENTRENCH,BARRICADE<BODY_SLAM,ENTRENCH<BARRICADE,BODY_SLAM<BARRICADE,"
                 "LIMIT_BREAK<INFLAME,LIMIT_BREAK<DEMON_FORM,LIMIT_BREAK<SPOT_WEAKNESS,HEAVY_BLADE<INFLAME,"
                 "RUPTURE<BLOODLETTING,RUPTURE<OFFERING")
DEFAULT_CONTROLS = ("SHRUG_IT_OFF,POMMEL_STRIKE,METALLICIZE,FLAME_BARRIER,SHOCKWAVE,UPPERCUT,DISARM,BATTLE_TRANCE,"
                    "CARNAGE,TWIN_STRIKE,ARMAMENTS,THUNDERCLAP")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--replay", required=True)
    ap.add_argument("--mode", choices=("table", "pairs"), required=True)
    ap.add_argument("--states", type=int, default=10, help="table: card rewards to show")
    ap.add_argument("--top", type=int, default=4)
    ap.add_argument("--pairs", default=DEFAULT_PAIRS, help="OFFERED<OWNED,... (OWNED may be relic:NAME)")
    ap.add_argument("--controls", default=DEFAULT_CONTROLS, help="owned control cards")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--out")
    args = ap.parse_args()
    args.partners = {}
    torch.set_num_threads(args.threads)
    rng = np.random.default_rng(args.seed)
    names, ids_of = id_names()
    net = load_net(args.ckpt)
    rows, meta = load_replay(args.replay)
    print(f"# {len(rows)} positions, {meta[-1]['run'] + 1} runs, {len(card_rewards(rows, meta))} card rewards")
    rep = (mode_table(net, rows, meta, names, args, rng) if args.mode == "table"
           else mode_pairs(net, rows, meta, names, ids_of, args, rng))
    if args.out:
        with open(args.out, "w") as fh:
            json.dump({"ckpt": args.ckpt, "replay": args.replay, "mode": args.mode, "seed": args.seed,
                       "report": rep}, fh, indent=1)


if __name__ == "__main__":
    main()
