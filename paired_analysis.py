#!/usr/bin/env python3
"""Paired benchmark analysis with bootstrap confidence intervals."""
import sys, math, random
import numpy as np

def load(path):
    expected = "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec".split(",")
    rows = []
    with open(path) as f:
        h = f.readline().strip().split(",")
        if sorted(h) != sorted(expected):
            raise ValueError(
                f"{path}: header {h} does not match the bestbench schema "
                f"({expected}); producer and consumer have drifted")
        cols = dict(zip(h, range(len(h))))
        for line in f:
            s = line.strip().split(",")
            rows.append({
                "seed": int(s[cols["seed"]]), "won": int(s[cols["won"]]),
                "floor": int(s[cols["floor"]]), "hp": int(s[cols["hpEnd"]]),
                "sec": float(s[cols["sec"]]),
            })
    return rows, h

def bootstrap_ci(data, n_boot=10000, ci=0.95):
    n = len(data)
    means = [np.mean(np.random.choice(data, n, replace=True)) for _ in range(n_boot)]
    lo = np.percentile(means, (1-ci)/2*100)
    hi = np.percentile(means, (1+ci)/2*100)
    return np.mean(data), lo, hi

def paired_report(a_path, b_path, label_a="A", label_b="B"):
    a_rows, _ = load(a_path)
    b_rows, _ = load(b_path)
    # Align by seed
    a_map = {r["seed"]: r for r in a_rows}
    b_map = {r["seed"]: r for r in b_rows}
    seeds = sorted(set(a_map) & set(b_map))
    if len(seeds) < len(a_rows) or len(seeds) < len(b_rows):
        print(f"WARNING: only {len(seeds)} paired seeds")
    
    a_win = [a_map[s]["won"] for s in seeds]
    b_win = [b_map[s]["won"] for s in seeds]
    a_flr = [a_map[s]["floor"] for s in seeds]
    b_flr = [b_map[s]["floor"] for s in seeds]
    a_hp  = [a_map[s]["hp"] for s in seeds]
    b_hp  = [b_map[s]["hp"] for s in seeds]
    a_sec = [a_map[s]["sec"] for s in seeds]
    b_sec = [b_map[s]["sec"] for s in seeds]

    n = len(seeds)
    a_wins = sum(a_win)
    b_wins = sum(b_win)

    # Discordant pairs
    both = sum(1 for i in range(n) if a_win[i] and b_win[i])
    neither = sum(1 for i in range(n) if not a_win[i] and not b_win[i])
    a_only = sum(1 for i in range(n) if a_win[i] and not b_win[i])
    b_only = sum(1 for i in range(n) if not a_win[i] and b_win[i])
    disc = a_only + b_only

    print(f"=== Paired comparison ({n} seeds) ===")
    print(f"{'Metric':<25} {label_a:>10} {label_b:>10} {'Delta':>10}")
    print(f"{'Win rate':<25} {a_wins/n*100:>9.1f}% {b_wins/n*100:>9.1f}% {(b_wins-a_wins)/n*100:>+9.1f}pp")
    
    # Bootstrap CI on win rate difference
    diffs = np.array(b_win) - np.array(a_win)
    mean_diff, lo_diff, hi_diff = bootstrap_ci(diffs)
    print(f"  Win diff 95% CI: [{lo_diff*100:+.1f}pp, {hi_diff*100:+.1f}pp]")
    
    floor_diffs = np.array(b_flr) - np.array(a_flr)
    mean_fd, lo_fd, hi_fd = bootstrap_ci(floor_diffs)
    print(f"{'Avg floor':<25} {np.mean(a_flr):>9.1f} {np.mean(b_flr):>9.1f} {mean_fd:>+9.1f}")
    print(f"  Floor diff 95% CI: [{lo_fd:+.1f}, {hi_fd:+.1f}]")
    
    hp_diffs = np.array(b_hp) - np.array(a_hp)
    mean_hd, lo_hd, hi_hd = bootstrap_ci(hp_diffs)
    print(f"{'Avg HP end':<25} {np.mean(a_hp):>9.1f} {np.mean(b_hp):>9.1f} {mean_hd:>+9.1f}")
    
    mean_sa, _, _ = bootstrap_ci(a_sec)
    mean_sb, _, _ = bootstrap_ci(b_sec)
    print(f"{'Avg sec/run':<25} {mean_sa:>9.2f} {mean_sb:>9.2f} {mean_sb-mean_sa:>+9.2f}")
    
    print(f"  Discordant: {disc}/{n} ({disc/n*100:.0f}%)")
    print(f"  Both win: {both}, both lose: {neither}, {label_a}-only: {a_only}, {label_b}-only: {b_only}")
    
    # Wilson CI for each proportion
    for name, w in [(label_a, a_wins), (label_b, b_wins)]:
        p = w/n
        z = 1.96
        denom = 1 + z**2/n
        centre = (p + z**2/(2*n)) / denom
        margin = z * math.sqrt(p*(1-p)/n + z**2/(4*n**2)) / denom
        print(f"  {name} Wilson 95% CI: [{max(0,centre-margin)*100:.1f}%, {min(1,centre+margin)*100:.1f}%]")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: paired_analysis.py FILE_A FILE_B [label_a] [label_b]")
        sys.exit(1)
    paired_report(sys.argv[1], sys.argv[2],
                  sys.argv[3] if len(sys.argv) > 3 else "A",
                  sys.argv[4] if len(sys.argv) > 4 else "B")
