"""Horizontal map mirror (x -> 6 - x) of a heart1 capture record, an exact symmetry of the game (§674 map-mirror audit).

Node xs, the burning elite, the current node and the offered paths map to 6 - x (-1 = no column is kept); the
[left, straight, right] edge triples become [6-right, 6-straight, 6-left]; map tokens are re-sorted by (y, x) as
buildRecord emits them. On floor 14 the only path is the boss move (action idx 0), which is kept. Path tokens keep
their order, so per-token targets stay aligned. Same transform as docs/experiments/evidence/map_mirror_20261023/mirror.py.
"""

def mx(x): return 6 - x if x >= 0 else x

def mirror(rec):
    r = dict(rec)
    xs = [mx(x) for x in rec["obs.map.xs"]]
    px = [[mx(p[2]), mx(p[1]), mx(p[0])] for p in rec["obs.map.pathXs"]]
    order = sorted(range(len(xs)), key=lambda j: (rec["obs.map.ys"][j], xs[j]))
    r["obs.map.xs"] = [xs[j] for j in order]
    r["obs.map.ys"] = [rec["obs.map.ys"][j] for j in order]
    r["obs.map.roomTypes"] = [rec["obs.map.roomTypes"][j] for j in order]
    r["obs.map.pathXs"] = [px[j] for j in order]
    r["obs.map.burningEliteX"] = mx(rec.get("obs.map.burningEliteX", -1))
    r["obs.mapX"] = mx(rec["obs.mapX"])
    if rec["obs.mapY"] != 14: r["paths_offered"] = [mx(p) for p in rec["paths_offered"]]
    return r
