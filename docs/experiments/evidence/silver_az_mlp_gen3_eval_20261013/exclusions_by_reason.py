"""Descriptive §460 helper: break invalid-fight exclusions down by quarantineReason (not part of the frozen analyzer)."""
import csv, glob, os, sys, collections
reasons = collections.Counter(); bad = {}
for d in sys.argv[1:]:
    for p in glob.glob(os.path.join(d, "**", "*.arms.csv"), recursive=True):
        for r in csv.DictReader(open(p)):
            if r["valid"] != "1":
                bad.setdefault(r["stateId"], set()).add(r["quarantineReason"] or ("control_mismatch" if r["controlReplayMatch"] != "1" else "unknown"))
for sid, rs in bad.items():
    reasons["+".join(sorted(rs))] += 1
print(dict(reasons), "fights:", len(bad))
