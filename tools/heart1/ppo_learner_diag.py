"""Per-update PPO diagnostics (ppo_train --diag 1; off by default): outcome decomposition, critic quality against
the Monte Carlo outcome per act, and full-batch policy shift (KL, entropy) per screen.

Why (PPO diagnostics findings, 2026-11-05): the Heart rate alone hid survival effects that the final floor shows
(CRIT_PRE lost Act 1 survival 30 updates before G1 saw it); the logged value loss is measured against the
bootstrapped lambda return, which the critic feeds itself, so it cannot tell a good critic from a self-consistent
one (LONG_B: explained variance 0.69 against that target, 0.26 against the game outcome); and the first-minibatch
approx KL (192 decisions) is too noisy to read the behaviour-to-learner lag from.

Everything here is computed from what the learner already holds at update start (critic values and logits of
the learner net, the behaviour net's logits from the trajectory lines) plus, after training, one more forward pass
for the update's own movement. It reads, never changes, the training data.

Definitions (all over the update's games / net decisions):
  outcome      act2/act3/act4 = share of games whose final floor is >= 17 / 34 / 51 (ACT_FLOORS); mean_floor;
               death_act = share of games lost in act k (act of the final floor); stalled = games without decisions.
  critic       V = the learner's critic at update start (before this update's training); target mc = the Monte
               Carlo return of the configured reward (lambda = 1; equals 1{Heart} for --reward heart with gamma 1);
               y = 1{Heart kill} of the decision's game. Per group (all, act1..act4 by the decision's own act,
               first = each game's first net decision): n, ev = 1 - Var(mc - V) / Var(mc), auc of V for y
               (Mann-Whitney, ties averaged), brier = mean((clip(V, 0, 1) - y)^2), mean_v, mean_y.
               ev_lambda = the same explained variance against the update's lambda targets (what value_loss sees).
  shift        decisions with more than one choice, at their sampling temperature. kl_behaviour = KL(behaviour ||
               learner at update start), from the logits stored in each trajectory line; kl_update = KL(learner at
               update start || learner after the update). mean, median, p90, argmax agreement, and per screen
               (ScreenState names) n, kl, agree, entropy (learner at update start), entropy_behaviour.
"""
import math

import torch
import torch.nn.functional as F

ACT_FLOORS = (17, 34, 51)   # = ppo_train.ACT_FLOORS (a test checks they agree)
SCREENS = {0: "invalid", 1: "event", 2: "rewards", 3: "boss_relic", 4: "card_select", 5: "map", 6: "treasure",
           7: "rest", 8: "shop", 9: "battle"}   # include/game/GameContext.h ScreenState


def act_of_floor(floor):
    return 1 + sum(1 for f in ACT_FLOORS if (floor or 0) >= f)


def _r(x, nd=5):
    return None if x is None else round(float(x), nd)


def outcome_stats(games):
    n = len(games)
    if n == 0:
        return {"games": 0}
    floors = [int(g["outcome"].get("floor", 0) or 0) for g in games]
    heart = [bool(g["outcome"].get("heart_kill")) for g in games]
    death = {str(k): 0 for k in (1, 2, 3, 4)}
    for f, h in zip(floors, heart):
        if not h:
            death[str(min(act_of_floor(f), 4))] += 1
    out = {"games": n, "heart": _r(sum(heart) / n), "mean_floor": _r(sum(floors) / n, 3),
           "stalled": sum(1 for g in games if not g["steps"])}
    for k, f in zip((2, 3, 4), ACT_FLOORS):
        out[f"act{k}"] = _r(sum(1 for x in floors if x >= f) / n)
    out["death_act"] = {k: _r(v / n) for k, v in death.items()}
    return out


def auc(scores, labels):
    """P(score of a positive > score of a negative), ties count half; None without both classes."""
    pos = sum(1 for y in labels if y)
    neg = len(labels) - pos
    if pos == 0 or neg == 0:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    rank_sum, i = 0.0, 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1   # 1-based average rank of the tie block
        rank_sum += avg * sum(1 for t in range(i, j + 1) if labels[order[t]])
        i = j + 1
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def explained_variance(pred, target):
    n = len(target)
    if n < 2:
        return None
    mt = sum(target) / n
    vt = sum((t - mt) ** 2 for t in target) / n
    if vt <= 0:
        return None
    res = [t - p for p, t in zip(pred, target)]
    mr = sum(res) / n
    return 1.0 - sum((r - mr) ** 2 for r in res) / n / vt


def _critic_group(v, mc, y):
    n = len(v)
    if n == 0:
        return {"n": 0}
    return {"n": n, "ev": _r(explained_variance(v, mc)), "auc": _r(auc(v, y)),
            "brier": _r(sum((min(max(a, 0.0), 1.0) - b) ** 2 for a, b in zip(v, y)) / n),
            "mean_v": _r(sum(v) / n), "mean_y": _r(sum(y) / n)}


def critic_stats(games, values, mc, lam_targets=None):
    """values / mc / lam_targets: one per net decision, in games' step order."""
    groups = {"all": [], "act1": [], "act2": [], "act3": [], "act4": [], "first": []}
    k = 0
    for g in games:
        y = 1.0 if g["outcome"].get("heart_kill") else 0.0
        for t, s in enumerate(g["steps"]):
            row = (values[k], mc[k], y)
            groups["all"].append(row)
            groups[f"act{min(max(int(s.get('act') or 1), 1), 4)}"].append(row)
            if t == 0:
                groups["first"].append(row)
            k += 1
    out = {name: _critic_group([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows])
           for name, rows in groups.items()}
    if lam_targets is not None:
        out["ev_lambda"] = _r(explained_variance(values, lam_targets))
    return out


def _padded(rows, temps):
    """Ragged logit lists -> (N, Cmax) log-probs at each row's temperature (padding -inf -> prob 0)."""
    cmax = max(len(r) for r in rows)
    x = torch.full((len(rows), cmax), float("-inf"), dtype=torch.float64)
    for i, r in enumerate(rows):
        x[i, :len(r)] = torch.tensor(r, dtype=torch.float64)
    t = torch.tensor(temps, dtype=torch.float64)[:, None]
    return F.log_softmax(x / t, dim=-1)


def _kl_rows(lp, lq):
    """Per-row KL(p || q), entropy of p and of q, argmax agreement, for padded log-prob tensors."""
    pad = torch.isneginf(lp)
    p, q = lp.exp().masked_fill(pad, 0.0), lq.exp().masked_fill(torch.isneginf(lq), 0.0)
    lp0, lq0 = lp.masked_fill(pad, 0.0), lq.masked_fill(torch.isneginf(lq), 0.0)
    kl = (p * (lp0 - lq0)).sum(-1).clamp_min(0.0)
    ent_p = -(p * lp0).sum(-1)
    ent_q = -(q * lq0).sum(-1)
    agree = (lp.argmax(-1) == lq.argmax(-1)).double()
    return kl, ent_p, ent_q, agree


def shift_stats(p_logits, q_logits, temps, screens, chunk=4096):
    """KL(p || q) over decisions (lists of logit lists of equal row lengths), summary + per screen.

    entropy = entropy of q (the learner side), entropy_behaviour = entropy of p."""
    if not p_logits:
        return {"n": 0}
    kls, eps, eqs, ags = [], [], [], []
    for i in range(0, len(p_logits), chunk):
        a = _padded(p_logits[i:i + chunk], temps[i:i + chunk])
        b = _padded(q_logits[i:i + chunk], temps[i:i + chunk])
        kl, ep, eq, ag = _kl_rows(a, b)
        kls.append(kl); eps.append(ep); eqs.append(eq); ags.append(ag)
    kl, ep, eq, ag = torch.cat(kls), torch.cat(eps), torch.cat(eqs), torch.cat(ags)
    out = {"n": len(p_logits), "mean": _r(kl.mean(), 6), "median": _r(kl.median(), 6),
           "p90": _r(torch.quantile(kl, 0.9), 6), "agree": _r(ag.mean()), "entropy": _r(eq.mean()),
           "entropy_behaviour": _r(ep.mean())}
    scr = torch.tensor(screens)
    per = {}
    for s in sorted(set(screens)):
        m = scr == s
        per[SCREENS.get(s, str(s))] = {"n": int(m.sum()), "kl": _r(kl[m].mean(), 6), "agree": _r(ag[m].mean()),
                                       "entropy": _r(eq[m].mean()), "entropy_behaviour": _r(ep[m].mean())}
    tot = float(kl.sum())
    for name, d in per.items():   # the screen's share of the summed KL
        d["kl_share"] = _r(d["kl"] * d["n"] / tot) if tot > 0 else None
    out["screens"] = per
    return out


def behaviour_shift(steps, logits_now):
    """kl_behaviour: KL(behaviour net || learner at update start) on decisions with > 1 choice whose trajectory line
    kept the behaviour logits ("blogits", load_games(keep_logits=True))."""
    p, q, temps, screens = [], [], [], []
    missing = 0
    for s, lg in zip(steps, logits_now):
        if s["n"] <= 1:
            continue
        b = s.get("blogits")
        if b is None or len(b) != len(lg):
            missing += 1
            continue
        p.append(b); q.append(lg)
        temps.append(float(s["temp"]) if s["temp"] > 0 else 1.0)
        screens.append(int(s.get("screen", -1)))
    out = shift_stats(p, q, temps, screens)
    out["missing"] = missing
    return out


def update_shift(steps, logits_start, logits_end):
    """kl_update: KL(learner at update start || learner after the update) on decisions with > 1 choice."""
    p, q, temps, screens = [], [], [], []
    for s, a, b in zip(steps, logits_start, logits_end):
        if s["n"] <= 1:
            continue
        p.append(a); q.append(b)
        temps.append(float(s["temp"]) if s["temp"] > 0 else 1.0)
        screens.append(int(s.get("screen", -1)))
    return shift_stats(p, q, temps, screens)


def finite(x):
    """JSON-safe: NaN/inf -> None, recursively."""
    if isinstance(x, dict):
        return {k: finite(v) for k, v in x.items()}
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x
