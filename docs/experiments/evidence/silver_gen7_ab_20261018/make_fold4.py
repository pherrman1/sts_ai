"""Held-out Act-4 states for the gen-7 prior A/B: the lines of the gen-7 states file (sha c095368c) whose
source run has sourceSeed % 5 == 4 (the training pack's test fold), in file order.
usage: python3 make_fold4.py ACT4_STATES.jsonl OUT.jsonl"""
import hashlib, json, sys
src, out = sys.argv[1:3]
assert hashlib.sha256(open(src, "rb").read()).hexdigest().startswith("c095368c"), "not the gen-7 states file"
keep = [l for l in open(src) if json.loads(l)["sourceSeed"] % 5 == 4]
open(out, "w").writelines(keep)
print(len(keep), hashlib.sha256(open(out, "rb").read()).hexdigest())
