"""Recompute PPO screen diagnostics from the evidence bundles (loop.json + games-*.csv) and plot them.

PPO diagnostics findings 2026-11-05 (secondary outcomes of screens §748, §751, §754): paired arm - control on each
screen's pre-registered window for Heart, Act 2/3/4 reached and mean final floor (95% seed bootstrap), learner-stat
means per arm, replica noise, entropy vs survival across arms, 11 figures, summary.json and summary.md.

    python3 tools/heart1/ppo_diag.py --data DIR --out OUT_DIR

DIR holds the unpacked screen bundles as DIR/s1res, DIR/s2res, DIR/archres (one sub-directory per arm with loop.json
and games-*.csv; s1res.tgz and s2res.tgz unpack with their top directory, archres.tgz without: unpack it inside
DIR/archres). The bundles are docs/experiments/evidence/ppo_recipe_screen_20261101/s1res.tgz,
ppo_reward_screen_20261103/s2res.tgz and ppo_arch_screen_20261102/archres.tgz. Needs numpy and matplotlib.
"""
import argparse
import csv
import glob
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

D = OUT = S = None   # set by main(): bundle directory, figure directory, table directory (= OUT)

PAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, INK3, SURF, GRID = "#0b0b0b", "#52514e", "#8a8984", "#fcfcfb", "#e6e5e1"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.titlesize": 10.5, "axes.titleweight": "semibold", "axes.titlelocation": "left",
    "font.size": 9, "legend.frameon": False, "legend.fontsize": 8.5, "lines.linewidth": 1.6,
    "xtick.major.size": 0, "ytick.major.size": 0, "font.family": "DejaVu Sans",
})

SCREENS = {
    "screen1": {"dir": "s1res", "title": "Screen 1: recipe (19 one-change arms, 30 updates)", "control": ["BASE"],
                "window": (20, 30), "games": 512},
    "screen2": {"dir": "s2res", "title": "Screen 2: reward / learning signal (6 arms, 60 updates)",
                "control": ["BASE", "BASE_S1"], "window": (40, 60), "games": 512},
    "arch": {"dir": "archres", "title": "Architecture screen (5 arms forked from screen-2 BASE after update 30)",
             "control": ["BASE"], "window": (40, 60), "games": 512},
}


def load_screen(key):
    sc = SCREENS[key]
    root = os.path.join(D, sc["dir"])
    arms = {}
    for arm in sorted(os.listdir(root)):
        p = os.path.join(root, arm)
        if not os.path.isdir(p) or not os.path.exists(os.path.join(p, "loop.json")):
            continue
        stats = json.load(open(os.path.join(p, "loop.json")))["iterations"]
        games = {}
        for f in sorted(glob.glob(os.path.join(p, "games-*.csv"))):
            for r in csv.DictReader(open(f)):
                games[int(r["seed"])] = (int(r["iteration"]), int(r["heart_kill"]), int(r["floor"]))
        arms[arm] = {"stats": stats, "games": games}
    return arms


def metric_vec(games, seeds, m):
    v = np.array([games[s][2] for s in seeds], dtype=float)
    hk = np.array([games[s][1] for s in seeds], dtype=float)
    return {"heart": hk, "act4": (v >= 51).astype(float), "act3": (v >= 34).astype(float),
            "act2": (v >= 17).astype(float), "floor": v}[m]


def boot_ci(d, seed=20261103, n=4000):
    rng = np.random.default_rng(seed)
    i = rng.integers(0, len(d), size=(n, len(d)))
    bs = d[i].mean(1)
    return float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


MLABEL = {"heart": "Heart kill (pp)", "act4": "Act 4 reached (pp)", "act3": "Act 3 reached (pp)",
          "act2": "Act 2 reached (pp)", "floor": "mean final floor"}


def paired_table(key, arms):
    """Per arm: D vs control on the primary window for several outcomes (seed bootstrap)."""
    sc = SCREENS[key]
    lo, hi = sc["window"]
    ctrl = sc["control"]
    rows = []
    for arm in arms:
        if arm in ctrl and len(ctrl) > 1:
            continue
        if arm == ctrl[0]:
            continue
        seeds = sorted(s for s, (it, _, _) in arms[arm]["games"].items() if lo <= it < hi
                       and all(s in arms[c]["games"] for c in ctrl))
        if len(seeds) < 1000:
            continue
        row = {"arm": arm, "n": len(seeds)}
        for m in ("heart", "act4", "act3", "act2", "floor"):
            a = metric_vec(arms[arm]["games"], seeds, m)
            c = np.mean([metric_vec(arms[cc]["games"], seeds, m) for cc in ctrl], axis=0)
            d = a - c
            scale = 1.0 if m == "floor" else 100.0
            lo_, hi_ = boot_ci(d)
            row[m] = (d.mean() * scale, lo_ * scale, hi_ * scale, d.std(ddof=1) * scale)
        rows.append(row)
    return rows


def fig_learner(key, arms, names, fname, ncol=3):
    sc = SCREENS[key]
    mets = [("approx_kl", "approx KL per update"), ("clipfrac", "clip fraction"), ("entropy", "policy entropy"),
            ("value", "value loss (½ MSE vs λ-return)"), ("gap", "mean value − mean λ-return"),
            ("first_mb_approx_kl", "KL behaviour → learner, first minibatch")]
    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    for ax, (m, title) in zip(axes.flat, mets):
        for k, arm in enumerate(names):
            st = [r for r in arms[arm]["stats"] if not r["value_only"]]
            x = [r["iteration"] for r in st]
            y = [r["mean_value"] - r["mean_return"] if m == "gap" else r.get(m, np.nan) for r in st]
            ax.plot(x, y, color=PAL[k % 8], label=arm, alpha=0.95 if k < 3 else 0.8)
        ax.set_title(title)
        ax.set_xlabel("update")
        if m == "gap":
            ax.axhline(0, color=INK3, lw=0.8)
        if m == "first_mb_approx_kl":
            ax.set_ylim(0, 0.08)
    axes[0, 0].legend(ncol=ncol, loc="upper left", bbox_to_anchor=(0, 1.0))
    fig.suptitle(sc["title"] + " — learner statistics per update", x=0.01, ha="left", fontsize=12, weight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(os.path.join(OUT, fname), dpi=160)
    plt.close(fig)


def fig_heart_noise(arms, fname):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2), sharey=True)
    for ax, arm, col in zip(axes, ("BASE", "CRIT_PRE"), (PAL[0], PAL[2])):
        st = arms[arm]["stats"]
        x = np.array([r["iteration"] for r in st]); y = np.array([r["heart_rate"] for r in st]) * 100
        p = y.mean() / 100
        se = 100 * np.sqrt(p * (1 - p) / 512)
        ax.axhspan(y.mean() - 1.96 * se, y.mean() + 1.96 * se, color=col, alpha=0.10, lw=0)
        ax.axhline(y.mean(), color=col, lw=0.8, ls="--")
        ax.plot(x, y, color=col, lw=1.2, alpha=0.9, marker="o", ms=3)
        for b in range(0, 60, 10):
            yb = y[(x > b) & (x <= b + 10)].mean()
            ax.plot([b + 1, b + 10], [yb, yb], color=INK, lw=2.2)
        ax.set_title(f"{arm}: sd across updates {y.std():.2f} pp, binomial sd at 512 games {se:.2f} pp")
        ax.set_xlabel("update"); ax.set_ylabel("Heart kills, % of 512 games")
        ax.text(1, 1.5, "band: ±1.96 binomial sd around the run mean; black: 10-update block means", color=INK2, fontsize=8)
    fig.suptitle("Screen 2: the per-update Heart curve is binomial noise", x=0.01, ha="left", fontsize=12, weight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(os.path.join(OUT, fname), dpi=160); plt.close(fig)


def fig_outcomes(key, arms, names, fname):
    sc = SCREENS[key]
    mets = [("heart", "Heart kill %"), ("act4", "Act 4 reached % (floor ≥ 51)"), ("act3", "Act 3 reached % (floor ≥ 34)"),
            ("act2", "Act 2 reached % (floor ≥ 17)")]
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.9))
    for ax, (m, title) in zip(axes, mets):
        for k, arm in enumerate(names):
            g = arms[arm]["games"]
            its = sorted({it for it, _, _ in g.values()})
            blocks = sorted({it // 10 for it in its})
            xs, ys = [], []
            for b in blocks:
                seeds = [s for s, (it, _, _) in g.items() if it // 10 == b]
                if len(seeds) < 2000:
                    continue
                xs.append(b * 10 + 5); ys.append(metric_vec(g, seeds, m).mean() * 100)
            ax.plot(xs, ys, color=PAL[k % 8], marker="o", ms=3.5, label=arm)
        ax.set_title(title); ax.set_xlabel("update (10-update blocks)")
    axes[0].legend(ncol=2, fontsize=8)
    fig.suptitle(sc["title"] + " — outcome decomposition per block (in-sample, sampled play)", x=0.01, ha="left",
                 fontsize=12, weight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(os.path.join(OUT, fname), dpi=160); plt.close(fig)


def fig_forest(key, rows, fname, noise=None):
    sc = SCREENS[key]
    mets = ["heart", "act4", "act3", "floor"]
    rows = sorted(rows, key=lambda r: -r["heart"][0])
    fig, axes = plt.subplots(1, 4, figsize=(15, 0.42 * len(rows) + 1.9), sharey=True)
    ylab = [f'{r["arm"]}' for r in rows]
    for ax, m in zip(axes, mets):
        for i, r in enumerate(rows):
            d, lo, hi, _ = r[m]
            col = PAL[0] if lo > 0 else (PAL[7] if hi < 0 else INK3)
            ax.plot([lo, hi], [i, i], color=col, lw=1.6)
            ax.plot([d], [i], "o", color=col, ms=5)
        ax.axvline(0, color=INK2, lw=0.8)
        if noise is not None and m == "heart":
            ax.axvspan(-noise, noise, color=PAL[3], alpha=0.12, lw=0)
            ax.text(noise, -0.9, f"run noise ±{noise:.2f}", color=INK2, fontsize=7.5)
        ax.set_title(f"Δ vs control: {MLABEL[m]}")
        ax.set_yticks(range(len(rows))); ax.set_yticklabels(ylab)
        ax.invert_yaxis()
    fig.suptitle(sc["title"] + f" — paired window {sc['window'][0]}–{sc['window'][1]-1}, 95% seed bootstrap",
                 x=0.01, ha="left", fontsize=12, weight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(os.path.join(OUT, fname), dpi=160); plt.close(fig)


def fig_power(rows2, fname):
    """CI half-width vs paired games from the empirical paired sd (screen 2, CRIT_PRE vs control)."""
    r = [x for x in rows2 if x["arm"] == "CRIT_PRE"][0]
    n = np.logspace(3, 5.3, 100)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2))
    for k, m in enumerate(("heart", "act4", "act3")):
        sd = r[m][3]
        axes[0].plot(n, 1.96 * sd / np.sqrt(n), color=PAL[k], label=f"{MLABEL[m].replace(' (pp)','')}  (paired sd {sd:.1f} pp)")
    axes[0].set_xscale("log"); axes[0].set_xlabel("paired games in the comparison window"); axes[0].set_ylabel("95% CI half-width, pp")
    axes[0].axvline(10240, color=INK3, lw=0.8, ls="--"); axes[0].text(10500, 2.3, "screen-2 window (10,240)", color=INK2, fontsize=8)
    axes[0].axhline(0.5, color=INK3, lw=0.8, ls=":"); axes[0].text(1100, 0.55, "0.5 pp", color=INK2, fontsize=8)
    axes[0].set_title("Half-width of the paired 95% CI vs window size"); axes[0].legend()
    sd = r["floor"][3]
    axes[1].plot(n, 1.96 * sd / np.sqrt(n), color=PAL[6], label=f"mean final floor (paired sd {sd:.1f} floors)")
    axes[1].set_xscale("log"); axes[1].set_xlabel("paired games"); axes[1].set_ylabel("95% CI half-width, floors")
    axes[1].axvline(10240, color=INK3, lw=0.8, ls="--"); axes[1].set_title("Same for the mean final floor"); axes[1].legend()
    fig.suptitle("How many paired games a window needs (empirical per-seed sd of arm − control, screen 2 CRIT_PRE)",
                 x=0.01, ha="left", fontsize=12, weight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(os.path.join(OUT, fname), dpi=160); plt.close(fig)


def fig_staleness(arms, fname):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.4))
    ax = axes[0]
    for k, arm in enumerate(arms):
        st = [r for r in arms[arm]["stats"] if not r["value_only"] and r["iteration"] > 4]
        ax.scatter([r["approx_kl"] for r in st], [r["first_mb_approx_kl"] for r in st], s=14, color=PAL[k % 8],
                   alpha=0.75, label=arm, edgecolor=SURF, linewidth=0.5)
    lim = 0.08
    ax.plot([0, lim], [0, lim], color=INK3, lw=0.8, ls="--"); ax.text(0.0135, 0.0145, "y = x", color=INK2, fontsize=8)
    ax.set_xlim(0.008, 0.016); ax.set_ylim(0, lim)
    ax.set_xlabel("approx KL of the whole update (mean over minibatches)")
    ax.set_ylabel("approx KL on the first minibatch, before any step")
    ax.set_title("KL(behaviour net → learner) at update start vs the update's own KL")
    ax.legend(ncol=1, fontsize=8, loc="upper right")
    ax = axes[1]
    for k, arm in enumerate(arms):
        st = [r for r in arms[arm]["stats"] if not r["value_only"]]
        ax.plot([r["iteration"] for r in st], [r["max_dlogp_behaviour"] for r in st], color=PAL[k % 8], label=arm)
    ax.set_yscale("log"); ax.set_xlabel("update"); ax.set_ylabel("max |log-prob(learner) − log-prob(behaviour)|")
    ax.set_title("Max per-decision log-prob gap to the behaviour net (0.09 = bf16 noise, > 1 = stale net)")
    fig.suptitle("Screen 2: what pipeline 1 costs — the learner starts each update already off-policy",
                 x=0.01, ha="left", fontsize=12, weight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(os.path.join(OUT, fname), dpi=160); plt.close(fig)


def fig_families(arms, fname):
    fam = [("learning rate", ["LR_3E6", "BASE", "LR_3E5"]), ("entropy coef", ["ENT_0007", "BASE", "ENT_01"]),
           ("KL anchor", ["BASE", "KL_01", "KL_1", "KL_DEC"]), ("epochs", ["EP_1", "BASE", "EP_4"]),
           ("clip / λ", ["BASE", "CLIP_01", "LAM_1"]), ("games/upd, minibatch", ["BASE", "G_256", "G_1024", "MB_512"])]
    mets = [("approx_kl", "approx KL"), ("entropy", "entropy"), ("clipfrac", "clip fraction"), ("value", "value loss")]
    fig, axes = plt.subplots(len(mets), len(fam), figsize=(17, 9.5), sharex="col")
    for j, (fname_, names) in enumerate(fam):
        for i, (m, mt) in enumerate(mets):
            ax = axes[i, j]
            for k, arm in enumerate(names):
                if arm not in arms:
                    continue
                st = [r for r in arms[arm]["stats"] if not r["value_only"]]
                col = INK2 if arm == "BASE" else PAL[(k + (1 if names.index("BASE") > k else 0)) % 8]
                ax.plot([r["iteration"] for r in st], [r.get(m, np.nan) for r in st], color=col, label=arm,
                        lw=2.0 if arm == "BASE" else 1.5)
            if i == 0:
                ax.set_title(fname_)
                ax.legend(fontsize=7.5)
            if j == 0:
                ax.set_ylabel(mt)
            if i == len(mets) - 1:
                ax.set_xlabel("update")
    fig.suptitle("Screen 1: how each recipe knob moved the learner statistics (BASE in grey; no arm moved the Heart rate)",
                 x=0.01, ha="left", fontsize=12, weight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(os.path.join(OUT, fname), dpi=160); plt.close(fig)


def fig_entropy_survival(summary, fname):
    """Per arm: policy entropy at the end of the window vs paired Δ Act 2 reached and Δ Heart."""
    pts = []
    for key, mk in (("screen1", "o"), ("screen2", "s"), ("arch", "^")):
        for arm, r in summary[key + "_paired"].items():
            ent = summary[key + "_learner"][arm]["entropy_last"]
            pts.append((key, mk, arm, ent, r["act2"][0], r["act2"][1], r["act2"][2], r["heart"][0]))
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, (yi, ylab) in zip(axes, ((4, "Δ Act 2 reached vs control, pp (95% CI)"), (7, "Δ Heart kill vs control, pp"))):
        for key, mk, col in (("screen1", "o", PAL[0]), ("screen2", "s", PAL[1]), ("arch", "^", PAL[2])):
            sel = [p for p in pts if p[0] == key]
            if yi == 4:
                for p in sel:
                    ax.plot([p[3], p[3]], [p[5], p[6]], color=col, lw=0.9, alpha=0.6)
            ax.scatter([p[3] for p in sel], [p[yi] for p in sel], marker=mk, s=42, color=col, label=key,
                       edgecolor=SURF, linewidth=0.6, zorder=3)
            for p in sel:
                if abs(p[yi]) > 1.2 or p[3] > 0.26 or p[3] < 0.2:
                    ax.annotate(p[2], (p[3], p[yi]), xytext=(4, 3), textcoords="offset points", fontsize=7.5, color=INK2)
        ax.axhline(0, color=INK2, lw=0.8)
        ax.set_xlabel("policy entropy at the last update of the arm"); ax.set_ylabel(ylab)
        x = np.array([p[3] for p in pts]); y = np.array([p[yi] for p in pts])
        ax.set_title(f"{ylab.split(' vs')[0]}  (Pearson r = {np.corrcoef(x, y)[0, 1]:+.2f}, {len(pts)} arms)")
    axes[0].legend(title="screen", fontsize=8)
    fig.suptitle(f"Across all {len(pts)} arm-vs-control comparisons: does a policy that got less decisive also die earlier?", x=0.01, ha="left",
                 fontsize=12, weight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(os.path.join(OUT, fname), dpi=160); plt.close(fig)


def write_tables(summary):
    L = ["# PPO screens: recomputed numbers\n",
         "Source: `docs/experiments/evidence/ppo_{recipe,reward,arch}_screen_*` bundles (loop.json + games-*.csv). "
         "Paired D = arm − control on the pre-registered window, 95% seed bootstrap (4,000 resamples). "
         "Act N reached = final floor ≥ 17 / 34 / 51. Learner stats are means over policy updates.\n"]
    for key, name in (("screen1", "Screen 1 recipe, window 20–29 vs BASE"), ("screen2", "Screen 2 reward, window 40–59 vs (BASE+BASE_S1)/2"),
                      ("arch", "Architecture screen, window 40–59 vs BASE")):
        L.append(f"\n## {name}\n")
        L.append("| arm | Heart D [CI] | Act 4 D [CI] | Act 3 D [CI] | Act 2 D [CI] | floor D [CI] | n |")
        L.append("|---|---|---|---|---|---|---|")
        for arm, r in sorted(summary[key + "_paired"].items(), key=lambda kv: -kv[1]["heart"][0]):
            f = lambda m: f"{r[m][0]:+.2f} [{r[m][1]:+.2f}, {r[m][2]:+.2f}]"
            L.append(f"| {arm} | {f('heart')} | {f('act4')} | {f('act3')} | {f('act2')} | {f('floor')} | {r['n']} |")
        L.append("\n| arm | approx KL | clipfrac | entropy first→last | value loss (last 10) | value−return first / last 10 | first-mb KL | Heart sd / binomial sd (pp) | kill games per update |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for arm, r in summary[key + "_learner"].items():
            L.append(f"| {arm} | {r['approx_kl']:.4f} | {r['clipfrac']:.3f} | {r['entropy_first']:.3f}→{r['entropy_last']:.3f} | "
                     f"{r['value_loss_last10']:.4f} | {r['gap_first']:+.3f} / {r['gap_last10']:+.3f} | {r['first_mb_kl_mean']:.3f} | "
                     f"{r['heart_sd_pp']:.2f} / {r['binomial_sd_pp']:.2f} | {r['kill_games_per_update']:.0f} |")
    L.append(f"\nScreen-2 run noise |BASE_S1 − BASE| on Heart, window 40–59: {summary['screen2_run_noise_pp']:.2f} pp.\n")
    open(os.path.join(S, "summary.md"), "w").write("\n".join(L))


def main(argv=None):
    global D, OUT, S
    ap = argparse.ArgumentParser(prog="ppo_diag.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", required=True, help="directory with the unpacked bundles s1res/, s2res/, archres/")
    ap.add_argument("--out", required=True, help="output directory for figures, summary.json and summary.md")
    a = ap.parse_args(argv)
    D, OUT = a.data, a.out
    S = OUT
    os.makedirs(OUT, exist_ok=True)
    s1, s2, ar = load_screen("screen1"), load_screen("screen2"), load_screen("arch")
    summary = {}

    # Learner-stat means per arm (policy updates only) and heart-rate noise
    for key, arms in (("screen1", s1), ("screen2", s2), ("arch", ar)):
        tab = {}
        for arm, a in arms.items():
            st = [r for r in a["stats"] if not r["value_only"]]
            if key == "arch" and arm not in ("BASE", "BASE_S1", "CRIT_PRE"):
                st = [r for r in st if r["iteration"] > 30]
            hr = np.array([r["heart_rate"] for r in st])
            p = hr.mean()
            tab[arm] = {"updates": len(st), "approx_kl": float(np.mean([r["approx_kl"] for r in st])),
                        "clipfrac": float(np.mean([r["clipfrac"] for r in st])),
                        "entropy_first": st[0]["entropy"], "entropy_last": st[-1]["entropy"],
                        "value_loss_last10": float(np.mean([r["value"] for r in st[-10:]])),
                        "gap_first": st[0]["mean_value"] - st[0]["mean_return"],
                        "gap_last10": float(np.mean([r["mean_value"] - r["mean_return"] for r in st[-10:]])),
                        "first_mb_kl_mean": float(np.mean([r.get("first_mb_approx_kl", 0) for r in st if r["iteration"] > 4])),
                        "heart_sd_pp": float(hr.std() * 100), "binomial_sd_pp": float(np.sqrt(p * (1 - p) / 512) * 100),
                        "policy_decisions_per_game": float(np.mean([r["policy_decisions"] / r["games"] for r in st])),
                        "kill_games_per_update": float(p * 512),
                        "train_s": float(np.mean([r["train_s"] for r in st])), "actor_s": float(np.mean([r.get("actor_s", 0) for r in st]))}
        summary[key + "_learner"] = tab

    r1, r2, ra = paired_table("screen1", s1), paired_table("screen2", s2), paired_table("arch", ar)
    for key, rows in (("screen1", r1), ("screen2", r2), ("arch", ra)):
        summary[key + "_paired"] = {r["arm"]: {m: r[m] for m in ("heart", "act4", "act3", "act2", "floor")} | {"n": r["n"]} for r in rows}
    json.dump(summary, open(os.path.join(S, "summary.json"), "w"), indent=1)

    # Figures
    fig_learner("screen2", s2, ["BASE", "BASE_S1", "CRIT_PRE", "PBRS_FLOOR", "PBRS_STATE", "ACT_BONUS"], "01_screen2_learner.png")
    fig_heart_noise(s2, "02_screen2_heart_noise.png")
    fig_outcomes("screen2", s2, ["BASE", "BASE_S1", "CRIT_PRE", "PBRS_FLOOR", "PBRS_STATE", "ACT_BONUS"], "03_screen2_outcomes.png")
    # run noise: |BASE_S1 - BASE| in the window
    sc = SCREENS["screen2"]; lo, hi = sc["window"]
    seeds = sorted(s for s, (it, _, _) in s2["BASE"]["games"].items() if lo <= it < hi and s in s2["BASE_S1"]["games"])
    noise2 = float(abs(metric_vec(s2["BASE_S1"]["games"], seeds, "heart").mean() - metric_vec(s2["BASE"]["games"], seeds, "heart").mean()) * 100)
    summary["screen2_run_noise_pp"] = noise2
    fig_forest("screen2", r2, "04_screen2_forest.png", noise=noise2)
    fig_forest("screen1", r1, "05_screen1_forest.png", noise=abs(summary["screen1_paired"]["BASE_S1"]["heart"][0]))
    fig_forest("arch", ra, "06_arch_forest.png", noise=noise2)
    fig_power(r2, "07_power.png")
    fig_staleness(s2, "08_screen2_staleness.png")
    fig_families(s1, "09_screen1_families.png")
    fig_learner("arch", ar, ["BASE", "CRIT_PRE", "DEPTH6", "CRITIC_SEP", "AUX", "VAL_SPARSE", "IN_DECK"], "10_arch_learner.png", ncol=4)
    fig_entropy_survival(summary, "11_entropy_vs_survival.png")
    json.dump(summary, open(os.path.join(S, "summary.json"), "w"), indent=1)
    write_tables(summary)
    # BASE_S1 vs BASE replica differences on the screen-2 window (run noise per metric)
    seeds = sorted(s for s, (it, _, _) in s2["BASE"]["games"].items() if lo <= it < hi and s in s2["BASE_S1"]["games"])
    for m in ("heart", "act4", "act3", "act2", "floor"):
        d = metric_vec(s2["BASE_S1"]["games"], seeds, m) - metric_vec(s2["BASE"]["games"], seeds, m)
        sc_ = 1 if m == "floor" else 100
        print("replica BASE_S1-BASE", m, round(d.mean() * sc_, 2), [round(x * sc_, 2) for x in boot_ci(d)])
    # Act 2 reached per block for screen 2 (first vs last block)
    for arm in s2:
        g = s2[arm]["games"]
        b0 = [s for s, (it, _, _) in g.items() if it < 10]; b5 = [s for s, (it, _, _) in g.items() if it >= 50]
        print("act2 block0→block5", arm, round(metric_vec(g, b0, "act2").mean() * 100, 1), round(metric_vec(g, b5, "act2").mean() * 100, 1))


if __name__ == "__main__":
    main()
