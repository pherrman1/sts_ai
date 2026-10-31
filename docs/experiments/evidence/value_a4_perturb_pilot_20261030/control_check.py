#!/usr/bin/env python3
"""Control child vs run 1's base game (value_a4_perturb_pilot campaign, Verify).

  control_check.py UNIT_DIR RUN1_TAR...

For every unit dir UNIT_DIR/*/ with a4p-SEED.p00.jsonl.gz, finds run 1's base-SEED.jsonl.gz in the given run-1
unit tars and reports whether the rows after the header (game and outcome rows) are identical.
"""
import glob, gzip, io, json, os, sys, tarfile


def lines(fobj):
    return [l for l in io.TextIOWrapper(gzip.GzipFile(fileobj=fobj), "utf-8") if l.strip()][1:]


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    run1 = {}
    for t in argv[2:]:
        seed = os.path.basename(t).split("_")[0]
        if seed in run1:
            continue
        with tarfile.open(t) as tf:
            m = [n for n in tf.getnames() if n.endswith(f"/base-{seed}.jsonl.gz")]
            if m:
                run1[seed] = lines(tf.extractfile(m[0]))
    same = diff = missing = 0
    for p in sorted(glob.glob(os.path.join(argv[1], "**", "a4p-*.p00.jsonl.gz"), recursive=True)):
        seed = os.path.basename(p).split("-")[1].split(".")[0]
        with open(p, "rb") as f:
            c = lines(f)
        if seed not in run1:
            missing += 1; print(seed, "no run-1 base"); continue
        if c == run1[seed]:
            same += 1
        else:
            diff += 1
            i = next((i for i, (a, b) in enumerate(zip(c, run1[seed])) if a != b), min(len(c), len(run1[seed])))
            print(seed, f"differs from row {i + 1} (control {len(c)} rows, run 1 {len(run1[seed])})")
    print(json.dumps({"identical": same, "different": diff, "missing": missing}))


if __name__ == "__main__":
    main(sys.argv)
