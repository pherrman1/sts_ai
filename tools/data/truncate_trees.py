#!/usr/bin/env python3
"""Keep the first N trees of a CombatValueNet tree-text file (boosting is additive,
so a prefix is a lower-capacity model). Usage: python3 tools/data/truncate_trees.py in.txt out.txt N"""
import sys
src, dst, N = sys.argv[1], sys.argv[2], int(sys.argv[3])
with open(src) as f:
    lines = f.readlines()
i = 0
head = []
while not lines[i].startswith("ntrees"):
    head.append(lines[i]); i += 1
# lines[i] is 'ntrees T'
i += 1
blocks = []
cur = None
while i < len(lines):
    if lines[i].startswith("tree "):
        if cur is not None: blocks.append(cur)
        cur = [lines[i]]
    else:
        cur.append(lines[i])
    i += 1
if cur is not None: blocks.append(cur)
keep = blocks[:N]
with open(dst, "w") as f:
    f.writelines(head)
    f.write(f"ntrees {len(keep)}\n")
    for b in keep:
        # renumber tree index to be safe (loader ignores idx, but keep tidy)
        f.writelines(b)
print(f"{dst}: kept {len(keep)}/{len(blocks)} trees")
