#!/usr/bin/env python3
"""Paired benchmark analysis with deterministic bootstrap confidence intervals.

Strict by default: pairing is by seed (never row order), every seed must appear
exactly once in each CSV, and the two files must contain the identical seed
set. Duplicate seeds, unequal seed sets, or schema drift fail loudly. The
`--allow-partial` flag is an explicit opt-in for diagnostic workflows only and
must never be used for a promotion gate.

Bootstrap confidence intervals use one fixed-seed NumPy generator per report,
so repeated analysis of the same inputs produces identical intervals.
"""
import sys, math, tempfile, os
import numpy as np

# Fixed seed for the per-report bootstrap generator: repeated analysis of the
# same inputs must produce identical confidence intervals.
BOOTSTRAP_SEED = 20260807
# Synthetic seed column values used by the self-test (kept far from any real
# bestbench seed block so test rows can never be confused with recorded data).
_SELFTEST_SEEDS = [900001, 900002, 900003]

EXPECTED = "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec".split(",")

def load(path):
    """Parse a bestbench CSV, rejecting schema drift and duplicate seeds."""
    rows = []
    try:
        f = open(path)
    except OSError as e:
        raise ValueError(f"{path}: cannot open ({e})")
    with f:
        h = f.readline().strip().split(",")
        if sorted(h) != sorted(EXPECTED):
            raise ValueError(
                f"{path}: header {h} does not match the bestbench schema "
                f"({EXPECTED}); producer and consumer have drifted")
        cols = dict(zip(h, range(len(h))))
        for ln, line in enumerate(f, start=2):
            line = line.strip()
            if not line:
                continue  # tolerate a trailing newline only; empty rows are not rows
            s = line.split(",")
            if len(s) != len(EXPECTED):
                raise ValueError(
                    f"{path}: row {ln} has {len(s)} columns, expected "
                    f"{len(EXPECTED)}; malformed appended CSV can be analyzed "
                    f"as a valid pair only if this check is bypassed")
            rows.append({
                "seed": int(s[cols["seed"]]), "won": int(s[cols["won"]]),
                "floor": int(s[cols["floor"]]), "hp": int(s[cols["hpEnd"]]),
                "sec": float(s[cols["sec"]]),
            })
    seeds = [r["seed"] for r in rows]
    if len(set(seeds)) != len(seeds):
        dupes = sorted({s for s in seeds if seeds.count(s) > 1})
        raise ValueError(
            f"{path}: duplicate seeds {dupes}; pairing requires exactly one "
            f"row per seed")
    return rows, h

def bootstrap_ci(data, n_boot=10000, ci=0.95, rng=None):
    """Bootstrap 95% CI over the mean of `data` using a caller-supplied
    fixed-seed generator (deterministic across repeated runs)."""
    if rng is None:
        rng = np.random.default_rng(BOOTSTRAP_SEED)
    n = len(data)
    arr = np.asarray(data)
    means = np.empty(n_boot)
    for i in range(n_boot):
        means[i] = arr[rng.integers(0, n, n)].mean()
    lo = np.percentile(means, (1 - ci) / 2 * 100)
    hi = np.percentile(means, (1 + ci) / 2 * 100)
    return float(arr.mean()), float(lo), float(hi)

def paired_report(a_path, b_path, label_a="A", label_b="B", allow_partial=False):
    a_rows, _ = load(a_path)
    b_rows, _ = load(b_path)
    # Pairing is by seed, never by row order.
    a_map = {r["seed"]: r for r in a_rows}
    b_map = {r["seed"]: r for r in b_rows}
    if set(a_map) != set(b_map):
        only_a = sorted(set(a_map) - set(b_map))
        only_b = sorted(set(b_map) - set(a_map))
        msg = (f"seed sets differ: {len(only_a)} seeds only in {a_path} "
               f"({only_a[:5]}{'...' if len(only_a) > 5 else ''}), "
               f"{len(only_b)} seeds only in {b_path} "
               f"({only_b[:5]}{'...' if len(only_b) > 5 else ''})")
        if not allow_partial:
            raise ValueError(
                f"{msg}; a normal policy gate requires identical seed sets. "
                f"Use --allow-partial for diagnostics only (never a promotion "
                f"gate)")
        print("WARNING: --allow-partial: comparing on the INTERSECTION of "
              f"unequal seed sets ({msg}). Diagnostic use only; this is NOT a "
              "valid promotion gate.")
        seeds = sorted(set(a_map) & set(b_map))
    else:
        seeds = sorted(a_map)
    # load() already guarantees exactly one row per seed per file, so every
    # seed in the paired set has exactly one row on each side; no extra guard
    # is needed here.

    rng = np.random.default_rng(BOOTSTRAP_SEED)  # one fixed-seed generator per report

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
    mean_diff, lo_diff, hi_diff = bootstrap_ci(diffs, rng=rng)
    print(f"  Win diff 95% CI: [{lo_diff*100:+.1f}pp, {hi_diff*100:+.1f}pp]")

    floor_diffs = np.array(b_flr) - np.array(a_flr)
    mean_fd, lo_fd, hi_fd = bootstrap_ci(floor_diffs, rng=rng)
    print(f"{'Avg floor':<25} {np.mean(a_flr):>9.1f} {np.mean(b_flr):>9.1f} {mean_fd:>+9.1f}")
    print(f"  Floor diff 95% CI: [{lo_fd:+.1f}, {hi_fd:+.1f}]")

    hp_diffs = np.array(b_hp) - np.array(a_hp)
    mean_hd, lo_hd, hi_hd = bootstrap_ci(hp_diffs, rng=rng)
    print(f"{'Avg HP end':<25} {np.mean(a_hp):>9.1f} {np.mean(b_hp):>9.1f} {mean_hd:>+9.1f}")

    mean_sa, _, _ = bootstrap_ci(a_sec, rng=rng)
    mean_sb, _, _ = bootstrap_ci(b_sec, rng=rng)
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


def _write_csv(path, rows):
    with open(path, "w") as f:
        f.write(",".join(EXPECTED) + "\n")
        for r in rows:
            f.write(f"{r['seed']},{r['won']},{r['floor']},1,"
                    f"{r['hp']},80,0,0,0,{r['sec']}\n")


def paired_analysis_selftest():
    """Exercise the strict analyzer: deterministic intervals, reordered rows,
    duplicate rejection, mismatched-set rejection, and the opt-in partial path.
    Returns 0 on success, nonzero on failure."""
    failures = []

    def check(name, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            failures.append(name)

    # ---- fixtures: two identical 3-seed CSVs with a known B advantage ----
    base_a = [{"seed": s, "won": 0, "floor": 20, "hp": 30, "sec": 1.0}
              for s in _SELFTEST_SEEDS]
    base_b = [{"seed": s, "won": 1, "floor": 33, "hp": 45, "sec": 2.0}
              for s in _SELFTEST_SEEDS]
    with tempfile.TemporaryDirectory() as td:
        pa = os.path.join(td, "a.csv")
        pb = os.path.join(td, "b.csv")
        _write_csv(pa, base_a)
        _write_csv(pb, base_b)

        import io, contextlib
        def run_report(*args, **kwargs):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                paired_report(*args, **kwargs)
            return buf.getvalue()

        # 1. deterministic intervals: two runs give identical output
        out1 = run_report(pa, pb, "A", "B")
        out2 = run_report(pa, pb, "A", "B")
        check("deterministic intervals across repeated runs", out1 == out2)
        check("bootstrap CI equals the exact mean for constant diffs",
              "Win diff 95% CI: [+100.0pp, +100.0pp]" in out1)

        # 2. reordered rows: shuffle B's rows, output identical
        import random as _rnd
        _rnd.seed(7)
        shuffled = base_b[:]
        _rnd.shuffle(shuffled)
        _write_csv(pb, shuffled)
        out3 = run_report(pa, pb, "A", "B")
        check("reordered rows give identical analysis", out1 == out3)
        _write_csv(pb, base_b)

        # 3. duplicate-seed rejection in either file
        dup = base_a + [dict(base_a[0])]
        pd_ = os.path.join(td, "dup.csv")
        _write_csv(pd_, dup)
        try:
            run_report(pa, pd_, "A", "B")
            check("duplicate seeds rejected", False)
        except ValueError:
            check("duplicate seeds rejected", True)
        pd2 = os.path.join(td, "dup2.csv")
        _write_csv(pd2, dup)
        try:
            run_report(pd2, pb, "A", "B")
            check("duplicate seeds rejected (either side)", False)
        except ValueError:
            check("duplicate seeds rejected (either side)", True)

        # 4. mismatched seed sets rejected by default
        miss = base_b[:-1]
        pm = os.path.join(td, "miss.csv")
        _write_csv(pm, miss)
        try:
            run_report(pa, pm, "A", "B")
            check("mismatched seed sets rejected by default", False)
        except ValueError:
            check("mismatched seed sets rejected by default", True)

        # 5. opt-in partial path: works, warns, and analyzes the intersection
        out4 = run_report(pa, pm, "A", "B", allow_partial=True)
        check("--allow-partial path runs on the intersection",
              "Paired comparison (2 seeds)" in out4 and "WARNING: --allow-partial" in out4)

        # 6. ten-column schema drift still rejected
        badhdr = os.path.join(td, "badhdr.csv")
        with open(badhdr, "w") as f:
            f.write("seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter\n")
        try:
            run_report(badhdr, pb, "A", "B")
            check("schema drift rejected", False)
        except ValueError:
            check("schema drift rejected", True)

        # 7. malformed rows (wrong column count) rejected
        badrow = os.path.join(td, "badrow.csv")
        with open(badrow, "w") as f:
            f.write(",".join(EXPECTED) + "\n")
            f.write("1,0,20,1,30,80,0,0,0\n")   # 9 columns
        try:
            run_report(badrow, pb, "A", "B")
            check("malformed row rejected", False)
        except ValueError:
            check("malformed row rejected", True)

    if failures:
        print(f"paired_analysis self-test: {len(failures)} FAILURE(S): {failures}")
        return 1
    print("paired_analysis self-test: all checks passed")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--self-test" in sys.argv:
        sys.exit(paired_analysis_selftest())
    allow_partial = "--allow-partial" in sys.argv
    if len(args) < 2:
        print("usage: paired_analysis.py FILE_A FILE_B [label_a] [label_b] "
              "[--allow-partial] [--self-test]")
        sys.exit(1)
    paired_report(args[0], args[1],
                  args[2] if len(args) > 2 else "A",
                  args[3] if len(args) > 3 else "B",
                  allow_partial=allow_partial)
