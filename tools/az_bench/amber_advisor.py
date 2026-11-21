#!/usr/bin/env python3
"""Live advisor proxy with the Amber net's decision explanation (2026-11-21; read-only, CPU only).

The STS Model Inspector mod starts one advisor executable and talks sts_model_inspector_v1 NDJSON with it. This
proxy starts the existing advisor (one_combat_advisor) as its child, passes every request and response through
unchanged, and adds one evaluator to the responses of out-of-combat observations:

  {"id": "amber_explain_v1", "scope": "ooc_decision", "status": "OK" | "FORCED" | "UNSUPPORTED" | "ERROR", ...}

with the Amber net's search from the observed state (amber_probe.py: the live stage-1 run's search rules, full
budget, noise-free) and its explanation (explain_live.py): per option the net's prior, the search's visits, Q,
search-backed P(win) and expected HP, the items the prior thinks the option synergises with; for the pick against
the runner-up the leave-one-out effects, Shapley values, the smallest item set that reverses the net's preference
and the HP at which it reverses. No language model; every number is the net's or the search's output.

Configuration (environment first, then the inspector's properties file, STS_MODEL_INSPECTOR_CONFIG or
~/.sts-model-inspector.properties):
  STS_AMBER_INNER_ADVISOR / amberInnerAdvisor   the advisor to wrap (one_combat_advisor; required)
  STS_AMBER_CKPT / amberCkpt                    an Amber checkpoint (selfplay.py ckpt_*.pt)
  STS_AMBER_MODULE_DIR / amberModuleDir         directory of az_bench_live (cmake --build ... --target az_bench_live)
  STS_AMBER_THREADS / amberThreads              CPU threads for the net (default 2; the GPU is never used)
  STS_AMBER_SIMS / amberSims                    simulations per decision (default 64, the live run's full budget)
  STS_AMBER_OOC / amberOoc                      "only" (default): out-of-combat requests are answered by this proxy
                                                alone (the inner advisor's own OOC search, a pre-Amber agent that
                                                takes 25-45 s, is skipped); "both": the inner advisor answers too and
                                                the Amber evaluator is added to its response (both run at once)
Set the mod's `advisor` to this file (executable). Without a checkpoint or module the proxy still passes the inner
advisor through and reports amber_explain_v1 as UNSUPPORTED with the reason.
"""

import json
import os
import subprocess
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

EVALUATOR = "amber_explain_v1"


def load_config(env=None):
    env = os.environ if env is None else env
    props = {}
    path = env.get("STS_MODEL_INSPECTOR_CONFIG") or os.path.join(os.path.expanduser("~"), ".sts-model-inspector.properties")
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line[0] in "#!" or "=" not in line:
                continue
            k, v = line.split("=", 1)
            props[k.strip()] = v.strip()
    get = lambda e, p, d=None: (env.get(e) or "").strip() or props.get(p) or d  # noqa: E731
    return {"inner": get("STS_AMBER_INNER_ADVISOR", "amberInnerAdvisor"), "ckpt": get("STS_AMBER_CKPT", "amberCkpt"),
            "module_dir": get("STS_AMBER_MODULE_DIR", "amberModuleDir"),
            "threads": int(get("STS_AMBER_THREADS", "amberThreads", "2")),
            "sims": int(get("STS_AMBER_SIMS", "amberSims", "64")),
            "ooc": get("STS_AMBER_OOC", "amberOoc", "only")}


def _num(x, nd=4):
    x = float(x)
    return round(x, nd) if x == x and abs(x) != float("inf") else None


class Amber:
    """The net, the module and the explanation of one live observation."""

    def __init__(self, cfg):
        self.cfg, self.error = cfg, None
        try:
            if not cfg["ckpt"] or not cfg["module_dir"]:
                raise RuntimeError("amberCkpt / amberModuleDir not configured")
            import torch
            torch.set_num_threads(max(1, cfg["threads"]))
            import amber_probe as ap
            import explain as ex
            import explain_live as el
            self.torch, self.ap, self.ex, self.el = torch, ap, ex, el
            self.native = ap.native_module(cfg["module_dir"], live=True)
            self.net = ex.load_net(cfg["ckpt"])
            self.vocab = ex.Vocab()
            self.model = os.path.basename(cfg["ckpt"])
        except Exception as e:   # the proxy keeps passing the inner advisor through
            self.error = f"{type(e).__name__}: {e}"

    def evaluate(self, observation):
        t0 = time.time()
        out = {"id": EVALUATOR, "scope": "ooc_decision"}
        if self.error:
            out.update(status="UNSUPPORTED", reason=self.error)
            return out
        try:
            state = self.native.GameState.from_live(json.dumps(observation))
        except ValueError as e:
            out.update(status="UNSUPPORTED", reason=str(e))
            return out
        res = self.ap.probe_states(self.native, self.net, [state], full_sims=self.cfg["sims"])[0]
        out.update(model=self.model, sims=self.cfg["sims"], floor=res["floor"], hp=res["hp"], maxHp=res["max_hp"])
        if res["status"] != "searched":
            out["status"] = "FORCED" if res["status"] == "forced" else "UNSUPPORTED"
            out["reason"] = res["status"]
            if res["status"] == "forced":
                try:
                    out["selectedLiveAction"] = json.loads(state.lower_action(int(res["pick_bits"])))
                except ValueError as e:
                    out["reason"] = f"forced, not mapped: {e}"
            out["latencyMicros"] = int((time.time() - t0) * 1e6)
            return out
        ex, el, ap = self.ex, self.el, self.ap
        row = ap.row_of(res["sample"])
        score = list(res["score"])
        pick = int(res["pick"])
        others = sorted((i for i in range(len(score)) if i != pick), key=lambda i: -score[i])
        runner = others[0] if others else None
        why = el.explain_decision(self.net, row, self.vocab, pick, runner)
        lg = [float(x) for x in res["logit"]]
        m = max(lg)
        prior = [2.718281828459045 ** (x - m) for x in lg]
        s = sum(prior)
        total = max(1, int(sum(res["n"])))
        nxt = res["floor"]   # index of floor + 1 in the per-floor HP vector (floors 1..56)
        cands = []
        for i in range(len(lg)):
            try:
                live = json.loads(state.lower_action(int(res["bits"][i])))
            except ValueError:
                live = None
            hpf = res.get("hpf")
            opt = why["options"][i] if i < len(why["options"]) else None
            cands.append({"liveAction": live, "label": ex.action_label(row, i, self.vocab) if i < len(row.a_type) else "",
                          "selected": i == pick, "prior": _num(prior[i] / s), "logit": _num(lg[i], 3),
                          "visits": int(res["n"][i]), "visitShare": _num(int(res["n"][i]) / total),
                          "q": _num(res["q"][i]), "qCompleted": _num(res["q_completed"][i]),
                          "policy": _num(res["policy"][i]), "pWin": _num(res["pwin"][i]),
                          "hpFloorEnd": _num(res["ehp"][i], 1),
                          "hpNextFloor": _num(hpf[i][nxt] * 255, 1) if hpf is not None and nxt < 56 else None,
                          "why": None if opt is None else {"ref": opt["ref"], "contrast": opt["contrast"],
                                                           "for": opt["for"], "against": opt["against"]}})
        order = sorted(range(len(cands)), key=lambda i: (not cands[i]["selected"], -score[i]))
        out.update(status="OK", decision=ex.decision_kind(row),
                   root={"netPWin": _num(res["root_dist"][0]), "searchPWin": _num(res["search_pwin"]),
                         "netHpFloorEnd": _num(res["root_ehp"], 1), "searchHpFloorEnd": _num(res["search_ehp"], 1),
                         "visits": int(res["root_n"]), "sigma": _num(res["sigma"], 3)},
                   selectedLiveAction=cands[pick]["liveAction"], candidates=[cands[i] for i in order],
                   pair=why.get("pair"), value=why.get("value"), items=why.get("items"),
                   latencyMicros=int((time.time() - t0) * 1e6))
        return out


PROTOCOL, PROTOCOL_VERSION = "sts_model_inspector_v1", 1


def _guarded(evaluate, obs, log):
    try:
        return evaluate(obs)
    except Exception as e:
        traceback.print_exc(file=log)
        return {"id": EVALUATOR, "scope": "ooc_decision", "status": "ERROR", "reason": f"{type(e).__name__}: {e}"}


def own_response(req, ev):
    """The analysis envelope of an out-of-combat request answered by the proxy alone (amberOoc = only)."""
    status = {"OK": "OK", "FORCED": "OK"}.get(ev.get("status"), "UNSUPPORTED")
    out = {"evaluators": [ev], "kind": "analysis", "observationHash": req.get("observationHash"),
           "protocol": PROTOCOL, "protocolVersion": PROTOCOL_VERSION, "sequence": req.get("sequence"),
           "session": req.get("session"), "status": status}
    if status != "OK":
        out["reason"] = ev.get("reason", "")
    return out


def serve(inp, outp, inner_cmd, evaluate, mode="only", log=sys.stderr):
    """Passes NDJSON lines from inp to the inner advisor and its answers to outp. An out-of-combat request: mode
    "only" answers it with evaluate(observation) alone; "both" runs evaluate while the inner advisor answers and
    appends the result to the inner response's evaluators."""
    child = subprocess.Popen([inner_cmd], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
                             text=True, encoding="utf-8", bufsize=1)

    def emit(obj):
        outp.write(json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n")
        outp.flush()

    try:
        for line in inp:
            if not line.strip():
                continue
            try:
                req = json.loads(line)
            except ValueError:
                req = None
            obs = req.get("observation") if isinstance(req, dict) else None
            ooc = isinstance(obs, dict) and obs.get("boundary") == "ooc"
            if ooc and mode == "only":
                emit(own_response(req, _guarded(evaluate, obs, log)))
                continue
            box = {}
            worker = None
            if ooc:
                worker = threading.Thread(target=lambda: box.update(ev=_guarded(evaluate, obs, log)), daemon=True)
                worker.start()
            child.stdin.write(line if line.endswith("\n") else line + "\n")
            child.stdin.flush()
            answer = child.stdout.readline()
            if not answer:
                raise RuntimeError("inner advisor exited")
            if worker is None:
                outp.write(answer)
                outp.flush()
                continue
            worker.join()
            try:
                resp = json.loads(answer)
                resp.setdefault("evaluators", []).append(box["ev"])
                emit(resp)
            except (ValueError, TypeError, AttributeError) as e:   # pass the inner answer through unchanged
                print(f"amber_advisor: {e}", file=log)
                outp.write(answer)
                outp.flush()
    finally:
        try:
            child.stdin.close()
        except OSError:
            pass
        child.wait(timeout=10)


def main():
    cfg = load_config()
    if not cfg["inner"]:
        print("amber_advisor: set STS_AMBER_INNER_ADVISOR or amberInnerAdvisor (the one_combat_advisor path)",
              file=sys.stderr)
        return 2
    amber = Amber(cfg)
    if amber.error:
        print(f"amber_advisor: explanation off: {amber.error}", file=sys.stderr)
    serve(sys.stdin, sys.stdout, cfg["inner"], amber.evaluate, cfg["ooc"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
