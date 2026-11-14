"""PPO run diagnostics (written for LONG_B): the update history from loop.json and one iteration's stored games.

PPO diagnostics findings 2026-11-05. History: Heart rate per update and in 10-update blocks, warm-up vs last 20,
OLS trend, entropy, approx KL, value loss, first-minibatch KL (L1_history.png). One iteration's trajectories: outcome
decomposition, critic of the behaviour net vs 1{Heart} per act (EV, AUC, Brier, calibration; L2_critic.png),
GAE advantages (lambda 0.97, reward 1{Heart}): kill-game share of |A|, within-game ICC and effective sample, per-act
scale, per-screen entropy (L3_advantage_policy.png). Writes summary.json and itNNNN_rows.json to --out only.

    python3 tools/heart1/longb_diag.py --run ~/ppo-longb/LONG_B --iteration 163 --out OUT_DIR

--run is the learner's arm directory (loop.json, parts/traj-NNNN-pK.jsonl.gz; a `ppo_cloud.py kept --fetch` output
has the same layout); --traj-dir overrides where the parts are. Read only: nothing is written under --run.
Needs numpy and matplotlib. The per-update numbers of a run with ppo_train --diag 1 are in loop.json directly.
"""
import argparse
import glob
import gzip
import json
import math
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

L = TRAJ = OUT = None   # set by main(): arm directory (loop.json), parts directory, output directory
IT = None   # the iteration whose trajectories are read

PAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, INK3, SURF, GRID = "#0b0b0b", "#52514e", "#8a8984", "#fcfcfb", "#e6e5e1"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.titlesize": 10.5, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "font.size": 9, "legend.frameon": False, "legend.fontsize": 8.5, "lines.linewidth": 1.6,
    "xtick.major.size": 0, "ytick.major.size": 0,
})
SCREEN = {0: "invalid", 1: "event", 2: "rewards", 3: "boss relic", 4: "card select", 5: "map", 6: "treasure",
          7: "rest", 8: "shop", 9: "battle"}
GAMES, WARMUP = None, None   # from loop.json: games per update, value-only (warm-up) updates
summary = {}


# ---------------------------------------------------------------- A. history

def history():
    global GAMES, WARMUP
    its = json.load(open(os.path.join(L, "loop.json")))["iterations"]
    GAMES = int(its[0]["games"])
    WARMUP = sum(1 for r in its if r.get("value_only"))
    it = np.array([r["iteration"] for r in its]); hr = np.array([r["heart_rate"] for r in its]) * 100
    vonly = np.array([r["value_only"] for r in its])
    warm = hr[vonly]; pol = ~vonly
    p0 = warm.mean() / 100
    se0 = 100 * math.sqrt(p0 * (1 - p0) / (GAMES * len(warm)))
    last20 = hr[-20:]
    p1 = last20.mean() / 100
    se1 = 100 * math.sqrt(p1 * (1 - p1) / (GAMES * 20))
    # linear trend over policy updates (OLS on per-update rates; SE from residuals)
    x, y = it[pol].astype(float), hr[pol]
    A = np.vstack([x, np.ones_like(x)]).T
    coef, res, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ coef
    s2 = resid.var(ddof=2); se_slope = math.sqrt(s2 / ((x - x.mean()) ** 2).sum())
    summary["history"] = {
        "updates": int(len(its)), "warmup_updates": int(vonly.sum()),
        "heart_warmup_pct": warm.mean(), "heart_warmup_se": se0, "heart_last20_pct": last20.mean(), "heart_last20_se": se1,
        "delta_last20_minus_warmup_pp": last20.mean() - warm.mean(), "delta_se": math.sqrt(se0 ** 2 + se1 ** 2),
        "slope_pp_per_10_updates": coef[0] * 10, "slope_se": se_slope * 10,
        "resid_sd_pp": float(resid.std(ddof=2)), "binomial_sd_pp": 100 * math.sqrt(p1 * (1 - p1) / GAMES),
        "entropy_first_policy": float(its[WARMUP]["entropy"]), "entropy_last": float(its[-1]["entropy"]),
        "approx_kl_mean": float(np.mean([r["approx_kl"] for r in its if not r["value_only"]])),
        "clipfrac_mean": float(np.mean([r["clipfrac"] for r in its if not r["value_only"]])),
        "value_loss_last20": float(np.mean([r["value"] for r in its[-20:]])),
        "gap_last20": float(np.mean([r["mean_value"] - r["mean_return"] for r in its[-20:]])),
        "first_mb_kl_median": float(np.median([r["first_mb_approx_kl"] for r in its if not r["value_only"]])),
        "first_mb_kl_p90": float(np.percentile([r["first_mb_approx_kl"] for r in its if not r["value_only"]], 90)),
        "actor_s_median": float(np.median([r["actor_s"] for r in its])), "actor_s_p90": float(np.percentile([r["actor_s"] for r in its], 90)),
        "train_s_mean": float(np.mean([r["train_s"] for r in its])),
        "games_total": int(GAMES * len(its)), "kill_games_per_update_last20": float(p1 * GAMES),
    }
    # blocks of 10 policy updates
    blocks = []
    for b in range(WARMUP, len(its), 10):
        sl = hr[b:b + 10]
        if len(sl) == 10:
            m = sl.mean(); blocks.append((b + 1, b + 10, m, 100 * math.sqrt(m / 100 * (1 - m / 100) / (GAMES * 10))))
    summary["history"]["blocks"] = blocks

    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    ax = axes[0, 0]
    ax.axvspan(0.5, WARMUP + 0.5, color=INK3, alpha=0.08, lw=0)
    ax.text(1, 23.5, "critic warm-up (heart1 policy)", color=INK2, fontsize=8)
    ax.plot(it, hr, color=PAL[0], lw=1.0, alpha=0.75, marker="o", ms=2.5)
    for lo, hi, m, se in blocks:
        ax.plot([lo, hi], [m, m], color=INK, lw=2.4)
        ax.plot([lo, hi], [m + 1.96 * se, m + 1.96 * se], color=INK, lw=0.6, alpha=0.5)
        ax.plot([lo, hi], [m - 1.96 * se, m - 1.96 * se], color=INK, lw=0.6, alpha=0.5)
    ax.axhline(warm.mean(), color=PAL[7], lw=1.0, ls="--")
    ax.text(len(its) - 1, warm.mean() + 0.3, f"heart1 start {warm.mean():.1f}%", color=PAL[7], fontsize=8, ha="right")
    xx = np.array([WARMUP + 1, len(its)]); ax.plot(xx, coef[0] * xx + coef[1], color=PAL[1], lw=1.4)
    ax.set_title(f"Heart % per update ({GAMES} games), 10-update blocks with 95% CI\ntrend {coef[0]*10:+.2f} ± {se_slope*10:.2f} pp per 10 updates")
    ax.set_xlabel("update"); ax.set_ylabel("Heart kills, %")
    ax = axes[0, 1]
    ax.plot(it[pol], [r["entropy"] for r in its if not r["value_only"]], color=PAL[0], label="policy entropy")
    ax.set_ylabel("entropy"); ax.set_xlabel("update"); ax.set_title("Policy entropy (left axis)\napprox KL per update (right axis)")
    ax2 = ax.twinx(); ax2.grid(False)
    ax2.plot(it[pol], [r["approx_kl"] for r in its if not r["value_only"]], color=PAL[1], lw=1.0, label="approx KL")
    ax2.set_ylabel("approx KL", color=PAL[1]); ax2.set_ylim(0, 0.02); ax2.spines["right"].set_visible(False)
    ax.legend(loc="upper left"); ax2.legend(loc="upper right")
    ax = axes[1, 0]
    ax.plot(it, [r["value"] for r in its], color=PAL[2], label="value loss (½ MSE vs target)")
    ax.set_yscale("log"); ax.set_xlabel("update"); ax.set_ylabel("value loss (log)")
    ax.set_title("Value loss: warm-up fits λ=1 Monte Carlo targets,\nPPO phase fits λ=0.97 bootstrapped targets")
    ax2 = ax.twinx(); ax2.grid(False)
    ax2.plot(it, [r["mean_value"] - r["mean_return"] for r in its], color=PAL[4], lw=1.0, label="mean value − mean return")
    ax2.axhline(0, color=INK3, lw=0.6); ax2.set_ylim(-0.08, 0.4); ax2.set_ylabel("value − return", color=PAL[4]); ax2.spines["right"].set_visible(False)
    ax.legend(loc="upper right"); ax2.legend(loc="center right")
    ax = axes[1, 1]
    ax.plot(it[pol], [r["first_mb_approx_kl"] for r in its if not r["value_only"]], color=PAL[6], lw=1.0, label="KL behaviour→learner at update start")
    ax.plot(it[pol], [r["approx_kl"] for r in its if not r["value_only"]], color=PAL[1], lw=1.0, label="approx KL of the update")
    ax.set_ylim(0, 0.16); ax.set_xlabel("update"); ax.set_ylabel("KL")
    ax.set_title("Pipeline staleness per update\n(spikes: updates whose actors ran far ahead)")
    ax.legend()
    fig.suptitle(f"{os.path.basename(os.path.normpath(L))}: {GAMES} games per update, {WARMUP} critic warm-up updates — history through update {len(its)}",
                 x=0.01, ha="left", fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95)); fig.savefig(os.path.join(OUT, "L1_history.png"), dpi=160); plt.close(fig)


# ---------------------------------------------------------------- B. one iteration's trajectories

def load_traj():
    games = {}
    paths = sorted(glob.glob(os.path.join(TRAJ, f"traj-{IT:04d}-p*.jsonl.gz")))
    if not paths:
        sys.exit(f"no {TRAJ}/traj-{IT:04d}-p*.jsonl.gz")
    for p in paths:
        with gzip.open(p, "rt") as f:
            steps, meta = {}, {}
            for line in f:
                r = json.loads(line)
                if r["type"] == "decision":
                    steps.setdefault(r["seed"], []).append(r)
                elif r["type"] == "game":
                    meta[r["seed"]] = r
            for seed, g in meta.items():
                st = sorted(steps.get(seed, []), key=lambda s: s["idx"])
                games[seed] = {"outcome": g["outcome"], "info": g, "steps": st}
    return games


def gae(rew, val, gamma, lam):
    n = len(rew); adv = [0.0] * n; last = 0.0
    for t in reversed(range(n)):
        nxt = val[t + 1] if t + 1 < n else 0.0
        d = rew[t] + gamma * nxt - val[t]; last = d + gamma * lam * last; adv[t] = last
    return adv, [a + v for a, v in zip(adv, val)]


def softmax_stats(logits, temp):
    z = np.array(logits, dtype=float) / (temp if temp > 0 else 1.0)
    z -= z.max(); p = np.exp(z); p /= p.sum()
    ent = float(-(p * np.log(np.clip(p, 1e-12, 1))).sum())
    return p, ent


def auc(score, y):
    order = np.argsort(score); r = np.empty(len(score)); r[order] = np.arange(1, len(score) + 1)
    # average ranks for ties
    s_sorted = score[order]; i = 0
    while i < len(s_sorted):
        j = i
        while j + 1 < len(s_sorted) and s_sorted[j + 1] == s_sorted[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = (i + 1 + j + 1) / 2
        i = j + 1
    npos = y.sum(); nneg = len(y) - npos
    return float((r[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def ev(v, y):
    return float(1 - np.var(y - v) / np.var(y))


def trajectories():
    games = load_traj()
    n_games = len(games)
    outs = [g["outcome"] for g in games.values()]
    heart = np.array([o["heart_kill"] for o in outs], float)
    floor = np.array([o["floor"] for o in outs], float)
    summary[f"it{IT:04d}_outcomes"] = {
        "games": n_games, "heart_pct": heart.mean() * 100, "act4_reached_pct": (floor >= 51).mean() * 100,
        "act3_reached_pct": (floor >= 34).mean() * 100, "act2_reached_pct": (floor >= 17).mean() * 100,
        "mean_floor": floor.mean(), "fallbacks": int(sum(g["info"]["fallbacks"] for g in games.values())),
        "decisions": int(sum(len(g["steps"]) for g in games.values())),
        "single_choice": int(sum(1 for g in games.values() for s in g["steps"] if s["n"] == 1)),
        "death_encounter_top": {}}
    # per-decision arrays
    rows = []
    for seed, g in games.items():
        y = float(g["outcome"]["heart_kill"])
        vals = [s["value"] for s in g["steps"]]
        rew = [0.0] * len(vals); rew[-1] = y
        adv, ret = gae(rew, vals, 1.0, 0.97)
        for k, s in enumerate(g["steps"]):
            p, ent = softmax_stats(s["logits"], s["temp"]) if s["n"] > 1 else (np.array([1.0]), 0.0)
            rows.append({"seed": seed, "y": y, "v": s["value"], "act": s["act"], "floor": s["floor"], "screen": s["screen"],
                         "n": s["n"], "ent": ent, "pchosen": float(p[s["chosen"]]), "pmax": float(p.max()),
                         "adv": adv[k], "lam_ret": ret[k], "t": k, "T": len(vals)})
    R = {k: np.array([r[k] for r in rows]) for k in rows[0]}
    policy = R["n"] > 1
    # critic
    crit = {"all": {"n": int(len(R["v"])), "ev_mc": ev(R["v"], R["y"]), "ev_lam": ev(R["v"], R["lam_ret"]),
                    "brier": float(np.mean((R["v"] - R["y"]) ** 2)), "auc": auc(R["v"], R["y"]),
                    "mean_v": float(R["v"].mean()), "mean_y": float(R["y"].mean())}}
    for a in (1, 2, 3, 4):
        m = R["act"] == a
        if m.sum() > 100 and 0 < R["y"][m].mean() < 1:
            crit[f"act{a}"] = {"n": int(m.sum()), "ev_mc": ev(R["v"][m], R["y"][m]), "ev_lam": ev(R["v"][m], R["lam_ret"][m]),
                               "brier": float(np.mean((R["v"][m] - R["y"][m]) ** 2)), "auc": auc(R["v"][m], R["y"][m]),
                               "mean_v": float(R["v"][m].mean()), "mean_y": float(R["y"][m].mean())}
    # first decision of each game: the critic's prior at floor 0
    first = np.array([r["t"] == 0 for r in rows])
    crit["first_decision"] = {"n": int(first.sum()), "mean_v": float(R["v"][first].mean()), "sd_v": float(R["v"][first].std()),
                              "auc": auc(R["v"][first], R["y"][first]), "ev_mc": ev(R["v"][first], R["y"][first])}
    summary["critic"] = crit
    # advantages
    a = R["adv"]; ap = a[policy]
    kill = R["y"] == 1
    mass_kill = float(np.abs(a[policy & kill]).sum() / np.abs(ap).sum())
    # within-game correlation of raw advantages (policy decisions): ICC via one-way ANOVA
    seeds = R["seed"][policy]
    grp = {}
    for s_, v_ in zip(seeds, ap):
        grp.setdefault(s_, []).append(v_)
    k = len(grp); N = len(ap); m_bar = N / k
    gm = ap.mean()
    ssb = sum(len(v) * (np.mean(v) - gm) ** 2 for v in grp.values()); ssw = sum(((np.array(v) - np.mean(v)) ** 2).sum() for v in grp.values())
    msb = ssb / (k - 1); msw = ssw / (N - k)
    icc = (msb - msw) / (msb + (m_bar - 1) * msw)
    deff = 1 + (m_bar - 1) * icc
    summary["advantage"] = {"policy_decisions": int(policy.sum()), "mean_abs": float(np.abs(ap).mean()), "sd": float(ap.std()),
                            "p_abs_gt_0.1": float((np.abs(ap) > 0.1).mean()), "p_abs_gt_0.3": float((np.abs(ap) > 0.3).mean()),
                            "share_abs_mass_kill_games": mass_kill, "kill_games": int(heart.sum()),
                            "icc_within_game": float(icc), "design_effect": float(deff), "effective_sample": float(N / deff),
                            "sd_by_act": {int(x): float(ap[R["act"][policy] == x].std()) for x in (1, 2, 3, 4)},
                            "mean_abs_kill": float(np.abs(a[policy & kill]).mean()), "mean_abs_nokill": float(np.abs(a[policy & ~kill]).mean())}
    # per screen
    per = {}
    for sc in sorted(set(R["screen"].tolist())):
        m = R["screen"] == sc
        mp = m & policy
        per[SCREEN.get(int(sc), str(sc))] = {"decisions": int(m.sum()), "policy": int(mp.sum()), "mean_n": float(R["n"][mp].mean()) if mp.any() else 0,
                                           "entropy": float(R["ent"][mp].mean()) if mp.any() else 0,
                                           "pchosen": float(R["pchosen"][mp].mean()) if mp.any() else 0,
                                           "pmax": float(R["pmax"][mp].mean()) if mp.any() else 0,
                                           "adv_sd": float(R["adv"][mp].std()) if mp.any() else 0}
    summary["per_screen"] = per
    json.dump({"R": {k: v.tolist() for k, v in R.items() if k != "seed"}}, open(os.path.join(OUT, f"it{IT:04d}_rows.json"), "w"))

    # ---- plots
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))
    ax = axes[0]
    bins = np.linspace(0, 1, 11)
    for a_, col in zip((1, 2, 3, 4), PAL):
        m = R["act"] == a_
        v, y = R["v"][m], R["y"][m]
        xs, ys, ns = [], [], []
        for lo, hi in zip(bins[:-1], bins[1:]):
            mm = (v >= lo) & (v < hi)
            if mm.sum() >= 30:
                xs.append(v[mm].mean()); ys.append(y[mm].mean()); ns.append(mm.sum())
        ax.plot(xs, ys, marker="o", ms=4, color=col, label=f"act {a_} (n={m.sum():,})")
    ax.plot([0, 1], [0, 1], color=INK3, lw=0.8, ls="--"); ax.set_xlim(0, 0.8); ax.set_ylim(0, 0.8)
    ax.set_xlabel("critic value V (behaviour net)"); ax.set_ylabel("observed Heart-kill rate in the bin")
    ax.set_title("Calibration: V vs outcome, by act (bins with ≥ 30 decisions)"); ax.legend()
    ax = axes[1]
    labels = ["all", "act1", "act2", "act3", "act4"]; labels = [l for l in labels if l in crit]
    xs = np.arange(len(labels))
    ax.bar(xs - 0.2, [crit[l]["ev_mc"] for l in labels], 0.38, color=PAL[0], label="EV vs Monte Carlo 1{Heart}")
    ax.bar(xs + 0.2, [crit[l]["auc"] for l in labels], 0.38, color=PAL[2], label="AUC vs 1{Heart}")
    for i, l in enumerate(labels):
        ax.text(i - 0.2, crit[l]["ev_mc"] + 0.01, f'{crit[l]["ev_mc"]:.2f}', ha="center", fontsize=8, color=INK2)
        ax.text(i + 0.2, crit[l]["auc"] + 0.01, f'{crit[l]["auc"]:.2f}', ha="center", fontsize=8, color=INK2)
    ax.set_xticks(xs); ax.set_xticklabels(labels); ax.set_ylim(0, 1); ax.set_title(f"Critic skill per act (iteration {IT}, {len(R['v']):,} decisions)"); ax.legend(loc="upper left")
    ax = axes[2]
    ax.hist(R["v"][R["y"] == 0], bins=40, range=(0, 1), color=PAL[0], alpha=0.7, label="games lost", density=True)
    ax.hist(R["v"][R["y"] == 1], bins=40, range=(0, 1), color=PAL[1], alpha=0.7, label="Heart killed", density=True)
    ax.set_xlabel("critic value V"); ax.set_ylabel("density of decisions"); ax.set_title("V distribution by game outcome"); ax.legend()
    fig.suptitle(f"Iteration {IT}: critic diagnostics from the stored trajectories (V of the behaviour net vs the game's outcome)",
                 x=0.01, ha="left", fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94)); fig.savefig(os.path.join(OUT, "L2_critic.png"), dpi=160); plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))
    ax = axes[0]
    ax.hist(a[policy & ~kill], bins=60, range=(-1, 1), color=PAL[0], alpha=0.75, label=f"lost games ({int((~kill[policy]).sum()):,} decisions)")
    ax.hist(a[policy & kill], bins=60, range=(-1, 1), color=PAL[1], alpha=0.75, label=f"Heart kills ({int(kill[policy].sum()):,} decisions)")
    ax.set_yscale("log"); ax.set_xlabel("GAE advantage (γ 1, λ 0.97, reward 1{Heart}), before normalisation"); ax.set_ylabel("decisions (log)")
    ax.set_title(f"Advantages: {mass_kill*100:.0f}% of |A| mass comes from the {int(heart.sum())} kill games"); ax.legend()
    ax = axes[1]
    acts = [1, 2, 3, 4]
    ax.bar(np.arange(4) - 0.2, [ap[R["act"][policy] == x].std() for x in acts], 0.38, color=PAL[0], label="sd of A")
    ax.bar(np.arange(4) + 0.2, [np.abs(ap[R["act"][policy] == x]).mean() for x in acts], 0.38, color=PAL[2], label="mean |A|")
    ax.set_xticks(range(4)); ax.set_xticklabels([f"act {x}\n(n={int((R['act'][policy]==x).sum()):,})" for x in acts])
    ax.set_title(f"Advantage scale by act (ICC {icc:.2f}, effective sample {N/deff:,.0f} of {N:,})"); ax.legend()
    ax = axes[2]
    names = [k for k in per if per[k]["policy"] > 50]
    xs = np.arange(len(names))
    ax.bar(xs - 0.2, [per[k]["entropy"] for k in names], 0.38, color=PAL[0], label="mean entropy of the choice distribution")
    ax.bar(xs + 0.2, [per[k]["pmax"] for k in names], 0.38, color=PAL[3], label="mean max-probability")
    for i, k in enumerate(names):
        ax.text(i, -0.08, f'{per[k]["policy"]:,}', ha="center", fontsize=7.5, color=INK2)
    ax.set_xticks(xs); ax.set_xticklabels(names, rotation=20); ax.set_ylim(-0.12, 1.05)
    ax.set_title("Policy by screen type (n = policy decisions)"); ax.legend(loc="upper right")
    fig.suptitle(f"Iteration {IT}: where the learning signal is and how decisive the policy is per screen",
                 x=0.01, ha="left", fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94)); fig.savefig(os.path.join(OUT, "L3_advantage_policy.png"), dpi=160); plt.close(fig)


def main(argv=None):
    global L, TRAJ, OUT, IT
    ap = argparse.ArgumentParser(prog="longb_diag.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", required=True, help="the learner's arm directory (loop.json, parts/)")
    ap.add_argument("--iteration", type=int, required=True, help="iteration whose stored parts are analysed")
    ap.add_argument("--traj-dir", help="directory of traj-NNNN-pK.jsonl.gz (default RUN/parts)")
    ap.add_argument("--out", required=True, help="output directory (figures, summary.json, itNNNN_rows.json)")
    a = ap.parse_args(argv)
    L, IT, OUT = a.run, a.iteration, a.out
    TRAJ = a.traj_dir or os.path.join(L, "parts")
    o, r = os.path.abspath(OUT), os.path.abspath(L)
    if o == r or o.startswith(r + os.sep):
        sys.exit("--out must not be inside --run (the run directory is read only)")
    os.makedirs(OUT, exist_ok=True)
    history()
    trajectories()
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
