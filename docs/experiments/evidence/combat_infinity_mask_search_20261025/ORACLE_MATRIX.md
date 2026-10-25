# Selected-mask K=4 annotation

| Decision | Active | Worlds | Classification | Candidate / certified | Nodes per world | Max depth per world | Caps | Oracle CPU ms |
|---:|---:|---:|---|---|---|---|---|---:|
|10|9|4 supported|NONE x4|0.0 / 0.0|[54, 54, 54, 54]|[4, 4, 4, 4]|0|0.601|
|12|9|4 supported|NONE x4|0.0 / 0.0|[19, 19, 19, 19]|[3, 3, 3, 3]|0|0.189|
|13|9|4 supported|NONE x4|0.0 / 0.0|[6, 6, 6, 6]|[2, 2, 2, 2]|0|0.063|
|14|9|4 supported|NONE x4|0.0 / 0.0|[2, 2, 2, 2]|[1, 1, 1, 1]|0|0.021|

Total 16 supported worlds, 324 nodes, 0.874ms reported oracle CPU; process CPU 0.008279s. No candidate, repeated control state, replay action or witness. Reach depths remain null. No budget change.

All four selected roots are turn2 with enemy Vulnerable0; Bash and Pommel Strike remain in the public unordered four-card draw pile, while the hand has no draw mechanism. Dropkicks cannot initiate their draw/refund loop in these roots. This is a public-state explanation for the small searched action trees, not a proven absence for the run, other roots or future turns.

The 16 concrete sampled worlds and their draw orders/seeds are retained in oracle.jsonl. Those are independently public-conditioned samples, not the real hidden order.
