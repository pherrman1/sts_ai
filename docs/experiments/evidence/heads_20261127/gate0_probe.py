"""Test 2 (heads thread, Philipp's go 2026-11-26 21:27 CET): what do the encounter tokens carry in the live net?
Read-only, CPU, no seeds. On whole UNSEEN runs (slice_runs.py output, unseen_*.npz) the checkpoint's net is evaluated
three ways: FULL (as trained), GATE0 (every enemy_gate parameter set to 0: encounter tokens weighted 0 in attention
and in the summary mean) and STRIP (amber_net.strip_encounters: the tokens removed). Reported per row group
(out-of-combat rows that hold encounter tokens = 'enc', all other rows = 'other'):
  outcome CE vs the final outcome, CE vs the stored EMA target, AUC / Brier of P(win) (class 0),
  policy CE vs the stored search policy (rows with a policy), argmax agreement with FULL, mean |dP(win)|.
Pre-registered rule (written before the data): on 'enc' rows, if GATE0 changes outcome CE (final) by < +0.5 %
relative AND policy CE by < +0.5 % relative AND the prior argmax agrees with FULL in >= 98 % of rows, the tokens
carry next to nothing -> candidate to switch off (Philipp decides). Otherwise they carry information -> keep.
usage: python3 -I gate0_probe.py REPO CKPT SLICE_DIR OUT_JSON [MAX_RUNS=600] [THREADS=4]"""
import copy, glob, importlib.util, json, os, sys, time
import numpy as np
import torch

repo, ckpt_path, sdir, out_json = sys.argv[1:5]
MAX_RUNS = int(sys.argv[5]) if len(sys.argv) > 5 else 600
torch.set_num_threads(int(sys.argv[6]) if len(sys.argv) > 6 else 4)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("sp", os.path.join(repo, "tools", "az_bench", "selfplay.py"))
sp = importlib.util.module_from_spec(spec); spec.loader.exec_module(sp)
am = sp.amber_net
import netload  # copied next to this script from halflife-b-20261125
ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)
net, _, _, W, A = netload.build(sp, ck)
net.eval()
g0 = copy.deepcopy(net)
with torch.no_grad():
    g0.enemy_gate.zero_()
INT = {"tok_type", "ids", "a_type", "a_src", "a_tgt"}


def runs(fn):
    z = np.load(fn)
    names = sorted({k.split(".")[0] for k in z.files}, key=lambda s: int(s[1:]))
    for nm in names:
        bt = {}
        for k in z.files:
            if k.startswith(nm + ".") and not k.endswith((".abs", ".run_id")):
                key = k.split(".", 1)[1]; v = z[k]
                t = torch.from_numpy(v.astype(np.int64) if key in INT else v)
                bt[key] = t.float() if t.dtype == torch.float16 else t
        yield bt


def auc(p, y):
    o = np.argsort(p); r = np.empty(len(p)); r[o] = np.arange(1, len(p) + 1)
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / max(1, n1 * n0))


acc = {g: {a: {"oc": [], "oe": [], "pw": [], "y": [], "pc": [], "arg": []} for a in ("full", "gate0", "strip")}
       for g in ("enc", "other")}
nrun, t0 = 0, time.time()
with torch.no_grad():
    for fn in sorted(glob.glob(os.path.join(sdir, "unseen_*.npz"))):
        for bt in runs(fn):
            if nrun >= MAX_RUNS: break
            nrun += 1
            cls = am.token_classes(bt["tok_type"], bt["ids"], bt["f"])
            enc_row = (bt["mask"] & am.enc_of(cls)).any(1)
            outs = {"full": net(bt), "gate0": g0(bt), "strip": net(am.strip_encounters(bt))}
            y_out = bt["outcome"].long().clamp(0, am.OUTCOME_CLASSES - 1)
            has = bt["has_policy"].bool() if "has_policy" in bt else bt["policy"].sum(-1) > 0
            arg_full = outs["full"][0].argmax(-1)
            for a, o in outs.items():
                lg, oc = o[0].float(), o[1].float()
                ls = torch.log_softmax(oc, -1)
                ce = -ls.gather(1, y_out[:, None])[:, 0]
                ema = -(bt["soft_outcome"].float() * ls).sum(-1) if "soft_outcome" in bt else ce * float("nan")
                pw = ls[:, 0].exp()
                lp = torch.log_softmax(lg.masked_fill(~bt["a_mask"], -1e4), -1)
                pce = -(bt["policy"].float() * lp).sum(-1)
                same = (lg.argmax(-1) == arg_full).float()
                for g, sel in (("enc", enc_row), ("other", ~enc_row)):
                    d = acc[g][a]
                    d["oc"].append(ce[sel]); d["oe"].append(ema[sel]); d["pw"].append(pw[sel])
                    d["y"].append((y_out[sel] == 0).float())
                    d["pc"].append(pce[sel & has]); d["arg"].append(same[sel & has])
        if nrun % 100 == 0:
            print(f"{nrun} runs ({time.time() - t0:.0f} s)", flush=True)
res = {"ckpt": os.path.basename(ckpt_path), "step": ck.get("step"), "runs": nrun,
       "gates": [round(float(x), 4) for x in net.enemy_gate], "groups": {}}
for g in acc:
    res["groups"][g] = {}
    full_pw = torch.cat(acc[g]["full"]["pw"]).numpy()
    for a in acc[g]:
        d = {k: torch.cat(v).numpy() for k, v in acc[g][a].items()}
        if len(d["oc"]) == 0: continue
        res["groups"][g][a] = {"rows": int(len(d["oc"])), "policy_rows": int(len(d["pc"])),
                               "outcome_ce": float(d["oc"].mean()), "outcome_ema_ce": float(np.nanmean(d["oe"])),
                               "auc_pwin": auc(d["pw"], d["y"]), "brier": float(((d["pw"] - d["y"]) ** 2).mean()),
                               "policy_ce": float(d["pc"].mean()) if len(d["pc"]) else None,
                               "argmax_agree": float(d["arg"].mean()) if len(d["arg"]) else None,
                               "mean_abs_dpwin": float(np.abs(d["pw"] - full_pw).mean())}
e = res["groups"].get("enc", {})
if "full" in e and "gate0" in e:
    f, z = e["full"], e["gate0"]
    rel = lambda k: (z[k] - f[k]) / f[k]
    res["rule"] = {"outcome_rel": rel("outcome_ce"), "policy_rel": rel("policy_ce"), "argmax_agree": z["argmax_agree"],
                   "verdict": "CARRIES_LITTLE" if rel("outcome_ce") < 0.005 and rel("policy_ce") < 0.005
                   and z["argmax_agree"] >= 0.98 else "CARRIES_INFO"}
with open(out_json, "w") as fh:
    json.dump(res, fh, indent=1)
print(json.dumps(res, indent=1))
