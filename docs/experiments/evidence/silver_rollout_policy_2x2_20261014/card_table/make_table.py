"""Write the rollout card table from fit_card_table.py's output.

Usage: python3 -I make_table.py card_table_fit.json card_table_g6.txt
Each fitted weight w[key] (key = card id * 2 + upgraded, nonzero weights only) becomes the line
"<card id> <upgraded> <w with 6 decimals>", sorted by key.
"""
import json, sys

w = json.load(open(sys.argv[1]))["weights"]
with open(sys.argv[2], "w") as f:
    for k, v in sorted(w.items(), key=lambda kv: int(kv[0])):
        k = int(k)
        f.write(f"{k // 2} {k % 2} {v:.6f}\n")
