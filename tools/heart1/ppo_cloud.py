"""PPO with cloud actors and one remote learner (the PC GPU), meeting in a store: a shared directory or git refs.

Actors run in cloud containers (4 CPUs, no GPU); one learner process (`serve`) trains every arm of a screen on a GPU
machine that shares no filesystem with them. They exchange files through a store:
  dir:PATH              a directory both sides see (tests; a shared mount)
  git:URL#PREFIX        one ref per file, refs/heads/PREFIX/<name>, each an orphan commit holding the file
                        ("data") and its metadata ("meta.json"). Actors only create new refs; the learner deletes
                        every ref it has consumed and old nets, so nothing accumulates (cloud git proxies refuse
                        deletes and force-pushes; the learner's own credentials do not).

Names in the store, per arm:
  ARM/config            arm.json: start net sha, actor env, games, parts, seed base, sims, asc, iterations,
                        value warm-up, learner hyperparameters, one_combat sha, pipeline       (written by init)
  ARM/net-NNNN          the net after NNNN updates (net-0000 = start); only the newest two stay (init, then learner)
  ARM/traj-NNNN-pK      part K of iteration NNNN's games, gzipped jsonl; meta: games, sha256,
                        behaviour net, actor seconds, first seed                             (actor of part K)
  ARM/stats-NNNN        the learner's loop.json after NNNN updates; only the newest stays      (learner)
  ARM/rebin             optional, written once: a replacement one_combat sha256 the actors may also use, for an
                        engine change that plays the same games (cmd_rebin)
Every name is written once (no ref is ever overwritten, so no force-push is needed).

Iteration i is split into P parts of GAMES/P games: part k plays seeds SEED_BASE + i*GAMES + k*GAMES/P ... with
STS_OOC_HEART1_SAMPLE_SALT=i (the same seeds and salts in every arm). Behaviour net: net_i (pipeline 0) or
net_{max(i-1,0)} (pipeline 1: actors play iteration i while the learner trains on i-1; the PPO ratio against the
recorded log-probs corrects the one-update lag, as ppo_loop.py --pipeline). Actors never run more than one iteration
ahead. The learner keeps its checkpoint (state.pt) and every net per arm in a local directory and resumes from it.

    python3 tools/heart1/ppo_cloud.py init STORE ARM --init start.bin --env-file actors.env --one-combat-sha SHA \
        --iterations 30 --games 512 --parts 2 --seed-base SEED [--pipeline 1] [--value-warmup 3] -- --lr 1e-5 ...
    python3 tools/heart1/ppo_cloud.py init STORE ARM --fork-dir LOCAL/BASE --fork-at 30 --local LOCAL --env-file ... \
        --one-combat-sha SHA --iterations 60 --games 512 --parts 4 --seed-base SEED -- --seed 0 --extra-blocks 2
        (on the learner machine: a new arm that continues BASE's run from its kept checkpoint state-0030.pt, see
        cmd_init; BASE's iteration-30 games are reused, so the arm's actors start at iteration 31)
    python3 tools/heart1/ppo_cloud.py actor STORE ARM --part K --one-combat one_combat [--threads 4]
    python3 tools/heart1/ppo_cloud.py serve STORE LOCAL_DIR ARM [ARM ...] [--device cuda]
    python3 tools/heart1/ppo_cloud.py status STORE ARM [ARM ...]
    python3 tools/heart1/ppo_cloud.py cleanup STORE ARM [ARM ...]     (end of a screen: delete every ref of the arms)
    python3 tools/heart1/ppo_cloud.py rebin STORE ARM --new SHA --reason TEXT
"""
import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ppo_loop  # noqa: E402

POLL_S = int(os.environ.get("PPO_CLOUD_POLL_S", "30"))
MAX_STALL_FRACTION = 0.01   # more stalled games than this in one part stops the actor (something else is broken)
MAX_PUT_MB = 64   # one stored file; GitHub warns at 50 MB and refuses at 100 MB per file


def check_size(path):
    mb = os.path.getsize(path) / 2**20
    if mb > MAX_PUT_MB:
        raise ValueError(f"{path}: {mb:.1f} MB exceeds the store cap of {MAX_PUT_MB} MB")


def log(msg):
    print(f"[ppo_cloud {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- stores

class DirStore:
    def __init__(self, path):
        self.root = path

    def _p(self, name):
        return os.path.join(self.root, name)

    def names(self, prefix):
        out = set()
        for d, _, files in os.walk(self.root):
            for f in files:
                if f.endswith(".meta") or ".tmp" in f:
                    continue
                rel = os.path.relpath(os.path.join(d, f), self.root)
                if rel.startswith(prefix):
                    out.add(rel)
        return out

    def put(self, name, path, meta):
        check_size(path)
        if os.path.exists(self._p(name)):   # as git refs without force-push: a name is written once
            raise FileExistsError(f"{name} exists in the store")
        os.makedirs(os.path.dirname(self._p(name)), exist_ok=True)
        tmp = f"{self._p(name)}.tmp{os.getpid()}"
        shutil.copyfile(path, tmp)
        with open(tmp + "m", "w") as f:
            json.dump(meta, f)
        os.replace(tmp + "m", self._p(name) + ".meta")
        os.replace(tmp, self._p(name))   # the data file appears last: present means complete

    def get(self, name, path):
        tmp = f"{path}.tmp{os.getpid()}"
        shutil.copyfile(self._p(name), tmp)
        os.replace(tmp, path)
        return json.load(open(self._p(name) + ".meta"))

    def delete(self, name):
        for f in (self._p(name), self._p(name) + ".meta"):
            if os.path.exists(f):
                os.remove(f)

    def get_many(self, items):
        """[(name, path)] -> [meta], as get() one by one."""
        return [self.get(n, p) for n, p in items]

    def update(self, puts=(), deletes=()):
        """Write every (name, path, meta) of puts, then delete every name of deletes."""
        for n, p, m in puts:
            self.put(n, p, m)
        for n in deletes:
            self.delete(n)


class GitStore:
    """One orphan commit per file under refs/heads/PREFIX/, through a scratch bare repository without refs."""

    def __init__(self, url, prefix):
        self.url, self.prefix = url, prefix.strip("/")
        self.repo = tempfile.mkdtemp(prefix="ppo-store-")
        self._git("init", "-q", "--bare", self.repo, here=False)
        self._since_gc = 0

    def _git(self, *args, here=True, data=None, check=True, tries=5):
        cmd = ["git"] + (["-C", self.repo] if here else []) + list(args)
        for k in range(tries):
            r = subprocess.run(cmd, input=data, capture_output=True)
            if r.returncode == 0 or not check:
                return r
            if k + 1 < tries:
                time.sleep(2 ** (k + 1))
        raise RuntimeError(f"{' '.join(cmd[3:6])}: {r.stderr.decode(errors='replace')[-400:]}")

    def _ref(self, name):
        return f"refs/heads/{self.prefix}/{name}"

    def names(self, prefix):
        r = self._git("ls-remote", self.url, f"refs/heads/{self.prefix}/{prefix}*")
        head = f"refs/heads/{self.prefix}/"
        out = set()
        for line in r.stdout.decode().splitlines():
            ref = line.split("\t", 1)[1]
            if ref.startswith(head) and ref[len(head):].startswith(prefix):
                out.add(ref[len(head):])
        return out

    def put(self, name, path, meta):
        self._git("push", "-q", self.url, f"{self._commit(path, meta, name)}:{self._ref(name)}")
        self._gc()

    def get(self, name, path):
        self._git("fetch", "-q", "--depth", "1", self.url, self._ref(name))
        tmp = f"{path}.tmp{os.getpid()}"
        with open(tmp, "wb") as f:
            subprocess.run(["git", "-C", self.repo, "cat-file", "blob", "FETCH_HEAD:data"], stdout=f, check=True)
        os.replace(tmp, path)
        meta = json.loads(self._git("cat-file", "blob", "FETCH_HEAD:meta.json").stdout)
        self._gc()
        return meta

    def delete(self, name):
        self._git("push", "-q", self.url, f":{self._ref(name)}")

    def _commit(self, path, meta, name):
        """One orphan commit holding path as data and meta as meta.json, in the scratch repository."""
        check_size(path)
        blob = self._git("hash-object", "-w", path).stdout.decode().strip()
        mblob = self._git("hash-object", "-w", "--stdin", data=json.dumps(meta).encode()).stdout.decode().strip()
        tree = self._git("mktree", data=f"100644 blob {blob}\tdata\n100644 blob {mblob}\tmeta.json\n".encode()
                         ).stdout.decode().strip()
        return self._git("-c", "user.name=ppo-cloud", "-c", "user.email=ppo-cloud@localhost", "commit-tree", tree,
                         "-m", name).stdout.decode().strip()

    def get_many(self, items):
        """[(name, path)] -> [meta]: one fetch for every name (get() fetches one ref per call)."""
        if not items:
            return []
        specs = [f"+{self._ref(n)}:refs/many/{k}" for k, (n, _) in enumerate(items)]
        self._git("fetch", "-q", "--depth", "1", "--no-tags", self.url, *specs)
        metas = []
        for k, (_, path) in enumerate(items):
            tmp = f"{path}.tmp{os.getpid()}"
            with open(tmp, "wb") as f:
                subprocess.run(["git", "-C", self.repo, "cat-file", "blob", f"refs/many/{k}:data"], stdout=f,
                               check=True)
            os.replace(tmp, path)
            metas.append(json.loads(self._git("cat-file", "blob", f"refs/many/{k}:meta.json").stdout))
        shutil.rmtree(self.repo, ignore_errors=True)   # drop the local refs and objects: the next call starts clean
        self._git("init", "-q", "--bare", self.repo, here=False)
        self._since_gc = 0
        return metas

    def update(self, puts=(), deletes=()):
        """One push that writes every (name, path, meta) of puts and deletes every name of deletes (put() and
        delete() push one ref per call). Retried as a whole; a retry after a partial success sees the new refs
        already there (same commit for a put: the push is a no-op for it; a delete of a gone ref is skipped)."""
        puts = [f"{self._commit(p, m, n)}:{self._ref(n)}" for n, p, m in puts]
        for k in range(5):   # each retry re-filters the deletes: a partly applied push leaves some refs gone
            have = self.names("") if deletes else set()
            specs = puts + [f":{self._ref(n)}" for n in deletes if n in have]
            if not specs:
                break
            r = self._git("push", "-q", self.url, *specs, check=False, tries=1)
            if r.returncode == 0:
                break
            if k == 4:
                raise RuntimeError(f"push: {r.stderr.decode(errors='replace')[-400:]}")
            time.sleep(2 ** (k + 1))
        self._gc()

    def _gc(self):
        self._since_gc += 1
        if self._since_gc >= 20:   # the scratch repo holds no refs: drop what was fetched and pushed
            shutil.rmtree(self.repo, ignore_errors=True)
            self._git("init", "-q", "--bare", self.repo, here=False)
            self._since_gc = 0


def open_store(spec):
    kind, _, rest = spec.partition(":")
    if kind == "dir":
        return DirStore(rest)
    if kind == "git":
        url, _, prefix = rest.partition("#")
        if not prefix:
            sys.exit("git store needs git:URL#PREFIX")
        return GitStore(url, prefix)
    sys.exit(f"unknown store {spec}")


def wait_for(store, name, what):
    waited = 0
    while name not in store.names(name):
        if waited % 1800 == 0:
            log(f"waiting for {what}")
        time.sleep(POLL_S)
        waited += POLL_S


def latest_stats(store, arm, names=None):
    names = store.names(f"{arm}/stats-") if names is None else names
    s = sorted(n for n in names if n.startswith(f"{arm}/stats-"))
    return s[-1] if s else None


def trained_iterations(store, arm, work):
    name = latest_stats(store, arm)
    if name is None:
        return 0
    p = os.path.join(work, "stats.json")
    store.get(name, p)
    return len(json.load(open(p))["iterations"])


# ---------------------------------------------------------------- commands

def cmd_init(argv):
    learner_argv = []
    if "--" in argv:
        k = argv.index("--")
        argv, learner_argv = argv[:k], argv[k + 1:]
    ap = argparse.ArgumentParser(prog="ppo_cloud.py init")
    ap.add_argument("store")
    ap.add_argument("arm")
    ap.add_argument("--init", help="start net (.bin); not with --fork-dir")
    ap.add_argument("--fork-dir", help="a source arm's learner directory (serve LOCAL/ARM) holding state-N.pt")
    ap.add_argument("--fork-at", type=int, help="the source's update count N to fork at (serve --keep-state N)")
    ap.add_argument("--local", help="with --fork-dir: the serve LOCAL directory the new arm's learner will use")
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--one-combat-sha", required=True, help="sha256 of the actors' one_combat")
    ap.add_argument("--iterations", type=int, required=True)
    ap.add_argument("--games", type=int, default=512)
    ap.add_argument("--parts", type=int, default=1)
    ap.add_argument("--seed-base", type=int, required=True)
    ap.add_argument("--sims", type=int, default=1000)
    ap.add_argument("--asc", type=int, default=20)
    ap.add_argument("--value-warmup", type=int, default=0)
    ap.add_argument("--pipeline", type=int, default=1)
    args = ap.parse_args(argv)
    if args.games % args.parts:
        sys.exit("--games must be a multiple of --parts")
    if bool(args.init) == bool(args.fork_dir):
        sys.exit("give exactly one of --init and --fork-dir")
    import ppo_train
    from ppo_model import PolicyNet
    hp = argparse.ArgumentParser(prog="learner")
    ppo_train.add_hparams(hp)
    hparams = hp.parse_args(learner_argv)
    ppo_train.phi_model_for(hparams)   # validate now (incl. the phi model's sha), not on the learner
    store = open_store(args.store)
    if store.names(f"{args.arm}/config"):
        sys.exit(f"{args.arm}/config exists in the store; an arm is frozen once")
    if args.fork_dir:
        return init_fork(args, learner_argv, hparams, store)
    with tempfile.TemporaryDirectory() as tmp:
        net0 = os.path.join(tmp, "net0.bin")
        PolicyNet.from_bin(args.init).to_bin(net0)   # extended with zero-init inputs, as ppo_loop
        cfg = {"arm": args.arm, "init": os.path.basename(args.init), "init_sha256": sha256(args.init),
               "net0_sha256": sha256(net0), "env": ppo_loop.read_env(args.env_file),
               "one_combat_sha256": args.one_combat_sha, "iterations": args.iterations, "games": args.games,
               "parts": args.parts, "seed_base": args.seed_base, "sims": args.sims, "asc": args.asc,
               "value_warmup": args.value_warmup, "pipeline": args.pipeline, "learner_argv": learner_argv}
        cp = os.path.join(tmp, "config.json")
        with open(cp, "w") as f:
            json.dump(cfg, f, indent=1)
        store.put(f"{args.arm}/net-0000", net0, {"sha256": cfg["net0_sha256"], "updates": 0})
        store.put(f"{args.arm}/config", cp, {"sha256": sha256(cp)})
    last = args.seed_base + args.iterations * args.games - 1
    print(f"{args.arm}: seeds {args.seed_base}..{last}, {args.iterations} x {args.games} in {args.parts} parts")


def init_fork(args, learner_argv, hparams, store):
    """A new arm continuing a source arm (arch screen design B, PREREG ppo_arch_screen_20261102).

    Runs on the learner machine, next to the source arm's serve directory. From the source's kept checkpoint
    state-N.pt (serve --keep-state N: after update N, net-N, Adam moments, iteration N) it writes the new arm's
    learner directory LOCAL/ARM: state.pt with the arm's arch flags applied (ppo_train.fork_learner), loop.json =
    the source's first N iterations (loop-N.json), net-N.bin (the constructed net) and the source's net-(N-1).bin.
    Under --pipeline 1 iteration N was played by net-(N-1), before any arm change exists, so the source's games of
    iteration N are the arm's: its kept parts/traj-N-pK go into the store as the arm's iteration-N parts, and the
    arm's actors start at iteration N+1 with the arm's net-N. Same seeds, games, parts, sims, asc and actor env as
    the source (checked); the actors' one_combat may differ (a new input arm's binary)."""
    import ppo_train
    import torch
    src, n = os.path.abspath(args.fork_dir), args.fork_at
    if n is None or n < 1 or not args.local:
        sys.exit("--fork-dir needs --fork-at N (>= 1) and --local")
    src_cfg = json.load(open(os.path.join(src, "config.json")))
    env = ppo_loop.read_env(args.env_file)
    for key, mine in (("games", args.games), ("parts", args.parts), ("seed_base", args.seed_base),
                      ("sims", args.sims), ("asc", args.asc), ("pipeline", args.pipeline), ("env", env)):
        if src_cfg[key] != mine:
            sys.exit(f"fork: {key} {mine!r} differs from the source's {src_cfg[key]!r}")
    if not args.pipeline:
        sys.exit("fork: needs --pipeline 1 (iteration N reused from the source was played by net-(N-1))")
    if args.value_warmup > n:
        sys.exit("fork: the value warm-up would reach past the fork point")
    if args.iterations <= n:
        sys.exit("fork: --iterations must exceed --fork-at")
    paths = {"state": f"state-{n:04d}.pt", "loop_n": f"loop-{n:04d}.json", "loop": "loop.json",
             "net_prev": f"net-{n - 1:04d}.bin", "net_n": f"net-{n:04d}.bin"}
    paths = {k: os.path.join(src, v) for k, v in paths.items()}
    n_part = args.games // args.parts
    parts = [os.path.join(src, "parts", f"traj-{n:04d}-p{k}.jsonl.gz") for k in range(args.parts)]
    for p in list(paths.values()) + parts:
        if not os.path.exists(p):
            sys.exit(f"fork: {p} missing")
    loop_n, loop = json.load(open(paths["loop_n"])), json.load(open(paths["loop"]))
    if len(loop_n["iterations"]) != n or loop_n["iterations"][-1].get("next_sha256") != sha256(paths["net_n"]):
        sys.exit(f"fork: {paths['loop_n']} is not the record of {paths['net_n']} after {n} updates")
    if loop["iterations"][:n] != loop_n["iterations"]:
        sys.exit("fork: the source's loop.json does not continue loop-N.json")
    behaviour = sha256(paths["net_prev"])
    if len(loop["iterations"]) > n:   # the source has trained iteration N: its games must be net-(N-1)'s
        rec = loop["iterations"][n]
        if rec.get("net") != f"net-{n - 1:04d}" or rec.get("net_sha256") != behaviour:
            sys.exit(f"fork: the source's iteration {n} was played by {rec.get('net')} {rec.get('net_sha256')}")
    learner = ppo_train.fork_learner(paths["state"], hparams, torch.device("cpu"))
    if learner.iteration != n:
        sys.exit(f"fork: {paths['state']} is at iteration {learner.iteration}, not {n}")
    arm_dir = os.path.join(args.local, args.arm)
    if os.path.exists(arm_dir) and os.listdir(arm_dir):
        sys.exit(f"fork: {arm_dir} exists and is not empty")
    os.makedirs(arm_dir, exist_ok=True)
    ppo_train.save(learner, os.path.join(arm_dir, "state.pt"))
    net_n = os.path.join(arm_dir, f"net-{n:04d}.bin")
    learner.net.to_bin(net_n)
    shutil.copyfile(paths["net_prev"], os.path.join(arm_dir, f"net-{n - 1:04d}.bin"))
    fork = {"source_arm": src_cfg["arm"], "source_dir": src, "at": n, "state_sha256": sha256(paths["state"]),
            "loop_sha256": sha256(paths["loop_n"]), "source_net_sha256": sha256(paths["net_n"]),
            "behaviour_net_sha256": behaviour, "arm_net_sha256": sha256(net_n),
            "parts_sha256": [sha256(p) for p in parts], "arm_state_sha256": sha256(os.path.join(arm_dir, "state.pt"))}
    with open(os.path.join(arm_dir, "loop.json"), "w") as f:
        json.dump({"iterations": loop_n["iterations"], "fork": fork}, f, indent=1)
    cfg = {"arm": args.arm, "init": None, "init_sha256": None, "net0_sha256": None, "env": env,
           "one_combat_sha256": args.one_combat_sha, "iterations": args.iterations, "games": args.games,
           "parts": args.parts, "seed_base": args.seed_base, "sims": args.sims, "asc": args.asc,
           "value_warmup": args.value_warmup, "pipeline": args.pipeline, "learner_argv": learner_argv,
           "start_iteration": n + 1, "fork": fork}
    cp = os.path.join(arm_dir, "config.json")
    with open(cp, "w") as f:
        json.dump(cfg, f, indent=1)
    store.put(f"{args.arm}/net-{n:04d}", net_n, {"sha256": fork["arm_net_sha256"], "updates": n})
    for k, p in enumerate(parts):
        store.put(f"{args.arm}/traj-{n:04d}-p{k}", p,
                  {"games": n_part, "sha256": fork["parts_sha256"][k], "net": f"net-{n - 1:04d}",
                   "net_sha256": behaviour, "actor_s": 0.0, "seed_first": args.seed_base + n * args.games + k * n_part,
                   "host": f"fork:{src_cfg['arm']}", "stalled": 0, "reused_from": src_cfg["arm"]})
    store.put(f"{args.arm}/config", cp, {"sha256": sha256(cp)})
    last = args.seed_base + args.iterations * args.games - 1
    print(f"{args.arm}: fork of {src_cfg['arm']} at update {n}; actors play iterations {n + 1}..{args.iterations - 1} "
          f"(seeds {args.seed_base + (n + 1) * args.games}..{last}); state {fork['arm_state_sha256'][:12]}")


def kill_stale_child(pidfile):
    """A previous actor that died without its game process (killed alone) must not keep writing."""
    try:
        pid = int(open(pidfile).read())
        cmd = open(f"/proc/{pid}/cmdline", "rb").read()
    except (OSError, ValueError):
        return
    if b"bestbench" in cmd or b"seed_guard" in cmd:
        try:
            os.killpg(pid, signal.SIGKILL)   # the game processes run in their own group (new_session)
        except OSError:
            return
        log(f"killed a stale game process {pid}")
        time.sleep(1)


def cmd_actor(argv):
    ap = argparse.ArgumentParser(prog="ppo_cloud.py actor")
    ap.add_argument("store")
    ap.add_argument("arm")
    ap.add_argument("--part", type=int, default=0)
    ap.add_argument("--one-combat", required=True)
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--work", default=None, help="local scratch (default $HOME/ppo-actor-ARM-pK)")
    a = ap.parse_args(argv)
    store = open_store(a.store)
    work = a.work or os.path.join(os.environ.get("HOME", "/tmp"), f"ppo-actor-{a.arm}-p{a.part}")
    os.makedirs(work, exist_ok=True)
    child_pid = os.path.join(work, "child.pid")
    kill_stale_child(child_pid)
    job = None

    def on_term(signum, _frame):
        if job is not None and job["proc"].poll() is None:
            os.killpg(job["proc"].pid, signal.SIGKILL)
        sys.exit(128 + signum)
    signal.signal(signal.SIGTERM, on_term)
    wait_for(store, f"{a.arm}/config", "the arm's config")
    store.get(f"{a.arm}/config", os.path.join(work, "config.json"))
    cfg = json.load(open(os.path.join(work, "config.json")))
    if not 0 <= a.part < cfg["parts"]:
        sys.exit(f"part {a.part} outside 0..{cfg['parts'] - 1}")
    bin_sha = sha256(a.one_combat)
    if bin_sha not in allowed_binaries(store, a.arm, cfg, work):
        sys.exit(f"{a.one_combat} sha256 is not the arm's {cfg['one_combat_sha256']} (or its rebin)")
    n_part = cfg["games"] // cfg["parts"]
    marker = os.path.join(work, "published.txt")
    published = set(open(marker).read().split()) if os.path.exists(marker) else set()
    for it in range(cfg.get("start_iteration", 0), cfg["iterations"]):   # a fork starts after its reused iteration
        name = f"{a.arm}/traj-{it:04d}-p{a.part}"
        if name in published:
            continue
        # The learner deletes consumed parts, so after a restart the stats say what was already trained.
        if it < trained_iterations(store, a.arm, work) or name in store.names(name):
            published.add(name)
            continue
        b = max(it - 1, 0) if cfg["pipeline"] else it
        net_name = f"{a.arm}/net-{b:04d}"
        wait_for(store, net_name, f"iteration {it}: {net_name}")
        local_net = os.path.join(work, f"net-{b:04d}.bin")
        meta = store.get(net_name, local_net)
        if sha256(local_net) != meta["sha256"]:
            sys.exit(f"{net_name}: sha256 mismatch")
        out = os.path.join(work, f"iter_{it:04d}")
        os.makedirs(out, exist_ok=True)
        log(f"iteration {it} part {a.part}: playing {n_part} games with net-{b:04d}")
        # start_actors plays seeds seed_base + it*games ...; part k of iteration it starts at
        # SEED_BASE + it*GAMES + k*n_part.
        run = argparse.Namespace(seed_base=cfg["seed_base"] + it * (cfg["games"] - n_part) + a.part * n_part,
                                 games=n_part, one_combat=a.one_combat, sims=cfg["sims"], asc=cfg["asc"],
                                 threads=a.threads)
        job = ppo_loop.start_actors(run, cfg["env"], local_net, it, out, new_session=True)
        with open(child_pid, "w") as f:
            f.write(str(job["proc"].pid))
        rc = job["proc"].wait()
        for f in job["files"]:
            f.close()
        stalled = []
        if rc != 0:
            with open(os.path.join(out, "actors.err")) as f:
                stalled = stalled_game_lines(f.read(), n_part)
            if stalled is None:
                sys.exit(f"iteration {it}: actors exited {rc} (see {out}/actors.err)")
            with open(job["traj"], "a") as f:
                f.writelines(line + "\n" for line in stalled)
            log(f"iteration {it} part {a.part}: {len(stalled)} stalled game(s) count as losses")
        with open(job["traj"]) as f:
            traj_text = f.read()
        with open(os.path.join(out, "actors.err")) as f:
            aborted = aborted_game_lines(f.read(), traj_text, job["seed"], n_part, max_stalls(n_part) - len(stalled))
        if aborted is None:
            sys.exit(f"iteration {it}: missing game lines that are not combat aborts (see {out}/actors.err)")
        if aborted:
            with open(job["traj"], "a") as f:
                f.writelines(line + "\n" for line in aborted)
            log(f"iteration {it} part {a.part}: {len(aborted)} combat-aborted game(s) count as losses")
            stalled += aborted
        n = 0
        with open(job["traj"]) as f:
            for line in f:
                n += '"type":"game"' in line and '"type":"decision"' not in line
        if n != n_part:
            sys.exit(f"iteration {it}: {n} game lines in {job['traj']}, expected {n_part}")
        gz = job["traj"] + ".gz"
        with open(job["traj"], "rb") as src, gzip.open(gz, "wb", compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)
        store.put(name, gz, {"games": n, "sha256": sha256(gz), "net": f"net-{b:04d}", "net_sha256": meta["sha256"],
                             "actor_s": time.time() - job["t0"], "seed_first": job["seed"],
                             "host": os.uname().nodename, "stalled": len(stalled), "one_combat_sha256": bin_sha})
        job = None
        published.add(name)
        with open(marker, "a") as f:
            f.write(name + "\n")
        shutil.rmtree(out)
        os.remove(local_net)
        log(f"iteration {it} part {a.part}: published")
    log("actor done")
    print("ACTOR_DONE", flush=True)


def max_stalls(n_part):
    """Stalled or aborted games one part may count as losses: 1% of the part, at least 1 (a 13-game part allows 1)."""
    return max(1, int(MAX_STALL_FRACTION * n_part))


COMBAT_ABORT = re.compile(r"^\[bestbench-combat-abort\] seed=(\d+) floor=(\d+)(.*)$", re.M)


def aborted_game_lines(err_text, traj_text, first_seed, n_part, cap):
    """Games of the part (seeds first_seed .. first_seed + n_part - 1) without a game line -> loss game lines.

    Since d3dc5eac bestbench ends a stalled combat as a CombatAbort: it records a loss row, prints
    "[bestbench-combat-abort] seed=N floor=F ..." and exits 0, but the game's trajectory (ppoEndGame) is never
    written. Returns [] if no game is missing, one loss line per missing seed if the missing seeds are exactly the
    aborted ones and there are at most cap of them, else None (the actor stops)."""
    want = {str(s) for s in range(first_seed, first_seed + n_part)}
    have = set()
    for line in traj_text.splitlines():   # the native lines have sorted keys ("type" comes last): parse them
        if '"type":"game"' in line and '"type":"decision"' not in line:
            have.add(str(json.loads(line).get("seed")))
    have &= want
    missing = want - have
    if not missing:
        return []
    aborts = {seed: (int(floor), rest.strip()) for seed, floor, rest in COMBAT_ABORT.findall(err_text)}
    if set(aborts) != missing or len(missing) > cap:
        return None
    return [json.dumps({"type": "game", "schema": ppo_loop.ppo_train.SCHEMA, "seed": seed, "decisions": 0,
                        "stalled": "combat abort " + aborts[seed][1],
                        "outcome": {"heart_kill": False, "stalled": True, "floor": aborts[seed][0]}},
                       separators=(",", ":")) for seed in sorted(missing, key=int)]


def stalled_game_lines(err_text, n_part):
    """bestbench's per-seed failures -> one "game" line per seed if every failure is a combat stall, else None.

    A sampled policy can build a deck whose fight never ends; the native Silver backend then stops the run at 1,000
    combat decisions ("stall: exceeded 1000 decisions") and the game's trajectory lines are lost (they are flushed
    only at game end). Such a game counts as a loss: a game line with no decisions (no training signal, the Heart
    rate counts it). Any other failure, a count that does not match bestbench's summary, or more than
    max_stalls(n_part) returns None (the actor stops as before)."""
    fails = re.findall(r"^\[bestbench-seed-failure\] seed=(\d+) error=(.*)$", err_text, re.M)
    summary = re.search(r"^bestbench: FAILED requested=(\d+) completed=(\d+) failed=(\d+)$", err_text, re.M)
    if not fails or not summary or int(summary.group(3)) != len(fails) or int(summary.group(1)) != n_part:
        return None
    if len(fails) > max_stalls(n_part) or not all("stall: exceeded" in msg for _, msg in fails):
        return None
    lines = []
    for seed, msg in fails:
        floor = re.search(r"floor=(\d+)", msg)
        lines.append(json.dumps({"type": "game", "schema": ppo_loop.ppo_train.SCHEMA, "seed": seed, "decisions": 0,
                                 "stalled": msg.strip(), "outcome": {"heart_kill": False, "stalled": True,
                                                                     "floor": int(floor.group(1)) if floor else 0}},
                                separators=(",", ":")))   # compact like the native lines (the actor counts them)
    return lines


class ArmLearner:
    def __init__(self, store, local, arm, device):
        import torch
        import ppo_train
        self.store, self.arm, self.device = store, arm, device
        self.keep_state = set()   # update counts after which state.pt is also kept as state-NNNN.pt (serve --keep-state)
        self.dir = os.path.join(local, arm)
        os.makedirs(self.dir, exist_ok=True)
        cfg_path = os.path.join(self.dir, "config.json")
        if not os.path.exists(cfg_path):
            store.get(f"{arm}/config", cfg_path)
        self.cfg = json.load(open(cfg_path))
        hp = argparse.ArgumentParser(prog="learner")
        ppo_train.add_hparams(hp)
        self.hparams = hp.parse_args(self.cfg["learner_argv"])
        self.state = os.path.join(self.dir, "state.pt")
        self.meta_path = os.path.join(self.dir, "loop.json")
        self.meta = json.load(open(self.meta_path)) if os.path.exists(self.meta_path) else {"iterations": []}
        net0 = os.path.join(self.dir, "net-0000.bin")
        if self.cfg.get("fork"):   # init_fork wrote state.pt, loop.json and the nets here
            net0 = None
            if not os.path.exists(self.state):
                sys.exit(f"{arm}: fork arm without {self.state} (run ppo_cloud.py init --fork-dir on this machine)")
        elif not os.path.exists(net0):
            m = store.get(f"{arm}/net-0000", net0)
            if sha256(net0) != m["sha256"] or m["sha256"] != self.cfg["net0_sha256"]:
                sys.exit(f"{arm}/net-0000 sha256 mismatch")
        self.hparams.state, self.hparams.init = self.state, net0
        torch.manual_seed(self.hparams.seed)
        # The learner (net, anchor, Adam moments) lives on the device only during its own update: one serve trains
        # many arms, and keeping every arm resident ran a 8 GB GPU out of memory after ten arms (screen1, 2026-11-02).
        # Each step reloads it from state.pt, the same path a restart takes.
        learner = ppo_train.make_learner(self.hparams, torch.device("cpu"))
        self.iteration0, self.trim_map = learner.iteration, learner.net.trim_map
        self.phi_model = ppo_train.phi_model_for(self.hparams)   # None unless --reward heart_phi (sha checked)
        del learner
        n = len(self.meta["iterations"])
        if self.iteration0 == n + 1 and os.path.exists(os.path.join(self.dir, f"net-{n + 1:04d}.bin")):
            # Crashed after the checkpoint, before loop.json: the update is done, its stats line is lost.
            self.meta["iterations"].append({"iteration": n + 1, "stats_lost": True,
                                            "next_sha256": sha256(os.path.join(self.dir, f"net-{n + 1:04d}.bin"))})
            self._write_meta()
        elif self.iteration0 != n:
            sys.exit(f"{self.state} is at iteration {self.iteration0}, loop.json at {n}")
        self.republish()

    def _write_meta(self):
        tmp = self.meta_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.meta, f, indent=1)
        os.replace(tmp, self.meta_path)

    def republish(self):
        """Make the store match the local state (idempotent): the newest net and the stats present, consumed parts
        and older nets gone. Covers a crash anywhere between the checkpoint and the end of step()."""
        it = self.next_it
        names = self.store.names(f"{self.arm}/")
        net = f"{self.arm}/net-{it:04d}"
        local = os.path.join(self.dir, f"net-{it:04d}.bin")
        puts, deletes = [], []
        if it > 0:
            if net not in names:
                puts.append((net, local, {"sha256": sha256(local), "updates": it}))
            if f"{self.arm}/stats-{it:04d}" not in names:
                puts.append((f"{self.arm}/stats-{it:04d}", self.meta_path, {"iterations": it}))
        for n in sorted(names):
            rest = n[len(self.arm) + 1:]
            if rest.startswith("traj-") and int(rest[5:9]) < it:
                deletes.append(n)
            elif rest.startswith("net-") and int(rest[4:8]) < it - 1:
                deletes.append(n)
            elif rest.startswith("stats-") and int(rest[6:10]) < it - 1:   # newest two: no read races
                deletes.append(n)
        # The new net first, in its own push: the actors wait for it; the clean-up push follows.
        self.store.update(puts=puts)
        self.store.update(deletes=deletes)

    @property
    def next_it(self):
        return len(self.meta["iterations"])

    def done(self):
        return self.next_it >= self.cfg["iterations"]

    def step(self, available):
        """Train iteration next_it if all its parts are in the store; returns True if it trained."""
        import ppo_train
        it = self.next_it
        parts = [f"{self.arm}/traj-{it:04d}-p{k}" for k in range(self.cfg["parts"])]
        if self.done() or not all(p in available for p in parts):
            return False
        t0 = time.time()
        files = [os.path.join(self.dir, os.path.basename(p) + ".jsonl.gz") for p in parts]
        metas = self.store.get_many(list(zip(parts, files)))   # one fetch for all parts
        for p, f, m in zip(parts, files, metas):
            if sha256(f) != m["sha256"]:
                sys.exit(f"{p}: sha256 mismatch")
            want = max(it - 1, 0) if self.cfg["pipeline"] else it
            local_net = os.path.join(self.dir, f"net-{want:04d}.bin")
            if m["net"] != f"net-{want:04d}" or m["net_sha256"] != sha256(local_net):
                sys.exit(f"{p}: played by {m['net']} {m['net_sha256'][:12]}, expected net-{want:04d} "
                         f"{sha256(local_net)[:12]}")
        games = ppo_train.load_games(files, self.trim_map, phi_model=self.phi_model)
        if len(games) != self.cfg["games"]:
            sys.exit(f"{self.arm} iteration {it}: {len(games)} games, expected {self.cfg['games']}")
        # Per-game outcomes for the paired analysis (a rerun of this iteration after a crash rewrites its rows).
        rows = os.path.join(self.dir, f"games-{it:04d}.csv")
        with open(rows + ".tmp", "w") as f:
            f.write("arm,iteration,seed,heart_kill,floor,net\n")
            for g in sorted(games, key=lambda g: g["seed"]):
                o = g["outcome"]
                f.write(f"{self.arm},{it},{g['seed']},{int(bool(o.get('heart_kill')))},{o.get('floor', '')},"
                        f"{metas[0]['net']}\n")
        os.replace(rows + ".tmp", rows)
        load_s = time.time() - t0
        import torch
        learner = ppo_train.make_learner(self.hparams, torch.device(self.device))
        if learner.iteration != it:
            sys.exit(f"{self.state} is at iteration {learner.iteration}, expected {it}")
        stats = learner.update(games, value_only=it < self.cfg["value_warmup"],
                                    log=lambda line: log(f"{self.arm} {line}"))
        del games
        nxt = os.path.join(self.dir, f"net-{it + 1:04d}.bin")
        learner.net.to("cpu").to_bin(nxt)
        ppo_train.save(learner, self.state)
        if it + 1 in self.keep_state:   # a fork point other screens resume from (net, optimizer, iteration)
            shutil.copyfile(self.state, os.path.join(self.dir, f"state-{it + 1:04d}.pt"))
        del learner
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        stats.update({"seed_first": min(m["seed_first"] for m in metas), "actor_s": max(m["actor_s"] for m in metas),
                      "net": metas[0]["net"], "nets": sorted({m["net"] for m in metas}),
                      "net_sha256": metas[0]["net_sha256"], "next_sha256": sha256(nxt), "load_s": load_s,
                      "learn_s": time.time() - t0, "pipeline": self.cfg["pipeline"]})
        self.meta["iterations"].append(stats)
        self._write_meta()
        if it + 1 in self.keep_state:   # the fork point's loop.json (its first it + 1 iterations), next to state-NNNN.pt
            shutil.copyfile(self.meta_path, os.path.join(self.dir, f"loop-{it + 1:04d}.json"))
        keep = os.path.join(self.dir, "parts")   # the raw games stay on the learner's disk
        os.makedirs(keep, exist_ok=True)
        for f in files:
            os.replace(f, os.path.join(keep, os.path.basename(f)))
        # Publish the net and the stats (actors read them to skip consumed iterations), delete the consumed parts
        # and every net but the newest two (the learner's disk keeps all of them).
        self.republish()
        log(f"{self.arm} iteration {it}: net-{it + 1:04d} published (load {load_s:.0f} s, "
            f"learn {time.time() - t0:.0f} s, heart {100 * stats['heart_rate']:.1f}%)")
        return True


def cmd_serve(argv):
    ap = argparse.ArgumentParser(prog="ppo_cloud.py serve")
    ap.add_argument("store")
    ap.add_argument("local")
    ap.add_argument("arms", nargs="+")
    ap.add_argument("--device", default=None)
    ap.add_argument("--micro-batch", type=int, default=0,
                    help="memory only: ppo_train --micro-batch for every arm whose minibatch exceeds it (same "
                         "gradient up to rounding; recorded in each update's stats; 0 = each arm's own setting)")
    ap.add_argument("--keep-state", type=int, nargs="*", default=[],
                    help="also keep each arm's checkpoint and loop.json after these update counts as ARM/state-NNNN.pt and "
                         "ARM/loop-NNNN.json (fork points; net-NNNN.bin is kept anyway)")
    a = ap.parse_args(argv)
    import torch
    device = a.device or ("cuda" if torch.cuda.is_available() else "cpu")
    store = open_store(a.store)
    learners = [ArmLearner(store, a.local, arm, device) for arm in a.arms]
    for x in learners:
        x.keep_state = set(a.keep_state)
    if a.micro_batch > 0:
        for x in learners:
            x.hparams.micro_batch = a.micro_batch
    log(f"serving {len(learners)} arms on {device}: " +
        ", ".join(f"{x.arm}@{x.next_it}/{x.cfg['iterations']}" for x in learners))
    while not all(x.done() for x in learners):
        available = store.names("")
        trained = False
        # Least progress first (fraction of the arm's iterations): no arm falls behind, and an arm with more, smaller
        # iterations (G_256: 60) is not held to the pace of the 30-iteration arms. Order only; each arm is independent.
        for x in sorted(learners, key=lambda x: (x.next_it / x.cfg["iterations"], x.next_it)):
            trained |= x.step(available)
        if not trained:
            time.sleep(POLL_S)
    log("all arms done")
    print("SERVE_DONE", flush=True)


def allowed_binaries(store, arm, cfg, work):
    """The one_combat sha256s an actor of the arm may play with: the config's, plus the replacement an ARM/rebin
    names (cmd_rebin) if that rebin replaces exactly the config's binary."""
    ok = {cfg["one_combat_sha256"]}
    if store.names(f"{arm}/rebin"):
        m = store.get(f"{arm}/rebin", os.path.join(work, "rebin.json"))
        if m.get("old") == cfg["one_combat_sha256"]:
            ok.add(m["new"])
    return ok


def cmd_rebin(argv):
    """Write ARM/rebin once: actors may then also play with binary NEW in place of the config's. Only for an engine
    change shown to play the same games (the evidence goes in the PREREG); the config itself stays frozen."""
    ap = argparse.ArgumentParser(prog="ppo_cloud.py rebin")
    ap.add_argument("store")
    ap.add_argument("arm")
    ap.add_argument("--new", required=True, help="sha256 of the replacement one_combat")
    ap.add_argument("--reason", required=True)
    args = ap.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{64}", args.new):
        sys.exit("--new must be a 64-char sha256")
    store = open_store(args.store)
    if store.names(f"{args.arm}/rebin"):
        sys.exit(f"{args.arm}/rebin exists; an arm is rebinned at most once")
    with tempfile.TemporaryDirectory() as tmp:
        store.get(f"{args.arm}/config", os.path.join(tmp, "config.json"))
        old = json.load(open(os.path.join(tmp, "config.json")))["one_combat_sha256"]
        if args.new == old:
            sys.exit("--new is the config's binary")
        rp = os.path.join(tmp, "rebin.json")
        with open(rp, "w") as f:
            json.dump({"old": old, "new": args.new, "reason": args.reason, "time": time.time()}, f, indent=1)
        store.put(f"{args.arm}/rebin", rp, {"old": old, "new": args.new, "sha256": sha256(rp)})
    print(f"{args.arm}: actors may play {args.new[:16]} in place of {old[:16]}")


def cmd_cleanup(argv):
    """Delete every ref of the given arms from the store (end of a screen; run where deletes are allowed)."""
    store = open_store(argv[0])
    for arm in argv[1:]:
        for n in sorted(store.names(f"{arm}/")):
            store.delete(n)
            print(f"deleted {n}")


def cmd_status(argv):
    store = open_store(argv[0])
    names = store.names("")
    for arm in argv[1:]:
        its = []
        latest = latest_stats(store, arm, names)
        if latest:
            with tempfile.TemporaryDirectory() as tmp:
                store.get(latest, os.path.join(tmp, "s"))
                its = json.load(open(os.path.join(tmp, "s")))["iterations"]
        pending = sorted(n.split("/", 1)[1] for n in names if n.startswith(f"{arm}/traj-"))
        heart = [round(100 * s["heart_rate"], 1) for s in its if "heart_rate" in s]
        print(f"{arm}: trained {len(its)} pending {pending} heart% last5 {heart[-5:]}")


if __name__ == "__main__":
    cmds = {"init": cmd_init, "actor": cmd_actor, "serve": cmd_serve, "status": cmd_status, "cleanup": cmd_cleanup,
            "rebin": cmd_rebin}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit("usage: ppo_cloud.py {init|actor|serve|status|cleanup|rebin} ...")
    cmds[sys.argv[1]](sys.argv[2:])
