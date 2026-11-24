#!/usr/bin/env python3
"""Explainability analyses on top of explain.py (2026-11-21, the P0-P2 list of the literature review
/mnt/project-files/explainability/): checks of the explanations themselves and of what the net represents. CPU only,
token edits on replay positions (explain.py's layout and limits), no simulator.

Modes (each prints a summary and writes --out JSON):
  coverage     how often the named cards were offered, picked and owned in the window (per run)
  design       constructed contexts, a 2 x 2 x 2 design per real card reward: offered card a, owned factors f1 and
               f2 (with / without), and a density factor (3 cards of one list or of another, same deck size); main
               effects and interactions on C(a, Skip) with run-clustered intervals
  lens         logit lens: the pair effects D2 of explain.py --mode pairs read from the residual stream after each
               trunk layer (out_norm + the same heads), i.e. at which depth an interaction appears
  patch        activation patching for a pair "a<k": the state s without k and s + k; the residual of a token
               group (the offered card, the run token, all other tokens) at layer l is copied from s + k into s;
               share of the effect C(s + k) - C(s) that the patch recovers, per layer and group
  calibration  reliability of the outcome head (P(win)), E[final floor] and the HP head (E[HP at the end of the
               floor]) against the window's labels, per act: Brier, ECE (10 bins), bootstrap over runs
  shapley      per decision: Shapley values of the owned items (one player per card copy / relic / potion) for the
               contrast C(best, runner-up); exact over the multiset of item types when the coalition count is small,
               else antithetic permutation sampling; efficiency check (sum = C(full) - C(nothing))
  faithful     sanity and faithfulness suite: deletion curves / AOPC of LOO, Shapley and gate-IG orderings against
               random orders, method agreement (Spearman LOO / Shapley / gate-IG / attention rollout), cascading
               weight randomization (Adebayo et al.), checkpoint stability (--ckpt2)
  counterfactual  minimal sets of owned items whose removal changes the net's choice (greedy + pruning, PRINCE-
               style), SARFA saliency (specificity x relevance), HP and gold scans (the smallest HP / gold change
               that flips the choice)
  probe        linear probes per layer on the run summary for state concepts, with input-embedding and
               random-init baselines and a control task (selectivity), across checkpoints (--ckpt2); TCAV for a
               concept and an action logit; a value GLM (the value head's logit regressed on readable features)
  interact     pairwise Shapley interactions (k-SII, Faithful-SII) between the top owned items of a decision via
               shapiq (exact over the top --players items, the rest always present)

usage: explain_lab.py --ckpt CKPT --replay DIR --mode MODE [...] [--out FILE.json]
"""

import argparse
import itertools
import json
import math
import os
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import explain as ex  # noqa: E402

F = torch.nn.functional


# ---------------------------------------------------------------------------------------------------- the trunk

def embed(net, b):
    tt = b["tok_type"]
    d = net.type_emb.weight.shape[1]
    W = torch.stack([net.proj[t].weight for t in ex.amber_net.TOKEN_TYPES])
    bias = torch.stack([net.proj[t].bias for t in ex.amber_net.TOKEN_TYPES])
    K = W.shape[0]
    P = F.linear(ex.amber_net.log_run_slots(tt, b["f"], net.run_log_slots), W.reshape(K * d, -1),
                 bias.reshape(-1)).view(*tt.shape, K, d)
    proj = torch.gather(P, 2, tt[..., None, None].expand(-1, -1, 1, d)).squeeze(2)
    return net.in_norm(net.type_emb(tt) + net._id_emb(tt, b["ids"], 2) + proj)


def trunk(net, b, patch=None, gate=None, attn=False):
    """The residual stream after the embedding and after each layer: xs [L + 1] of [B, T, d] (sdpa_trunk's math).

    patch: {layer: [(row, tok, vector)]} sets x[row, tok] after that layer (0 = the embedding).
    gate:  [B, T] presence in (0, 1]: log(gate) is added to the attention logits of every query towards that key,
           and the summary mean weights tokens by it (gate -> 0 behaves as the token's absence; gate-IG).
    attn:  also return the attention matrices per layer [B, H, T, T] (head-averaged later)."""
    x = embed(net, b)
    mask = b["mask"]
    B, T, d = x.shape
    bias = torch.zeros(B, 1, 1, T, dtype=x.dtype).masked_fill(~mask[:, None, None, :], float("-inf"))
    if gate is not None:
        bias = bias + torch.log(gate.clamp(min=1e-12))[:, None, None, :]
    xs, atts = [x], []

    def apply(l, x):
        if patch and l in patch:
            x = x.clone()
            for r, t, v in patch[l]:
                x[r, t] = v
        return x

    x = apply(0, x)
    xs[0] = x
    for li, layer in enumerate(net.trunk.layers):
        a = layer.self_attn
        H = a.num_heads
        y = layer.norm1(x)
        qkv = F.linear(y, a.in_proj_weight, a.in_proj_bias).view(B, T, 3, H, d // H).permute(2, 0, 3, 1, 4)
        s = (qkv[0] @ qkv[1].transpose(-1, -2)) * (d // H) ** -0.5 + bias
        p = torch.softmax(s, -1)
        if attn:
            atts.append(p.detach())
        o = p @ qkv[2]
        x = x + a.out_proj(o.transpose(1, 2).reshape(B, T, d))
        x = x + layer.linear2(F.gelu(layer.linear1(layer.norm2(x))))
        x = apply(li + 1, x)
        xs.append(x)
    return (xs, atts) if attn else xs


def heads(net, x, b, gate=None):
    """The net's outputs (logits, outcome, hp, hp_floor) from a residual stream x [B, T, d]."""
    h = net.out_norm(x)
    if gate is None:
        return net._heads(h, b["mask"], b)
    live = (b["mask"][:, 1:].to(h.dtype) * gate[:, 1:])[..., None]
    rest = (h[:, 1:] * live).sum(1) / live.sum(1).clamp(min=1e-6)
    c = h[:, 0] + net.summary_mlp(rest)
    d = h.shape[-1]

    def pick(idx, none):
        g = torch.gather(h, 1, idx.clamp(min=0)[..., None].expand(-1, -1, d))
        return torch.where((idx >= 0)[..., None], g, none.to(g.dtype))

    e = (net.a_type(b["a_type"]) + net.w_s(pick(b["a_src"], net.a_none[0])) + net.w_t(pick(b["a_tgt"], net.a_none[1]))
         + net._act_feat(b["a_type"], b["a_f"]) + net.w_c(c)[:, None])
    return (net.pol(e).squeeze(-1).masked_fill(~b["a_mask"], -1e4), net.outcome(c), net.hp(c))


def summary(net, x, b):
    """The run summary c (the heads' input) from a residual stream."""
    h = net.out_norm(x)
    live = b["mask"][:, 1:, None].to(h.dtype)
    return h[:, 0] + net.summary_mlp((h[:, 1:] * live).sum(1) / live.sum(1).clamp(min=1))


@torch.no_grad()
def lens_logits(net, rows, batch=128):
    """Per row: policy logits [L + 1][A] read after the embedding and after each layer."""
    out = []
    for s in range(0, len(rows), batch):
        chunk = rows[s:s + batch]
        b = ex.batch_of(chunk)
        xs = trunk(net, b)
        z = [heads(net, x, b)[0].numpy().astype(np.float64) for x in xs]
        out += [[zl[i, :len(r.a_type)] for zl in z] for i, r in enumerate(chunk)]
    return out


# ---------------------------------------------------------------------------------------------------- subsets

def players_of(r, copies=True, keep_actions=()):
    """Players of a coalition game on position r: (kind, token) per card copy (copies=True) or per token. Tokens
    that the actions in keep_actions name (a card-select choice's card) are no players: they always stay."""
    named = {int(x) for a in keep_actions for x in (r.a_src[a], r.a_tgt[a]) if x >= 0}
    out = []
    for kind, i, c in ex.owned_items(r):
        if i not in named:
            out += [(kind, i)] * (c if copies else 1)
    return out


def without(r, players, absent):
    """Position r without the listed players (indices into players); returns (row, kept action indices)."""
    cnt = {}
    for j in absent:
        kind, i = players[j]
        cnt[(kind, i)] = cnt.get((kind, i), 0) + 1
    v = r.copy()
    keep = np.arange(len(r.a_type))
    for (kind, i), n in sorted(cnt.items(), key=lambda kv: -kv[0][1]):   # highest token first: lower ones stay put
        for _ in range(n):
            k = v.remove(kind, i)
            keep = keep[k]
    return v, keep


def contrast_of(ev, keep, a, b):
    pos = {int(o): n for n, o in enumerate(keep)}
    if a not in pos or b not in pos:
        return float("nan")
    return float(ev.z[pos[a]] - ev.z[pos[b]])


class Game:
    """v(S) = C(a, b) at position r with only the players in S present (memoised, batched)."""

    def __init__(self, net, r, players, a, b):
        self.net, self.r, self.players, self.a, self.b = net, r, players, a, b
        self.cache = {}
        self.evals = 0

    def values(self, coalitions):
        """coalitions: iterable of frozensets of present players."""
        need = [c for c in set(coalitions) if c not in self.cache]
        n = len(self.players)
        rows, keeps = [], []
        for c in need:
            v, k = without(self.r, self.players, [j for j in range(n) if j not in c])
            rows.append(v)
            keeps.append(k)
        if rows:
            evs = ex.evaluate(self.net, rows)
            self.evals += len(rows)
            for c, e, k in zip(need, evs, keeps):
                self.cache[c] = contrast_of(e, k, self.a, self.b)
        return [self.cache[c] for c in coalitions]


def shapley_permutation(game, n, perms, rng):
    """Antithetic permutation sampling: each sampled order and its reverse."""
    phi = np.zeros(n)
    cnt = 0
    for _ in range(perms // 2):
        p = list(rng.permutation(n))
        for order in (p, p[::-1]):
            chain = [frozenset(order[:k]) for k in range(n + 1)]
            v = game.values(chain)
            for k, j in enumerate(order):
                phi[j] += v[k + 1] - v[k]
            cnt += 1
    return phi / max(cnt, 1)


def shapley_multiset(game, players):
    """Exact Shapley values when players come in identical copies: coalitions as counts per type."""
    types = sorted(set(players))
    m = [players.count(t) for t in types]
    n = len(players)
    idx = {t: [j for j, p in enumerate(players) if p == t] for t in types}

    def coal(counts):
        return frozenset(j for t, c in zip(types, counts) for j in idx[t][:c])

    grid = list(itertools.product(*[range(x + 1) for x in m]))
    vals = dict(zip(grid, game.values([coal(c) for c in grid])))
    fact = [math.factorial(k) for k in range(n + 1)]
    phi_t = []
    for ti in range(len(types)):
        tot = 0.0
        for c in grid:
            if c[ti] >= m[ti]:
                continue
            s = sum(c)
            ways = 1
            for tj, (cj, mj) in enumerate(zip(c, m)):
                ways *= math.comb(mj - (1 if tj == ti else 0), cj)
            up = list(c)
            up[ti] += 1
            tot += ways * fact[s] * fact[n - s - 1] / fact[n] * (vals[tuple(up)] - vals[c])
        phi_t.append(tot)
    phi = np.zeros(n)
    for t, v in zip(types, phi_t):
        phi[idx[t]] = v
    return phi


def shapley(net, r, a, b, rng, perms=64, exact_limit=4096):
    players = players_of(r, keep_actions=(a, b))
    n = len(players)
    game = Game(net, r, players, a, b)
    types = set(players)
    grid = int(np.prod([players.count(t) + 1 for t in types]))
    phi = shapley_multiset(game, players) if grid <= exact_limit else shapley_permutation(game, n, perms, rng)
    full, empty = game.values([frozenset(range(n)), frozenset()])
    return players, phi, {"exact": grid <= exact_limit, "coalitions": grid, "evals": game.evals,
                          "efficiency_gap": float(full - empty - phi.sum())}


def per_item(players, phi):
    """Sum of player values per (kind, token)."""
    out = {}
    for p, v in zip(players, phi):
        out[p] = out.get(p, 0.0) + float(v)
    return out


# ---------------------------------------------------------------------------------------------------- gate-IG, rollout

def gate_ig(net, r, a, b, steps=24):
    """Integrated gradients of C(a, b) over the presence gates of the owned item tokens (all others stay at 1),
    from absent (0) to present (1); returns {(kind, tok): attribution}. Derived counts (deck size) do not move."""
    items = ex.owned_items(r)
    bt = ex.batch_of([r] * steps)
    T = bt["tok_type"].shape[1]
    alphas = (torch.arange(steps, dtype=torch.float32) + 0.5) / steps
    sel = torch.zeros(T)
    for _, i, _ in items:
        sel[i] = 1
    g = torch.ones(steps, T) - sel[None] + alphas[:, None] * sel[None]
    g.requires_grad_(True)
    xs = trunk(net, bt, gate=g)
    z = heads(net, xs[-1], bt, gate=g)[0]
    (z[:, a] - z[:, b]).sum().backward()
    grad = g.grad.mean(0)
    return {(k, i): float(grad[i]) for k, i, _ in items}


@torch.no_grad()
def rollout(net, r, a):
    """Attention rollout (Abnar and Zuidema 2020) from the action's source token (the run token if none) and from
    the run token (the summary), averaged; returns {(kind, tok): relevance}."""
    bt = ex.batch_of([r])
    _, atts = trunk(net, bt, attn=True)
    T = bt["tok_type"].shape[1]
    R = torch.eye(T)
    for p in atts:
        A = p[0].mean(0)
        A = 0.5 * A + 0.5 * torch.eye(T)
        R = A @ R
    src = int(r.a_src[a]) if r.a_src[a] >= 0 else 0
    rel = 0.5 * (R[src] + R[0])
    return {(k, i): float(rel[i]) for k, i, _ in ex.owned_items(r)}


def spearman(x, y):
    from scipy.stats import spearmanr
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = ~(np.isnan(x) | np.isnan(y))
    if ok.sum() < 4 or np.std(x[ok]) == 0 or np.std(y[ok]) == 0:
        return float("nan")
    return float(spearmanr(x[ok], y[ok])[0])


# ---------------------------------------------------------------------------------------------------- helpers

def best_two(ev):
    o = np.argsort(-ev.z)
    return int(o[0]), int(o[1])


def loo_effects(net, r, a, b):
    base, items, evs, keeps = ex.explain_position(net, r, VOCAB)
    return {(k, i): v for (k, i, _, _), v in zip(items, ex.contrast_effects(base, evs, keeps, a, b))}


def sample_decisions(rows, meta, n, rng, kinds=None, min_items=3):
    pool = [i for i in ex.decisions(rows, meta) if len(ex.owned_items(rows[i])) >= min_items
            and (not kinds or ex.decision_kind(rows[i]) in kinds)]
    return sorted(rng.choice(pool, min(n, len(pool)), replace=False))


def ci(x, run, rng):
    return ex.boot_ci(x, run, rng)


f3 = lambda t: f"{t[0]:+.3f} [{t[1]:+.3f}, {t[2]:+.3f}]"   # noqa: E731
VOCAB = None


# ---------------------------------------------------------------------------------------------------- modes

def mode_coverage(net, rows, meta, args, rng):
    cards = [c for c in args.cards.split(",") if c]
    ids = {VOCAB.ids[c]: c for c in cards}
    stat = {c: {"offered": 0, "offer_runs": set(), "picked": 0, "deck_runs": set(), "deck_positions": 0} for c in cards}
    last_deck = {}
    prev = None
    for i, (r, m) in enumerate(zip(rows, meta)):
        if m["combat"]:
            continue
        deck = {}
        for j in r.deck():
            deck[int(r.ids[j, 0])] = deck.get(int(r.ids[j, 0]), 0) + r.copies(j)
        for cid, c in ids.items():
            if deck.get(cid):
                stat[c]["deck_runs"].add(m["run"])
                stat[c]["deck_positions"] += 1
        if prev is not None and prev[1] == m["run"]:
            for cid in prev[0]:
                if cid in ids and deck.get(cid, 0) > last_deck.get(cid, 0):
                    stat[ids[cid]]["picked"] += 1
        offered = {int(r.ids[j, 0]) for j in r.offered()}
        for cid in offered & set(ids):
            stat[ids[cid]]["offered"] += 1
            stat[ids[cid]]["offer_runs"].add(m["run"])
        prev = (offered, m["run"])
        last_deck = deck
    out = {}
    runs = meta[-1]["run"] + 1
    print(f"{'card':<16} {'offered':>7} {'runs':>5} {'picked':>6} {'owned runs':>10} {'owned pos':>9}   ({runs} runs)")
    for c in cards:
        s = stat[c]
        out[c] = {"offered": s["offered"], "offer_runs": len(s["offer_runs"]), "picked": s["picked"],
                  "deck_runs": len(s["deck_runs"]), "deck_positions": s["deck_positions"], "runs": runs}
        print(f"{c:<16} {s['offered']:7d} {len(s['offer_runs']):5d} {s['picked']:6d} {len(s['deck_runs']):10d} "
              f"{s['deck_positions']:9d}")
    return out


def mode_design(net, rows, meta, args, rng):
    """--designs "A:F1,F2:H1+H2+H3/L1+L2+L3;..." (offered A, owned factors F1, F2, density high / low lists)."""
    tp = ex.Templates(rows, meta, VOCAB)
    cr = ex.card_rewards(rows, meta)
    out = []
    for spec in args.designs.split(";"):
        a_name, fac, dens = spec.split(":")
        f1, f2 = fac.split(",")
        hi, lo = (x.split("+") for x in dens.split("/"))
        a_tpl = tp.offer(a_name)
        if a_tpl is None:
            print(f"{spec}: no offered token")
            continue
        names = [a_name, f1, f2] + hi + lo
        have_ids = {VOCAB.ids[x] for x in names}
        batch, index = [], []
        for si in cr:
            r = rows[si]
            have = {int(x) for x in r.ids[np.concatenate([r.deck(), r.offered(), r.relics()]), 0]}
            if have & have_ids or len(r.offered()) < 2 or len(r.offered()) > 4 or r.skip() < 0:
                continue
            s0 = r.copy()
            tok = int(rng.choice(s0.offered()))
            s0.offer(tok, *a_tpl)
            a = s0.action_of(tok)
            for e1, e2, k in itertools.product((0, 1), (0, 1), (0, 1)):
                v = s0
                for x in (hi if k else lo):
                    v = tp.add(v, x)
                if e1:
                    v = tp.add(v, f1)
                if e2:
                    v = tp.add(v, f2)
                batch.append(v)
            index.append((si, a, r.skip()))
        ev = ex.evaluate(net, batch)
        C = np.array([[ev[8 * n + j].z[a] - ev[8 * n + j].z[sk] for j in range(8)] for n, (_, a, sk) in enumerate(index)])
        run = np.array([meta[si]["run"] for si, _, _ in index])
        # 8 cells in (f1, f2, density) order; effects as +-1 contrasts / 4 (a main effect = mean difference)
        sign = np.array(list(itertools.product((-1, 1), (-1, 1), (-1, 1))), float)
        eff = {}
        for name, cols in (("f1", [0]), ("f2", [1]), ("density", [2]), ("f1 x f2", [0, 1]), ("f1 x density", [0, 2]),
                           ("f2 x density", [1, 2]), ("f1 x f2 x density", [0, 1, 2])):
            w = np.prod(sign[:, cols], 1) / 4
            eff[name] = ci(C @ w, run, rng)
        res = {"design": spec, "n": len(index), "runs": len(set(run)), "mean_contrast": float(C.mean()),
               "effects": eff, "built": sorted(tp.built & set(names))}
        out.append(res)
        print(f"\n{a_name} offered; f1 = {f1}, f2 = {f2}; density {'+'.join(hi)} vs {'+'.join(lo)}: n {len(index)}, "
              f"C(a, Skip) mean {C.mean():+.2f}" + (f"; tokens built for {res['built']}" if res["built"] else ""))
        for k, v in eff.items():
            print(f"   {k:<20} {f3(v)}")
    return out


def pair_states(rows, meta, tp, pair, controls, rng, limit):
    """Base positions for pair "A<K": (s0 = A offered, s1 = s0 + K, controls s0 + c), as explain.py's pairs mode."""
    a_name, k_name = pair.split("<")
    a_tpl = tp.offer(a_name)
    kk, k_tpl = tp.owned(k_name)
    if a_tpl is None or k_tpl is None:
        return []
    a_id, k_id = VOCAB.ids[a_name], VOCAB.ids[k_name]
    out = []
    for si in ex.card_rewards(rows, meta):
        r = rows[si]
        have = {int(x) for x in r.ids[np.concatenate([r.deck(), r.offered(), r.relics()]), 0]}
        if a_id in have or k_id in have or len(r.offered()) < 2 or len(r.offered()) > 4 or r.skip() < 0:
            continue
        s0 = r.copy()
        tok = int(rng.choice(s0.offered()))
        s0.offer(tok, *a_tpl)
        cs = [tp.add(s0, c) for c in controls if c not in (a_name, k_name) and VOCAB.ids[c] not in have
              and tp.owned(c)[1] is not None]
        out.append((si, s0, tp.add(s0, k_name), cs, s0.action_of(tok), r.skip(), tok))
    rng.shuffle(out)
    return out[:limit]


def mode_lens(net, rows, meta, args, rng):
    tp = ex.Templates(rows, meta, VOCAB)
    controls = [c for c in args.controls.split(",") if c]
    out = []
    for pair in args.pairs.split(","):
        ps = pair_states(rows, meta, tp, pair, controls, rng, args.limit)
        if not ps:
            print(f"{pair}: no positions")
            continue
        flat, index = [], []
        for si, s0, s1, cs, a, sk, _ in ps:
            index.append((si, len(flat), len(cs), a, sk))
            flat += [s0, s1] + cs
        lz = lens_logits(net, flat)
        L = len(lz[0])
        d2 = np.zeros((len(index), L))
        for n, (si, at, nc, a, sk) in enumerate(index):
            for l in range(L):
                C = lambda j: lz[j][l][a] - lz[j][l][sk]   # noqa: E731
                d2[n, l] = (C(at + 1) - C(at)) - np.mean([C(at + 2 + j) - C(at) for j in range(nc)])
        run = np.array([meta[x[0]]["run"] for x in index])
        res = {"pair": pair, "n": len(index), "d2_skip_by_layer": [ci(d2[:, l], run, rng) for l in range(L)]}
        out.append(res)
        print(f"{pair:<30} n {len(index):4d}  D2 vs Skip after " +
              "  ".join(f"L{l}: {v[0]:+.2f}" for l, v in enumerate(res["d2_skip_by_layer"])))
    return out


@torch.no_grad()
def mode_patch(net, rows, meta, args, rng):
    tp = ex.Templates(rows, meta, VOCAB)
    out = []
    for pair in args.pairs.split(","):
        ps = pair_states(rows, meta, tp, pair, [], rng, args.limit)
        if not ps:
            continue
        L = len(net.trunk.layers)
        groups = ("offered card", "run token", "other deck/relics", "all but the new token")
        rec = {g: [[] for _ in range(L + 1)] for g in groups}
        runs = []
        for si, s0, s1, _, a, sk, tok in ps:
            b0, b1 = ex.batch_of([s0]), ex.batch_of([s1])
            x0, x1 = trunk(net, b0), trunk(net, b1)
            C = lambda z: float(z[0, a] - z[0, sk])   # noqa: E731
            c0, c1 = C(heads(net, x0[-1], b0)[0]), C(heads(net, x1[-1], b1)[0])
            if abs(c1 - c0) < 0.05:
                continue
            # s1 = s0 with one token inserted: map s0's tokens to s1's (the new one is where tok types differ)
            n0 = len(s0.tt)
            ins = next((i for i in range(n0) if s0.tt[i] != s1.tt[i] or (s0.ids[i] != s1.ids[i]).any()), n0)
            m01 = [i if i < ins else i + 1 for i in range(n0)]
            sel = {"offered card": [tok], "run token": [0],
                   "other deck/relics": [i for i in range(1, n0) if i != tok and s0.tt[i] in (ex.CARD, ex.RELIC)],
                   "all but the new token": list(range(n0))}
            runs.append(meta[si]["run"])
            for g in groups:
                for l in range(L + 1):
                    patch = {l: [(0, i, x1[l][0, m01[i]]) for i in sel[g]]}
                    xp = trunk(net, b0, patch=patch)
                    rec[g][l].append((C(heads(net, xp[-1], b0)[0]) - c0) / (c1 - c0))
        res = {"pair": pair, "n": len(runs), "recovered": {g: [float(np.median(v)) if v else None for v in rec[g]]
                                                            for g in groups}}
        out.append(res)
        print(f"\n{pair}: n {len(runs)}; median share of the effect recovered by patching from s + k, per layer "
              f"(0 = embedding)")
        for g in groups:
            print(f"   {g:<24} " + "  ".join(f"L{l} {v:+.2f}" for l, v in enumerate(res["recovered"][g])))
    return out


def mode_calibration(net, rows, meta, args, rng):
    """Labels: outcome 0 = win, f = death on floor f; hp_end = HP at the end of the floor."""
    idx = [i for i, m in enumerate(meta) if m.get("outcome", -1) >= 0 and (args.combat or not m["combat"])]
    if args.max_positions and len(idx) > args.max_positions:
        idx = sorted(rng.choice(idx, args.max_positions, replace=False))
    ev = ex.evaluate(net, [rows[i] for i in idx])
    p = np.array([e.pwin for e in ev])
    y = np.array([1.0 if meta[i]["outcome"] == 0 else 0.0 for i in idx])
    ef = np.array([e.efloor for e in ev])
    yf = np.array([57.0 if meta[i]["outcome"] == 0 else meta[i]["outcome"] for i in idx])
    hp = np.array([e.hp for e in ev])
    yh = np.array([meta[i].get("hp_end", np.nan) for i in idx])
    act = np.array([int(round(float(rows[i].f[0, 0]) * 4)) for i in idx])
    run = np.array([meta[i]["run"] for i in idx])

    def ece(p, y, bins=10):
        edges = np.linspace(0, 1, bins + 1)
        k = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
        return float(sum(abs(p[k == j].mean() - y[k == j].mean()) * (k == j).mean() for j in range(bins) if (k == j).any()))

    def boot(fn, sel):
        ids = np.unique(run[sel])
        vals = []
        for _ in range(500):
            pick = rng.choice(ids, len(ids))
            s = np.concatenate([np.flatnonzero(sel & (run == i)) for i in pick])
            vals.append(fn(s))
        return float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))

    out = {"positions": len(idx), "runs": int(len(np.unique(run))), "wins": int(y[np.unique(run, return_index=True)[1]].sum())}
    print(f"# {len(idx)} positions, {out['runs']} runs, {out['wins']} wins")
    print(f"{'act':<5} {'pos':>6} {'runs':>5} {'mean P(win)':>11} {'win rate':>8} {'Brier':>7} {'ECE':>6} {'ECE 95%':>15} "
          f"{'E[floor]-floor':>14} {'E[HP]-HP':>9}")
    for a in (0, 1, 2, 3, 4):
        sel = np.ones(len(idx), bool) if a == 0 else act == a
        if sel.sum() < 20:
            continue
        lo, hi = boot(lambda s: ece(p[s], y[s]), sel)
        okh = sel & ~np.isnan(yh)
        r = {"positions": int(sel.sum()), "runs": int(len(np.unique(run[sel]))), "mean_p": float(p[sel].mean()),
             "win_rate": float(y[sel].mean()), "brier": float(((p[sel] - y[sel]) ** 2).mean()),
             "ece": ece(p[sel], y[sel]), "ece_ci": (lo, hi), "floor_bias": float((ef[sel] - yf[sel]).mean()),
             "hp_bias": float((hp[okh] - yh[okh]).mean()) if okh.any() else None,
             "hp_mae": float(np.abs(hp[okh] - yh[okh]).mean()) if okh.any() else None}
        edges = np.linspace(0, 1, 11)
        k = np.clip(np.digitize(p[sel], edges) - 1, 0, 9)
        r["reliability"] = [{"bin": j, "n": int((k == j).sum()), "p": float(p[sel][k == j].mean()),
                             "y": float(y[sel][k == j].mean())} for j in range(10) if (k == j).any()]
        out["all" if a == 0 else f"act {a}"] = r
        print(f"{'all' if a == 0 else a:<5} {r['positions']:6d} {r['runs']:5d} {r['mean_p']:11.3f} {r['win_rate']:8.3f} "
              f"{r['brier']:7.4f} {r['ece']:6.3f} [{lo:.3f}, {hi:.3f}] {r['floor_bias']:+14.2f} "
              f"{(r['hp_bias'] if r['hp_bias'] is not None else float('nan')):+9.2f}")
    print("reliability (all): " + "  ".join(f"{x['p']:.2f}->{x['y']:.2f} ({x['n']})" for x in out["all"]["reliability"]))
    return out


def mode_shapley(net, rows, meta, args, rng):
    out = []
    agree = []
    for si in sample_decisions(rows, meta, args.states, rng, args.kinds and set(args.kinds.split(","))):
        r = rows[si]
        base = ex.evaluate(net, [r])[0]
        a, b = best_two(base)
        players, phi, info = shapley(net, r, a, b, rng, args.perms, args.exact_limit)
        items = per_item(players, phi)
        loo = loo_effects(net, r, a, b)
        keys = list(items)
        rho = spearman([items[k] for k in keys], [loo.get(k, np.nan) for k in keys])
        agree.append(rho)
        top = sorted(items.items(), key=lambda kv: -abs(kv[1]))[:args.top]
        rep = {"sample": int(si), "kind": ex.decision_kind(r), "best": ex.action_label(r, a, VOCAB),
               "runner_up": ex.action_label(r, b, VOCAB), "contrast": float(base.z[a] - base.z[b]), **info,
               "spearman_loo": rho,
               "top": [(ex.item_name(r, k, i, VOCAB), v, loo.get((k, i), float("nan"))) for (k, i), v in top]}
        out.append(rep)
        print(f"[{rep['kind']}] {rep['best']} over {rep['runner_up']} (C {rep['contrast']:+.2f}); "
              f"{'exact' if info['exact'] else 'sampled'} ({info['evals']} evals, efficiency gap "
              f"{info['efficiency_gap']:+.3f}); Spearman vs LOO {rho:+.2f}")
        print("    " + ", ".join(f"{n} {v:+.2f} (LOO {l:+.2f})" for n, v, l in rep["top"]))
    print(f"\nmean Spearman(Shapley, LOO) {np.nanmean(agree):+.2f} over {len(agree)} decisions")
    return {"decisions": out, "mean_spearman_loo": float(np.nanmean(agree))}


def deletion(net, r, a, b, order, k_max):
    """C(a, b) after removing the first 1..k_max players of `order` (indices into players_of(r, copies=False))."""
    players = players_of(r, copies=False, keep_actions=(a, b))
    rows, keeps = [], []
    for k in range(1, min(k_max, len(order)) + 1):
        absent = []
        for j in order[:k]:
            absent += [j]
        v, kp = without_tokens(r, [players[j] for j in absent])
        rows.append(v)
        keeps.append(kp)
    evs = ex.evaluate(net, rows)
    return [contrast_of(e, kp, a, b) for e, kp in zip(evs, keeps)]


def without_tokens(r, items):
    """r without whole item tokens (every copy of a stack)."""
    v = r.copy()
    keep = np.arange(len(r.a_type))
    for kind, i in sorted(items, key=lambda x: -x[1]):
        for _ in range(r.copies(i) if kind == "card" else 1):
            keep = keep[v.remove(kind, i)]
    return v, keep


def randomized(net, upto):
    """A copy of net with the weights of the heads and the top `upto` trunk layers re-initialised."""
    import copy
    m = copy.deepcopy(net)
    torch.manual_seed(upto + 1)
    mods = [m.pol, m.w_c, m.w_s, m.w_t, m.summary_mlp, m.out_norm] + list(m.trunk.layers)[::-1][:max(0, upto - 1)]
    for mod in mods:
        for p in mod.parameters():
            with torch.no_grad():
                p.copy_(torch.randn_like(p) * (p.std() if p.numel() > 1 else 1.0))
    return m


def mode_faithful(net, rows, meta, args, rng):
    net2 = ex.load_net(args.ckpt2) if args.ckpt2 else None
    K = args.k_delete
    res = {"aopc": {}, "spearman": {}, "randomization": {}, "stability": []}
    aopc = {m: [] for m in ("LOO", "Shapley", "gate-IG", "rollout", "random")}
    rho = {m: [] for m in ("LOO~Shapley", "LOO~gate-IG", "LOO~rollout", "Shapley~gate-IG")}
    rand = {u: [] for u in range(1, len(net.trunk.layers) + 2)}
    for si in sample_decisions(rows, meta, args.states, rng):
        r = rows[si]
        base = ex.evaluate(net, [r])[0]
        a, b = best_two(base)
        c0 = float(base.z[a] - base.z[b])
        toks = [(k, i) for k, i in players_of(r, copies=False, keep_actions=(a, b))]
        loo = loo_effects(net, r, a, b)
        players, phi, _ = shapley(net, r, a, b, rng, args.perms, args.exact_limit)
        sh = per_item(players, phi)
        ig = gate_ig(net, r, a, b)
        ro = rollout(net, r, a)
        scores = {"LOO": [loo.get(t, np.nan) for t in toks], "Shapley": [sh.get(t, np.nan) for t in toks],
                  "gate-IG": [ig.get(t, np.nan) for t in toks], "rollout": [ro.get(t, np.nan) for t in toks]}
        for m, s in scores.items():
            order = list(np.argsort(-np.nan_to_num(np.asarray(s), nan=-1e9)))
            curve = deletion(net, r, a, b, order, K)
            aopc[m].append(float(np.nanmean([c0 - c for c in curve])))
        rc = []
        for _ in range(args.random_orders):
            curve = deletion(net, r, a, b, list(rng.permutation(len(toks))), K)
            rc.append(float(np.nanmean([c0 - c for c in curve])))
        aopc["random"].append(float(np.mean(rc)))
        rho["LOO~Shapley"].append(spearman(scores["LOO"], scores["Shapley"]))
        rho["LOO~gate-IG"].append(spearman(scores["LOO"], scores["gate-IG"]))
        rho["LOO~rollout"].append(spearman(scores["LOO"], scores["rollout"]))
        rho["Shapley~gate-IG"].append(spearman(scores["Shapley"], scores["gate-IG"]))
        for u in rand:
            m = randomized(net, u)
            rl = loo_effects(m, r, a, b)
            rand[u].append(spearman(scores["LOO"], [rl.get(t, np.nan) for t in toks]))
        if net2 is not None:
            e2 = ex.evaluate(net2, [r])[0]
            l2 = loo_effects(net2, r, a, b)
            res["stability"].append({"same_best": int(np.argmax(e2.z)) == a,
                                     "spearman": spearman(scores["LOO"], [l2.get(t, np.nan) for t in toks])})
    for m, v in aopc.items():
        res["aopc"][m] = float(np.mean(v))
    for m, v in rho.items():
        res["spearman"][m] = float(np.nanmean(v))
    for u, v in rand.items():
        res["randomization"][f"heads + top {u - 1} layers"] = float(np.nanmean(v))
    print(f"AOPC over the first {K} deletions (mean drop of C(best, runner-up); larger = more faithful):")
    print("   " + "  ".join(f"{m} {v:.3f}" for m, v in res["aopc"].items()))
    print("method agreement (mean Spearman): " + "  ".join(f"{m} {v:+.2f}" for m, v in res["spearman"].items()))
    print("cascading randomization, Spearman(LOO, LOO of the randomized net): " +
          "  ".join(f"{m}: {v:+.2f}" for m, v in res["randomization"].items()))
    if res["stability"]:
        st = res["stability"]
        res["stability_summary"] = {"same_best": float(np.mean([x["same_best"] for x in st])),
                                    "spearman": float(np.nanmean([x["spearman"] for x in st]))}
        print(f"checkpoint stability ({os.path.basename(args.ckpt2)}): same best action "
              f"{res['stability_summary']['same_best']:.2f}, Spearman of LOO {res['stability_summary']['spearman']:+.2f}")
    return res


def mode_counterfactual(net, rows, meta, args, rng):
    out = []
    sizes, hp_flip, sarfa_top = [], [], []
    for si in sample_decisions(rows, meta, args.states, rng):
        r = rows[si]
        base, items, evs, keeps = ex.explain_position(net, r, VOCAB)
        a, b = best_two(base)
        # PRINCE-style: smallest set of owned items whose removal changes the top action (greedy on the margin
        # effect, then drop members that are not needed)
        dc = ex.contrast_effects(base, evs, keeps, a, b)
        order = [j for j in np.argsort(-np.nan_to_num(dc, nan=-1e9)) if not np.isnan(dc[j]) and dc[j] > 0]
        toks = [(k, i) for k, i, _, _ in items]
        found = None
        for n in range(1, min(len(order), args.max_set) + 1):
            v, kp = without_tokens(r, [toks[j] for j in order[:n]])
            e = ex.evaluate(net, [v])[0]
            if a not in kp or int(kp[int(np.argmax(e.z))]) != a:
                found = list(order[:n])
                break
        if found:
            for j in list(found):
                trial = [x for x in found if x != j]
                if not trial:
                    break
                v, kp = without_tokens(r, [toks[x] for x in trial])
                e = ex.evaluate(net, [v])[0]
                if a not in kp or int(kp[int(np.argmax(e.z))]) != a:
                    found = trial
            v, kp = without_tokens(r, [toks[x] for x in found])
            e = ex.evaluate(net, [v])[0]
            new = ex.action_label(r, int(kp[int(np.argmax(e.z))]), VOCAB)
        sizes.append(len(found) if found else None)
        # SARFA (Puri et al. 2020): specificity dp of the chosen action, relevance 1 / (1 + KL) of the others
        sar = []
        p0 = np.exp(base.lp)
        for (k, i, name, _), e, kp in zip(items, evs, keeps):
            pos = {int(o): n for n, o in enumerate(kp)}
            if a not in pos:
                continue
            p1 = np.exp(e.lp)
            dp = p0[a] - p1[pos[a]]
            oth = [o for o in kp if o != a]
            q0 = p0[oth] / p0[oth].sum()
            q1 = p1[[pos[o] for o in oth]] / p1[[pos[o] for o in oth]].sum()
            K_ = 1.0 / (1.0 + float((q0 * np.log(q0 / q1)).sum()))
            sal = 2 * dp * K_ / (dp + K_) if dp > 0 else 0.0
            sar.append((name, float(sal), float(dp)))
        sar.sort(key=lambda x: -x[1])
        sarfa_top.append(sar[0][1] if sar else 0.0)
        # HP scan: the smallest HP drop / gain (in HP, current HP only) that changes the top action
        hp0 = round(float(r.f[np.flatnonzero(r.tt == ex.PLAYER)[0], 0]) * 100)
        mx = float(r.f[np.flatnonzero(r.tt == ex.PLAYER)[0], 1]) * 100
        pt = int(np.flatnonzero(r.tt == ex.PLAYER)[0])
        grid = [h for h in range(1, int(mx) + 1) if h != round(hp0)]
        vs = []
        for h in grid:
            v = r.copy()
            v.f[pt, 0] = np.float16(h / 100)
            v.f[pt, 2] = np.float16(h / mx)
            vs.append(v)
        ev = ex.evaluate(net, vs) if vs else []
        flips = [h for h, e in zip(grid, ev) if int(np.argmax(e.z)) != a]
        hp_d = min((abs(h - hp0) for h in flips), default=None)
        hp_flip.append(hp_d)
        hp_to = min(flips, key=lambda h: abs(h - hp0)) if flips else None
        rep = {"sample": int(si), "kind": ex.decision_kind(r), "best": ex.action_label(r, a, VOCAB),
               "minimal_set": [items[j][2] for j in found] if found else None,
               "choice_without_set": new if found else None, "sarfa": sar[:args.top], "hp": round(hp0),
               "hp_flip_at": hp_to, "choice_at_flip_hp": (ex.action_label(r, int(np.argmax(ev[grid.index(hp_to)].z)), VOCAB)
                                                          if hp_to is not None else None)}
        out.append(rep)
        ms = ", ".join(rep["minimal_set"]) if rep["minimal_set"] else f"none within {args.max_set}"
        print(f"[{rep['kind']}] {rep['best']}: without {{{ms}}} -> {rep['choice_without_set']}; HP {rep['hp']} -> "
              f"{rep['hp_flip_at']} flips to {rep['choice_at_flip_hp']}; SARFA " +
              ", ".join(f"{n} {s:.2f}" for n, s, _ in rep["sarfa"]))
    got = [s for s in sizes if s]
    summ = {"decisions": len(sizes), "with_minimal_set": len(got), "mean_set_size": float(np.mean(got)) if got else None,
            "set_size_hist": {int(k): int(v) for k, v in zip(*np.unique(got, return_counts=True))} if got else {},
            "hp_flip_share": float(np.mean([h is not None for h in hp_flip])),
            "median_hp_distance": float(np.median([h for h in hp_flip if h is not None])) if any(h is not None for h in hp_flip) else None}
    print(f"\n{summ}")
    return {"summary": summ, "decisions": out}


# ---------------------------------------------------------------------------------------------------- probes

BLOCK = ("DEFEND_RED", "SHRUG_IT_OFF", "FLAME_BARRIER", "IMPERVIOUS", "GHOSTLY_ARMOR", "TRUE_GRIT", "POWER_THROUGH",
         "ENTRENCH", "SECOND_WIND", "IRON_WAVE", "SENTINEL", "METALLICIZE", "BARRICADE", "FEEL_NO_PAIN", "JUGGERNAUT")
STRENGTH = ("INFLAME", "SPOT_WEAKNESS", "DEMON_FORM", "LIMIT_BREAK", "FLEX", "RUPTURE")
EXHAUST = ("CORRUPTION", "FEEL_NO_PAIN", "DARK_EMBRACE", "SECOND_WIND", "BURNING_PACT", "FIEND_FIRE", "SEVER_SOUL",
           "TRUE_GRIT", "SENTINEL")


def concepts(r):
    deck = {}
    for j in r.deck():
        n = VOCAB.enum.get(int(r.ids[j, 0]), "")
        deck[n] = deck.get(n, 0) + r.copies(j)
    size = max(1, sum(deck.values()))
    pt = int(np.flatnonzero(r.tt == ex.PLAYER)[0])
    rel = {VOCAB.enum.get(int(r.ids[j, 0]), "") for j in r.relics()}
    return {"act": round(float(r.f[0, 0]) * 4), "hp_ratio": float(r.f[pt, 2]), "deck_size": size,
            "gold": float(r.f[pt, 7]) * 100, "relics": len(rel),
            "block_share": sum(deck.get(c, 0) for c in BLOCK) / size,
            "strength_sources": sum(deck.get(c, 0) for c in STRENGTH),
            "exhaust_engine": float(sum(1 for c in EXHAUST if deck.get(c)) + ("relic:DEAD_BRANCH" in rel) >= 2),
            "has_corruption": float(deck.get("CORRUPTION", 0) > 0),
            "curses": sum(v for n, v in deck.items() if n and VOCAB.card_info(VOCAB.ids[n])[0] == "CURSE")}


@torch.no_grad()
def features(net, rows, batch=256):
    """Per row: the run summary per layer [L + 1, d] (logit-lens summary) and the mean input embedding."""
    out, emb = [], []
    for s in range(0, len(rows), batch):
        chunk = rows[s:s + batch]
        b = ex.batch_of(chunk)
        xs = trunk(net, b)
        out.append(torch.stack([summary(net, x, b) for x in xs], 1).numpy())
        m = b["mask"][..., None].float()
        emb.append(((xs[0] * m).sum(1) / m.sum(1)).numpy())
    return np.concatenate(out), np.concatenate(emb)


def probe_scores(X, y, run, binary, rng):
    """Run-grouped 5-fold ridge / logistic probe, scored on the pooled out-of-fold predictions: R^2, or for a 0/1
    concept the balanced accuracy (0.5 = chance whatever the base rate)."""
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.model_selection import GroupKFold
    from sklearn.preprocessing import StandardScaler
    pred = np.full(len(y), np.nan)
    for tr, te in GroupKFold(5).split(X, y, run):
        s = StandardScaler().fit(X[tr])
        if binary:
            if len(set(y[tr])) < 2:
                continue
            m = LogisticRegression(max_iter=1000, C=0.1, class_weight="balanced").fit(s.transform(X[tr]), y[tr])
        else:
            m = Ridge(alpha=10.0).fit(s.transform(X[tr]), y[tr])
        pred[te] = m.predict(s.transform(X[te]))
    ok = ~np.isnan(pred)
    if ok.sum() < 10:
        return float("nan")
    p, t = pred[ok], y[ok]
    if binary:
        return float(np.mean([(p[t == c] == c).mean() for c in (0.0, 1.0) if (t == c).any()]))
    return float(1 - ((p - t) ** 2).sum() / max(((t - t.mean()) ** 2).sum(), 1e-9))


def summary_grad(net, r, a):
    """d C(a, Skip) / d (run summary c) at position r (the heads' input; TCAV's directional derivative)."""
    b = ex.batch_of([r])
    with torch.no_grad():
        h = net.out_norm(trunk(net, b)[-1])
        live = b["mask"][:, 1:, None].float()
        c0 = h[:, 0] + net.summary_mlp((h[:, 1:] * live).sum(1) / live.sum(1))
    c = c0.clone().requires_grad_(True)
    d = h.shape[-1]

    def pick(idx, none):
        return torch.where((idx >= 0)[..., None], torch.gather(h, 1, idx.clamp(min=0)[..., None].expand(-1, -1, d)), none)

    with torch.enable_grad():
        e = (net.a_type(b["a_type"]) + net.w_s(pick(b["a_src"], net.a_none[0])) + net.w_t(pick(b["a_tgt"], net.a_none[1]))
             + net._act_feat(b["a_type"], b["a_f"]) + net.w_c(c)[:, None])
        z = net.pol(e).squeeze(-1)
        sk = r.skip()
        (z[0, a] - (z[0, sk] if sk >= 0 else 0)).backward()
    return c.grad[0].numpy()


def mode_probe(net, rows, meta, args, rng):
    idx = [i for i in ex.decisions(rows, meta)]
    if len(idx) > args.max_positions:
        idx = sorted(rng.choice(idx, args.max_positions, replace=False))
    rs = [rows[i] for i in idx]
    run = np.array([meta[i]["run"] for i in idx])
    C = [concepts(r) for r in rs]
    names = list(C[0])
    nets = [("ckpt", net)] + ([("ckpt2", ex.load_net(args.ckpt2))] if args.ckpt2 else [])
    rnd = ex.amber_net.AmberNet(d=net.type_emb.weight.shape[1], layers=len(net.trunk.layers),
                                hp_floors=net.hp_floor[2].weight.shape[0]).eval()
    rnd.sdpa = True
    nets.append(("random init", rnd))
    feats = {n: features(m, rs) for n, m in nets}
    out = {"positions": len(idx), "probes": {}}
    L = feats["ckpt"][0].shape[1]
    print(f"# {len(idx)} decisions; probe score (R^2, or accuracy for 0/1 concepts) on held-out runs; "
          f"control = the same probe on labels shuffled within act")
    print(f"{'concept':<18}" + "".join(f" {n[:10] + ' L' + str(l):>14}" for n, _ in nets for l in range(L))
          + f" {'input emb':>10} {'control':>8}")
    for c in names:
        y = np.array([x[c] for x in C], float)
        binary = set(np.unique(y)) <= {0.0, 1.0}
        if len(np.unique(y)) < 2:
            continue
        row = {}
        for n, _ in nets:
            for l in range(L):
                row[f"{n} L{l}"] = probe_scores(feats[n][0][:, l], y, run, binary, rng)
        row["input embedding"] = probe_scores(feats["ckpt"][1], y, run, binary, rng)
        acts = np.array([x["act"] for x in C])
        yc = y.copy()
        for a in np.unique(acts):
            s = acts == a
            yc[s] = rng.permutation(yc[s])
        row["control"] = probe_scores(feats["ckpt"][0][:, L - 1], yc, run, binary, rng)
        out["probes"][c] = row
        print(f"{c:<18}" + "".join(f" {row[f'{n} L{l}']:14.2f}" for n, _ in nets for l in range(L))
              + f" {row['input embedding']:10.2f} {row['control']:8.2f}")
    # TCAV (Kim et al. 2018): a concept direction (CAV) in the run summary c; score = share of the card rewards
    # offering the card where moving c along the CAV raises C(card, Skip); against CAVs of shuffled concept labels
    from sklearn.linear_model import LogisticRegression
    tc = {}
    X = feats["ckpt"][0][:, L - 1]
    tgt = [r for r in rs if ex.decision_kind(r) == "card reward"]
    grads = {}
    for card in ("CORRUPTION", "DARK_EMBRACE", "FEEL_NO_PAIN", "BARRICADE", "LIMIT_BREAK", "SHRUG_IT_OFF",
                 "INFLAME", "SPOT_WEAKNESS", "HEAVY_BLADE", "ENTRENCH", "BODY_SLAM"):
        cid = VOCAB.ids[card]
        g = []
        for r in tgt:
            hit = [t for t in r.offered() if int(r.ids[t, 0]) == cid]
            if hit:
                g.append(summary_grad(net, r, r.action_of(hit[0])))
        if len(g) >= 5:
            grads[card] = np.array(g)

    def cav(lbl):
        v = LogisticRegression(max_iter=1000, C=0.1, class_weight="balanced").fit(X, lbl).coef_[0]
        return v / np.linalg.norm(v)

    for concept in ("exhaust_engine", "has_corruption", "block_share", "strength_sources"):
        y = np.array([x[concept] for x in C], float)
        if concept in ("block_share", "strength_sources"):
            y = (y > np.median(y)).astype(float)
        if not (10 < y.sum() < len(y) - 10):
            continue
        v = cav(y)
        rnd = [cav(rng.permutation(y)) for _ in range(args.random_cavs)]
        res = {}
        for card, g in grads.items():
            sc = float(((g @ v) > 0).mean())
            rs_ = np.array([((g @ w) > 0).mean() for w in rnd])
            res[card] = {"n": len(g), "tcav": sc, "random_mean": float(rs_.mean()),
                         "p": float((np.abs(rs_ - 0.5) >= abs(sc - 0.5)).mean())}
        tc[concept] = res
        print(f"TCAV '{concept}' (share where the concept raises C(card, Skip); random-CAV mean; p): " +
              "  ".join(f"{k} {x['tcav']:.2f}/{x['random_mean']:.2f}/p{x['p']:.2f} ({x['n']})" for k, x in res.items()))
    out["tcav"] = tc
    # value GLM: logit P(win) from readable features
    from sklearn.linear_model import LinearRegression
    ev = ex.evaluate(net, rs)
    lg = np.array([math.log(max(e.pwin, 1e-6) / max(1 - e.pwin, 1e-6)) for e in ev])
    X = np.array([[x[c] for c in names] for x in C], float)
    Xs = (X - X.mean(0)) / X.std(0).clip(1e-9)
    m = LinearRegression().fit(Xs, lg)
    r2 = float(m.score(Xs, lg))
    out["value_glm"] = {"r2": r2, "coef_per_sd": dict(zip(names, map(float, m.coef_)))}
    print(f"value GLM: R^2 {r2:.2f} of logit P(win) from {', '.join(names)}; per-SD coefficients " +
          ", ".join(f"{n} {v:+.2f}" for n, v in out["value_glm"]["coef_per_sd"].items()))
    return out


def mode_interact(net, rows, meta, args, rng):
    import shapiq
    out = []
    for si in sample_decisions(rows, meta, args.states, rng, args.kinds and set(args.kinds.split(","))):
        r = rows[si]
        base = ex.evaluate(net, [r])[0]
        a, b = best_two(base)
        loo = loo_effects(net, r, a, b)
        # items whose removal takes action a or b away (a card-select choice's own card) have no contrast: no players
        top = [k for k, v in sorted(loo.items(), key=lambda kv: -abs(np.nan_to_num(kv[1])))
               if np.isfinite(v)][:args.players]
        n = len(top)
        if n < 3:
            continue
        cache = {}

        class G(shapiq.Game):
            def __init__(self):
                super().__init__(n_players=n, normalize=False)

            def value_function(self, coalitions):
                need = [tuple(c) for c in coalitions if tuple(c) not in cache]
                rws, kps = [], []
                for c in need:
                    v, kp = without_tokens(r, [top[j] for j in range(n) if not c[j]])
                    rws.append(v)
                    kps.append(kp)
                if rws:
                    for c, e, kp in zip(need, ex.evaluate(net, rws), kps):
                        cache[c] = contrast_of(e, kp, a, b)
                return np.array([cache[tuple(c)] for c in coalitions])

        g = G()
        comp = shapiq.ExactComputer(n_players=n, game=g)
        res = {}
        for index in ("k-SII", "FSII"):
            iv = comp(index=index, order=2)
            pairs = [(i, j, float(iv[(i, j)])) for i, j in itertools.combinations(range(n), 2)]
            pairs.sort(key=lambda x: -abs(x[2]))
            res[index] = [(ex.item_name(r, *top[i], VOCAB), ex.item_name(r, *top[j], VOCAB), v)
                          for i, j, v in pairs[:args.top]]
        rep = {"sample": int(si), "kind": ex.decision_kind(r), "best": ex.action_label(r, a, VOCAB),
               "runner_up": ex.action_label(r, b, VOCAB), "players": [ex.item_name(r, *t, VOCAB) for t in top],
               "evals": len(cache), **res}
        out.append(rep)
        print(f"[{rep['kind']}] {rep['best']} over {rep['runner_up']}: strongest pair interactions (k-SII) " +
              ", ".join(f"{x} x {y} {v:+.2f}" for x, y, v in res["k-SII"]))
    return out


def main():
    global VOCAB
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--ckpt2", help="faithful / probe: a second checkpoint (stability, across training)")
    ap.add_argument("--replay", required=True)
    ap.add_argument("--mode", required=True, choices=("coverage", "design", "lens", "patch", "calibration", "shapley",
                                                       "faithful", "counterfactual", "probe", "interact"))
    ap.add_argument("--cards", default="BARRICADE,ENTRENCH,BODY_SLAM,RUPTURE,BLOODLETTING,OFFERING,CORRUPTION,"
                                        "DARK_EMBRACE,FEEL_NO_PAIN,LIMIT_BREAK,INFLAME,SPOT_WEAKNESS,DEMON_FORM")
    ap.add_argument("--designs", default="BARRICADE:ENTRENCH,BODY_SLAM:SHRUG_IT_OFF+FLAME_BARRIER+GHOSTLY_ARMOR/"
                                         "POMMEL_STRIKE+TWIN_STRIKE+UPPERCUT;"
                                         "CORRUPTION:DARK_EMBRACE,FEEL_NO_PAIN:SHRUG_IT_OFF+FLAME_BARRIER+GHOSTLY_ARMOR/"
                                         "POMMEL_STRIKE+TWIN_STRIKE+UPPERCUT;"
                                         "RUPTURE:BLOODLETTING,OFFERING:HEMOKINESIS+COMBUST+BRUTALITY/"
                                         "POMMEL_STRIKE+TWIN_STRIKE+UPPERCUT")
    ap.add_argument("--pairs", default="CORRUPTION<DARK_EMBRACE,CORRUPTION<relic:DEAD_BRANCH,LIMIT_BREAK<INFLAME,"
                                       "BARRICADE<ENTRENCH,ENTRENCH<BARRICADE,RUPTURE<OFFERING")
    ap.add_argument("--controls", default=ex.DEFAULT_CONTROLS)
    ap.add_argument("--limit", type=int, default=200, help="lens / patch: base positions per pair")
    ap.add_argument("--states", type=int, default=20)
    ap.add_argument("--kinds", default="")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--perms", type=int, default=64)
    ap.add_argument("--exact-limit", type=int, default=4096)
    ap.add_argument("--k-delete", type=int, default=5)
    ap.add_argument("--random-orders", type=int, default=8)
    ap.add_argument("--max-set", type=int, default=6)
    ap.add_argument("--players", type=int, default=10)
    ap.add_argument("--max-positions", type=int, default=4000)
    ap.add_argument("--random-cavs", type=int, default=20, help="probe: TCAV baseline CAVs of shuffled labels")
    ap.add_argument("--combat", action="store_true", help="calibration: include combat positions")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--out")
    args = ap.parse_args()
    torch.set_num_threads(args.threads)
    rng = np.random.default_rng(args.seed)
    VOCAB = ex.Vocab()
    net = ex.load_net(args.ckpt)
    rows, meta = ex.load_replay(args.replay, extra=args.mode == "calibration")
    fn = globals()["mode_" + args.mode]
    rep = fn(net, rows, meta, args, rng)
    if args.out:
        with open(args.out, "w") as fh:
            json.dump({"ckpt": args.ckpt, "ckpt2": args.ckpt2, "replay": args.replay, "mode": args.mode,
                       "seed": args.seed, "report": rep}, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
