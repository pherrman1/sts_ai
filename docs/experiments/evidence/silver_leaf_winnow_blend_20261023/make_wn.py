#!/usr/bin/env python3
"""Write the constant head wn.txt: a leaf head whose output is always 10000 points (the a20 head's file with its output
layer zeroed and offset 10000). Under the win-now cap it always binds, so hblend:wn:L+cap is exactly
L x winNow + (1 - L) x playout, with no net in the value (the trunk still runs, its output is unused).

usage: make_wn.py heads/a20.txt OUT/wn.txt   (sha256 of the result: 5efb2d2d...)
"""
import sys

src, dst = sys.argv[1], sys.argv[2]
out = []
for line in open(src).read().split("\n"):
    t = line.split(" ")
    if t[0] == "w2":
        line = "w2 " + " ".join(["0"] * (len(t) - 1))
    elif t[0] == "b2":
        line = "b2 0"
    elif t[0] == "offset":
        line = "offset 10000"
    out.append(line)
open(dst, "w").write("\n".join(out))
