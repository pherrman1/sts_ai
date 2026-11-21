#!/usr/bin/env python3
"""Explanation of one out-of-combat decision for the live advisor (2026-11-21; no language model, CPU only).

Built on explain.py's token edits (leave-one-out over the owned cards / relics / potions) and explain_lab.py's
coalition game, for one position (a probe search's root, amber_probe.py) and the search's decision:

  options    per action a, the items whose removal lowers the net's contrast C(a, ref) = z_a - z_ref most
             (ref = Skip where it exists, else the best other action): what the net's prior thinks a synergises
             with, with a placebo z among all owned items (median / MAD; |z| >= 3 = stands out)
  pair       the search pick against the runner-up (by the search's root score): leave-one-out effects on
             C(pick, runner-up), exact Shapley values over the strongest items (the others always present), the
             smallest set of items whose removal reverses the net's preference between the two (greedy + pruning,
             PRINCE-style), the nearest current HP at which it reverses (HP scan)
  value      items whose removal changes the net's P(win) of the position most (what the value head thinks
             carries the run)

Every number is the net's own output on edited inputs; nothing is narrated. The ablation leaves states the net
never saw (a deck without its Strikes is out of distribution); the placebo z puts each effect against all items.
"""

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import explain as ex  # noqa: E402
import explain_lab as lab  # noqa: E402


def _item(x):
    return {"item": x[0], "kind": x[1], "effect": round(float(x[2]), 3),
            "z": None if not np.isfinite(x[3]) else round(float(x[3]), 1)}


def option_effects(base, items, evs, keeps, r, vocab, top=3):
    """Per action: the items supporting / opposing it against its reference action."""
    out = []
    for a in range(len(r.a_type)):
        ref = ex.reference(r, base, a)
        dc = ex.contrast_effects(base, evs, keeps, a, ref)
        ok = ~np.isnan(dc)
        z = np.full(len(dc), np.nan)
        if ok.sum() >= 3:
            z[ok] = ex.robust_z(dc[ok])
        rows = [(items[k][2], items[k][0], dc[k], z[k]) for k in range(len(items)) if ok[k]]
        rows.sort(key=lambda x: -x[2])
        out.append({"action": a, "ref": ex.action_label(r, ref, vocab), "contrast": round(float(base.z[a] - base.z[ref]), 3),
                    "for": [_item(x) for x in rows[:top] if x[2] > 0],
                    "against": [_item(x) for x in rows[::-1][:top] if x[2] < 0]})
    return out


def minimal_flip(net, r, a, b, items, dc, max_set=5):
    """Smallest set of items whose removal reverses the sign of C(a, b) (greedy on dC, then pruned); None if no
    set of up to max_set items does."""
    c0 = None
    toks = [(k, i) for k, i, _, _ in items]
    sign = 1.0
    ev0 = ex.evaluate(net, [r])[0]
    c0 = float(ev0.z[a] - ev0.z[b])
    sign = 1.0 if c0 > 0 else -1.0
    order = [j for j in np.argsort(-sign * np.nan_to_num(dc, nan=-sign * 1e9))
             if np.isfinite(dc[j]) and sign * dc[j] > 0][:max_set]

    def reversed_without(sel):
        v, kp = lab.without_tokens(r, [toks[j] for j in sel])
        pos = {int(o): n for n, o in enumerate(kp)}
        if a not in pos or b not in pos:
            return False, None
        e = ex.evaluate(net, [v])[0]
        return sign * float(e.z[pos[a]] - e.z[pos[b]]) < 0, e

    found = None
    for n in range(1, len(order) + 1):
        if reversed_without(order[:n])[0]:
            found = list(order[:n])
            break
    if found:
        for j in list(found):
            trial = [x for x in found if x != j]
            if trial and reversed_without(trial)[0]:
                found = trial
    return {"contrast": round(c0, 3), "set": [items[j][2] for j in found] if found else None}


def hp_reversal(net, r, a, b):
    """The current HP nearest to the real one at which the net's C(a, b) changes sign (None: no HP does)."""
    pt = int(np.flatnonzero(r.tt == ex.PLAYER)[0])
    hp0 = round(float(r.f[pt, 0]) * 100)
    mx = round(float(r.f[pt, 1]) * 100)
    ev0 = ex.evaluate(net, [r])[0]
    s0 = np.sign(ev0.z[a] - ev0.z[b])
    grid = [h for h in range(1, mx + 1) if h != hp0]
    vs = []
    for h in grid:
        v = r.copy()
        v.f[pt, 0] = np.float16(h / 100)
        v.f[pt, 2] = np.float16(h / max(mx, 1))
        vs.append(v)
    flips = [h for h, e in zip(grid, ex.evaluate(net, vs) if vs else []) if np.sign(e.z[a] - e.z[b]) != s0]
    if not flips:
        return {"hp": hp0, "reverses_at": None}
    return {"hp": hp0, "reverses_at": int(min(flips, key=lambda h: abs(h - hp0)))}


def pair_shapley(net, r, a, b, items, dc, players=6):
    """Exact Shapley values of the `players` items with the largest |dC(a, b)| (one player per copy); the other
    items stay present. Sum = C(all) - C(without those items)."""
    cand = [j for j in np.argsort(-np.abs(np.nan_to_num(dc, nan=0.0))) if np.isfinite(dc[j]) and dc[j] != 0][:players]
    if not cand:
        return []
    pl = []
    for j in cand:
        kind, i, _, c = items[j]
        pl += [(kind, i)] * c
    game = lab.Game(net, r, pl, a, b)
    phi = lab.shapley_multiset(game, pl)
    per = lab.per_item(pl, phi)
    out = [{"item": items[j][2], "shapley": round(float(per[(items[j][0], items[j][1])]), 3)} for j in cand]
    out.sort(key=lambda x: -abs(x["shapley"]))
    return out


def explain_decision(net, r, vocab, pick, runner_up=None, top=3, players=6, max_set=5):
    """The explanation of position r's decision: per option, the pick against the runner-up, value items."""
    base, items, evs, keeps = ex.explain_position(net, r, vocab)
    rep = {"net_pwin": round(float(base.pwin), 4), "net_ehp": round(float(base.hp), 1),
           "items": len(items), "options": option_effects(base, items, evs, keeps, r, vocab, top)}
    vals = sorted(((items[k][2], base.pwin - e.pwin) for k, e in enumerate(evs)), key=lambda x: -abs(x[1]))
    rep["value"] = [{"item": n, "dpwin": round(float(d), 4)} for n, d in vals[:top]]
    if runner_up is None or runner_up == pick or not items:
        return rep
    dc = ex.contrast_effects(base, evs, keeps, pick, runner_up)
    ok = ~np.isnan(dc)
    z = np.full(len(dc), np.nan)
    if ok.sum() >= 3:
        z[ok] = ex.robust_z(dc[ok])
    rows = sorted(((items[k][2], items[k][0], dc[k], z[k]) for k in range(len(items)) if ok[k]), key=lambda x: -x[2])
    rep["pair"] = {"pick": ex.action_label(r, pick, vocab), "runner_up": ex.action_label(r, runner_up, vocab),
                   "for": [_item(x) for x in rows[:top] if x[2] > 0],
                   "against": [_item(x) for x in rows[::-1][:top] if x[2] < 0],
                   "shapley": pair_shapley(net, r, pick, runner_up, items, dc, players),
                   "minimal_flip": minimal_flip(net, r, pick, runner_up, items, dc, max_set),
                   "hp": hp_reversal(net, r, pick, runner_up)}
    return rep
