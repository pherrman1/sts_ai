#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# SELF-PLAY ITERATION LOOP — AlphaZero-style, fair-play, no hand knowledge.
#
# Retrains the agent per arm and promotes each arm independently when it wins:
#   META  V_win(state)->P(win) + paired rest   OOC picks via v_server
#   FIGHT combat value net (leaf)  +  policy prior (PUCT)     [COMBAT=1, default]
#
# Each iteration:  self-play datagen -> retrain due arms -> GATE each candidate vs
# current on held-out seeds -> promote qualifying arms independently (all-or-nothing
# only within one arm's own promotion; a policy promotion is deferred if value also
# promoted in the same iteration). Promotion is allowed ONLY on the final hard-cap
# gate look (multiplicity guard); intermediate looks are advisory.
# Everything is versioned on disk: Ctrl-C ANYTIME and re-run to CONTINUE from the
# last completed iteration (a killed iteration is just redone; promotion is atomic).
#
# Live tracking in another terminal:   watch -n2 selfplay/status.sh
#
# Config via env (defaults SMALL for validation; scale RUNS_PER_ITER/SIMS up later):
#   RUNS_PER_ITER  self-play runs per iteration        (1000)
#   SIMS           combat sims per decision            (400)
#   META_SIMS      sims for meta-label datagen          (300)
#   GATE_SIMS      sims for held-out verification       (600)
#   POLICY_SIMS    stronger teacher sims for combat/policy targets (1000)
#   WINDOW         combat replay buffer: last N iters  (4)
#   META_WINDOW    V_win replay buffer: last N iters    (=WINDOW)
#   GATE_SEEDS     maximum held-out seeds for adaptive promotion gate (500)
#   GATE_INITIAL   first paired-seed look                       (100)
#   GATE_STEP      extra paired seeds per inconclusive look     (100)
#   GATE_Z         confidence bound Z (2.58 ~= 99% nominal per look)
#   COMBAT         retrain fight models (0/1)          (1)
#   POLICY_RETRAIN retrain the PUCT prior (0/1)        (1)
#   META_RETRAIN_EVERY   retrain/gate V_win every N iterations (2)
#   VALUE_RETRAIN_EVERY  retrain/gate combat value every N iterations (2)
#   POLICY_RETRAIN_EVERY retrain/gate prior every N iterations (2)
#   POLICY_TREES   maximum trees in the policy prior   (100)
#   VNET_ALPHA     value-net leaf blend               (0.3)
#   VNET_TREES     truncate value net to N trees (0=all) (0)
#   VALUE_MARGIN   value-gate margin              (=PROMOTE_MARGIN; a negative
#                  value requires VALUE_MARGIN_LATENCY=1 latency evidence)
#   VALUE_MARGIN_LATENCY  measured latency evidence for negative VALUE_MARGIN (0)
#   MAX_ITERS      stop after N iters (0=forever)      (0)
#   ASC            ascension                           (0)
# ---------------------------------------------------------------------------
set -u
cd "$(dirname "$0")/.."
SP=selfplay
mkdir -p $SP/buffer $SP/rbuffer $SP/cbuffer $SP/pbuffer $SP/models $SP/current $SP/cand $SP/logs

# CMake produces build/one_combat; a stale root ./one_combat.elf is NOT the built
# binary. Override with ONE_COMBAT_BIN or STS_BIN.
BIN=${ONE_COMBAT_BIN:-${STS_BIN:-./build/one_combat}}
if [ ! -x "$BIN" ]; then
    echo "ERROR: $BIN missing or not executable; build with 'cmake --build build -j' or set ONE_COMBAT_BIN/STS_BIN" >&2
    exit 1
fi

RUNS_PER_ITER=${RUNS_PER_ITER:-1000}
SIMS=${SIMS:-400}
# the META datagen pass only needs combats played out to a win/loss for V_win labels
# (it does NOT generate combat targets), so it can run at fewer sims than the combat
# pass -> big speedup on the more expensive pass. Defaults to SIMS if unset.
META_SIMS=${META_SIMS:-300}
REST_CF_SIMS=${REST_CF_SIMS:-300}
REST_CF_FUTURES=${REST_CF_FUTURES:-1}
REST_CF_STRIDE=${REST_CF_STRIDE:-4}       # paired branches on ~1/4 of meta runs
# Policy targets must come from a stronger search than the deployed 400-600-sim
# student; otherwise self-play merely distills its current prior into itself.
POLICY_SIMS=${POLICY_SIMS:-1000}
GATE_SIMS=${GATE_SIMS:-600}
WINDOW=${WINDOW:-4}
# Meta CSVs are small, and reducing runs/iteration otherwise silently shrinks the
# effective number of independent trajectories used by V_win. Keep this separate
# from the much larger combat replay window.
META_WINDOW=${META_WINDOW:-$WINDOW}
REST_WINDOW=${REST_WINDOW:-5}
# The policy buffer is ~70x denser than meta (~2M rows/iter) AND its target (the
# current searcher's visit-π) goes stale fast, so it uses a SEPARATE small window:
# fresher targets + bounded load RAM (5-window would be ~37GB CSV / ~18GB int16 frame).
POLICY_WINDOW=${POLICY_WINDOW:-2}
GATE_SEEDS=${GATE_SEEDS:-500}           # held-out cap; adaptive gate stops clear regressions early,
                                        # but promotion is allowed only at the cap (multiplicity guard)
GATE_INITIAL=${GATE_INITIAL:-100}       # cheap first look; clear regressions stop here
GATE_STEP=${GATE_STEP:-100}             # extend ambiguous comparisons up to GATE_SEEDS
GATE_Z=${GATE_Z:-2.58}                  # nominal per-look bound; see multiplicity guard in the gate loop
PROMOTE_MARGIN=${PROMOTE_MARGIN:-0.5}   # min blended-score gain to promote (kills '>=' tie-promote)
# A negative VALUE_MARGIN is a latency allowance, not a quality standard: it is
# honored only with measured latency evidence (VALUE_MARGIN_LATENCY=1). Without
# the flag, a negative value is clamped to PROMOTE_MARGIN so a zero-delta value
# candidate can never qualify (Issue 14).
VALUE_MARGIN_LATENCY=${VALUE_MARGIN_LATENCY:-0}
VALUE_MARGIN=${VALUE_MARGIN:-$PROMOTE_MARGIN}
if [ "$VALUE_MARGIN_LATENCY" != 1 ] && [ "${VALUE_MARGIN:0:1}" = "-" ]; then
    echo "WARNING: VALUE_MARGIN=$VALUE_MARGIN is negative but VALUE_MARGIN_LATENCY!=1; forcing $PROMOTE_MARGIN (latency evidence required)" | tee -a $SP/logs/loop.log >&2
    VALUE_MARGIN=$PROMOTE_MARGIN
fi
WIN_WEIGHT=${WIN_WEIGHT:-0.1}           # win% weight in the blended gate score (floor-dominant)
COMBAT=${COMBAT:-1}
POLICY_RETRAIN=${POLICY_RETRAIN:-1}
META_RETRAIN_EVERY=${META_RETRAIN_EVERY:-2}
VALUE_RETRAIN_EVERY=${VALUE_RETRAIN_EVERY:-2}
POLICY_RETRAIN_EVERY=${POLICY_RETRAIN_EVERY:-2}
[ "$META_RETRAIN_EVERY" -lt 1 ] && META_RETRAIN_EVERY=1
[ "$VALUE_RETRAIN_EVERY" -lt 1 ] && VALUE_RETRAIN_EVERY=1
[ "$POLICY_RETRAIN_EVERY" -lt 1 ] && POLICY_RETRAIN_EVERY=1
POLICY_TREES=${POLICY_TREES:-100}
VNET_ALPHA=${VNET_ALPHA:-0.3}
VNET_TREES=${VNET_TREES:-0}
MAX_ITERS=${MAX_ITERS:-0}
ASC=${ASC:-0}
EPS=${EPS:-0.05}
CEPS=${CEPS:-0.3}                       # combat/policy datagen exploration eps
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-12}
# Start from the proven hybrid OOC policy: V_floor (v_rich) for card/shop choices and
# V_win for survival-shaped rest choices.  A newly trained V_win only takes over all
# OOC choices after the held-out gate proves that the unified policy beats this anchor.
FLOOR_POLICY_ENV="STS_FAIR=1 STS_CARD_WIN=0 STS_SHOP_WIN=0 STS_REST_WIN=1"
WIN_POLICY_ENV="STS_FAIR=1 STS_CARD_WIN=1 STS_SHOP_WIN=1 STS_REST_WIN=1"
# The META arm must exercise the CANDIDATE models through v_server (Issue 01):
# with native OOC left on, one_combat's fixed build/v_rich_trees.txt +
# build/v_win_trees.txt own every OOC decision and the candidate V_win/rest are
# never consulted.  STS_NATIVE_OOC=0 forces server-backed inference for meta
# generation and meta gates.  Combat datagen and value/policy gates keep the
# deployed native stack.
META_OOC_DISABLE="STS_NATIVE_OOC=0"
FLOOR_META_POLICY_ENV="$FLOOR_POLICY_ENV $META_OOC_DISABLE"
WIN_META_POLICY_ENV="$WIN_POLICY_ENV $META_OOC_DISABLE"

STATE=$SP/state.env; HIST=$SP/history.tsv; STATUS=$SP/status.txt
GATE_DIR=$SP/gate; GATE_STATE=$GATE_DIR/progress.env
BASE_CACHE_DIR=$GATE_DIR/baseline_cache
mkdir -p "$GATE_DIR" "$BASE_CACHE_DIR"
META_MODE_FILE=$SP/meta_mode.env
[ -f "$META_MODE_FILE" ] || echo floor > "$META_MODE_FILE"
META_MODE=$(cat "$META_MODE_FILE")
case "$META_MODE" in
    floor) POLICY_ENV=$FLOOR_POLICY_ENV; META_POLICY_ENV=$FLOOR_META_POLICY_ENV;;
    win)   POLICY_ENV=$WIN_POLICY_ENV;   META_POLICY_ENV=$WIN_META_POLICY_ENV;;
    *)     echo "floor" > "$META_MODE_FILE"; META_MODE=floor; POLICY_ENV=$FLOOR_POLICY_ENV; META_POLICY_ENV=$FLOOR_META_POLICY_ENV;;
esac
MEAS_COMBAT=""                          # combat env for the current gate batch
MEAS_POLICY_ENV="$POLICY_ENV"           # OOC policy env for the current gate batch

# ---- bootstrap state machine (Issues 11/30) ---------------------------------
#   fresh:  no state.env                    -> seed current/ + state/history
#   resume: state.env AND current/ models   -> continue from the checkpoint
#   repair: state.env but current/ missing  -> refuse with a diagnostic (a
#           checked-in snapshot is not silently resumable).  The directories
#           were created above, so the branches key on the current/ FILES.
BOOT_SOURCES="build/v_win_xgb.json build/v_combat_fair_trees.txt build/policy_fair_trees_c.txt"
BOOT_BRANCH=resume
if [ ! -f "$STATE" ]; then BOOT_BRANCH=fresh
elif [ ! -f "$SP/current/v_win.json" ] || [ ! -f "$SP/current/v_combat_trees.txt" ] || [ ! -f "$SP/current/policy_trees_c.txt" ]; then
    BOOT_BRANCH=repair
fi
case "$BOOT_BRANCH" in
    fresh)
        for f in $BOOT_SOURCES; do
            [ -f "$f" ] || { echo "ERROR: first-run model source missing: $f" >&2; exit 1; }
        done
        cp build/v_win_xgb.json          $SP/current/v_win.json
        cp build/v_combat_fair_trees.txt $SP/current/v_combat_trees.txt
        cp build/policy_fair_trees_c.txt $SP/current/policy_trees_c.txt
        echo "ITER=0"            > $STATE
        echo "SEED_OFF=1000000" >> $STATE
        echo "RUNS_TOTAL=0"     >> $STATE
        printf "iter\truns_total\tbase_win\tmeta_win\tvalue_win\tmeta_promo\tvalue_promo\tts\tbase_floor\tmeta_floor\tvalue_floor\tpolicy_win\tpolicy_promo\tpolicy_floor\n" > $HIST
        echo "=== self-play loop initialized $(date) ===" > $SP/logs/loop.log
        ;;
    resume)
        # state.env exists and current/ looks complete; continue from the checkpoint.
        ;;
    repair)
        # state.env exists but the current/ models it refers to are gone.  The
        # first-run copy branch must NOT be skipped silently (Issue 11): refuse
        # to run and explain the repair options instead.
        echo "ERROR: $STATE exists but $SP/current/ is incomplete; the snapshot cannot resume." >&2
        echo "  Repair options:" >&2
        echo "  1) restore $SP/current/ (v_win.json, v_combat_trees.txt, policy_trees_c.txt) from a backup, or" >&2
        echo "  2) fresh bootstrap: move $STATE and $SP/history.tsv aside, then re-run this script" >&2
        echo "     (a fresh bootstrap copies build/v_win_xgb.json, build/v_combat_fair_trees.txt and" >&2
        echo "      build/policy_fair_trees_c.txt into $SP/current/ and resets ITER/SEED_OFF/RUNS_TOTAL)." >&2
        exit 1
        ;;
esac
echo "bootstrap: $BOOT_BRANCH ($(tr '\n' ' ' < "$STATE"))" >> $SP/logs/loop.log
# record the run config so the dashboard knows the per-iter targets
{ echo "RUNS_PER_ITER=$RUNS_PER_ITER"; echo "SIMS=$SIMS"; echo "META_SIMS=$META_SIMS"; echo "REST_CF_SIMS=$REST_CF_SIMS"; echo "REST_CF_FUTURES=$REST_CF_FUTURES"; echo "REST_CF_STRIDE=$REST_CF_STRIDE"; echo "POLICY_SIMS=$POLICY_SIMS"; echo "GATE_SIMS=$GATE_SIMS"; echo "VNET_TREES=$VNET_TREES"; echo "POLICY_TREES=$POLICY_TREES"; echo "META_RETRAIN_EVERY=$META_RETRAIN_EVERY"; echo "VALUE_RETRAIN_EVERY=$VALUE_RETRAIN_EVERY"; echo "POLICY_RETRAIN_EVERY=$POLICY_RETRAIN_EVERY"; echo "GATE_SEEDS=$GATE_SEEDS"; echo "GATE_INITIAL=$GATE_INITIAL"; echo "GATE_STEP=$GATE_STEP"; echo "GATE_Z=$GATE_Z"; echo "WINDOW=$WINDOW"; echo "META_WINDOW=$META_WINDOW"; echo "REST_WINDOW=$REST_WINDOW"; echo "POLICY_WINDOW=$POLICY_WINDOW"; echo "COMBAT=$COMBAT"; echo "PROMOTE_MARGIN=$PROMOTE_MARGIN"; echo "VALUE_MARGIN=$VALUE_MARGIN"; echo "VALUE_MARGIN_LATENCY=$VALUE_MARGIN_LATENCY"; echo "WIN_WEIGHT=$WIN_WEIGHT"; echo "META_MODE=$META_MODE"; echo "BIN=$BIN"; } > $SP/config.env

set_status() { echo "$1" > "$STATUS"; }

# combat env (STS_VNET/STS_POLICY) for the model files in dir $1; empty if COMBAT=0
cenv_files() { [ "$COMBAT" = 1 ] || { echo ""; return; }
    echo "STS_VNET=$1 STS_VNET_ALPHA=$VNET_ALPHA STS_POLICY=$2"; }
cenv() { cenv_files "$1/v_combat_trees.txt" "$1/policy_trees_c.txt"; }

start_server() {   # $1 = v_win json; optional $2 = paired rest model
    # Liveness check: poll the port; log and return non-zero if the server does
    # not respond within 30s.  Every caller treats a non-zero return as a failed
    # phase, so a silent server cannot produce a valid batch (Issue 01).
    for p in $(pgrep -x python3); do grep -qa v_server.py /proc/$p/cmdline 2>/dev/null && kill $p 2>/dev/null; done
    sleep 1
    # Every self-play arm requires the requested V_win model.  Do not silently
    # continue with card/shop/rest fallbacks if that model is malformed.
    local rest_model=${2:-} rest_required=0
    [ -n "$rest_model" ] && [ -f "$rest_model" ] && rest_required=1 || rest_model=""
    VWIN="$1" VWIN_REQUIRED=1 VREST="$rest_model" VREST_REQUIRED="$rest_required" \
        setsid python3 v_server.py > $SP/logs/vserver.log 2>&1 < /dev/null &
    for _ in $(seq 1 30); do
        python3 -c "import socket,sys;s=socket.socket();s.settimeout(1);sys.exit(0 if s.connect_ex(('127.0.0.1',5555))==0 else 1)" 2>/dev/null && return 0
        sleep 1
    done
    echo "ERROR: v_server did not come up" >> $SP/logs/loop.log; return 1
}
stop_server() { for p in $(pgrep -x python3); do grep -qa v_server.py /proc/$p/cmdline 2>/dev/null && kill $p 2>/dev/null; done; }

# Helpers for the adaptive held-out gate. Training seeds start near 1,000,000;
# gate seeds start at zero and are paired across baseline/candidate arms.
gate_summary() {
    [ -f "$1" ] || { echo "NA NA"; return; }
    awk -F, 'NR>1{n++;w+=$2;f+=$3} END{if(n)printf "%.3f %.3f",100*w/n,f/n;else print "NA NA"}' "$1"
}

# Paired common-seed comparison. Per-seed score exactly matches the aggregate
# blend: floor + WIN_WEIGHT * win_percent, hence a win adds 100*WIN_WEIGHT.
# Output: n baseWin baseFloor candWin candFloor meanDelta SE low high decision.
gate_stats() {
    local margin=${3:-$PROMOTE_MARGIN}
    awk -F, -v ww="$WIN_WEIGHT" -v margin="$margin" -v z="$GATE_Z" '
        NR==FNR {if(FNR>1){b[$1]=$3+100*ww*$2; bw[$1]=$2; bf[$1]=$3} next}
        FNR>1 && ($1 in b) {
            d=($3+100*ww*$2)-b[$1]; n++; sum+=d; ss+=d*d
            bws+=bw[$1]; bfs+=bf[$1]; cws+=$2; cfs+=$3
        }
        END {
            if(n<2){print n,"NA NA NA NA NA NA NA NA continue"; exit}
            mean=sum/n; var=(ss-sum*sum/n)/(n-1); if(var<0)var=0
            se=sqrt(var/n); lo=mean-z*se; hi=mean+z*se
            decision=(lo>margin)?"promote":((hi<=margin)?"reject":"continue")
            printf "%d %.3f %.3f %.3f %.3f %.4f %.4f %.4f %.4f %s\n", \
                   n,100*bws/n,bfs/n,100*cws/n,cfs/n,mean,se,lo,hi,decision
        }' "$1" "$2"
}

# Atomically publish cheap dashboard telemetry. All values are shell-safe tokens.
gate_write_state() {
    local arm=$1 target=$2 tmp=${GATE_STATE}.tmp
    {
        echo "GATE_ITER=$N"; echo "GATE_STATUS=${gate_status:-running}"; echo "GATE_ARM=$arm"
        echo "GATE_TARGET=$target"; echo "GATE_MAX=$GATE_SEEDS"; echo "GATE_LOOKS=${looks:-0}"
        echo "GATE_BASE_CACHE=${gate_base_cache:-unknown}"
        echo "META_DECISION=$meta_decision"; echo "VALUE_DECISION=$value_decision"; echo "POLICY_DECISION=$policy_decision"
        echo "META_N=$meta_n"; echo "META_DELTA=$meta_delta"; echo "META_LOW=$meta_low"; echo "META_HIGH=$meta_high"
        echo "VALUE_N=$value_n"; echo "VALUE_DELTA=$value_delta"; echo "VALUE_LOW=$value_low"; echo "VALUE_HIGH=$value_high"
        echo "POLICY_N=$policy_n"; echo "POLICY_DELTA=$policy_delta"; echo "POLICY_LOW=$policy_low"; echo "POLICY_HIGH=$policy_high"
    } > "$tmp"
    mv "$tmp" "$GATE_STATE"
}

# Run one append-only gate batch for the currently selected server/model env.
run_gate_batch() { # arm offset count cumulative_target results_csv
    local arm=$1 offset=$2 count=$3 target=$4 out=$5
    gate_write_state "$arm" "$target"
    echo "gate $arm: seeds $offset..$((offset+count-1)) (look $target/$GATE_SEEDS)" >> "$SP/logs/gate_${N}.log"
    env $MEAS_POLICY_ENV $MEAS_COMBAT "$BIN" bestbench "$GATE_SIMS" "$count" "$ASC" "$offset" "$out" \
        >> "$SP/logs/gate_${N}.log" 2>&1
}

# Baseline outcomes are ASSUMED deterministic for a fixed executable, deployed model
# stack, policy mode, and evaluation config. The assumption is not re-verified on
# every cache hit (Issue 13). Cache them across iterations; a promotion (or binary/
# config/model change) changes the content key and automatically starts a new cache.
# Candidate rows remain iteration-specific.
baseline_cache_key() {
    {
        printf 'sims=%s\nasc=%s\nmeta_mode=%s\nvnet_alpha=%s\npolicy_env=%s\nmeta_policy_env=%s\n' \
               "$GATE_SIMS" "$ASC" "$META_MODE" "$VNET_ALPHA" "$POLICY_ENV" "$META_POLICY_ENV"
        sha256sum "$BIN" "$SP/current/v_win.json" \
                  "$SP/current/v_combat_trees.txt" "$SP/current/policy_trees_c.txt"
        # Native-OOC gates (baseline/value/policy) also depend on the fixed tracked
        # trees, so hash them too: a tree change must invalidate the cache.
        sha256sum build/v_rich_trees.txt build/v_win_trees.txt
        if [ -f "$SP/current/rest_cf.json" ]; then sha256sum "$SP/current/rest_cf.json"
        else printf 'rest_cf=V_win_fallback\n'; fi
        # Server-backed rows (meta arm) depend on the server implementation.
        # Python dependency versions (pip freeze) are deliberately omitted: the
        # freeze is too expensive to run on every cache-key evaluation.
        sha256sum v_server.py
        # Training-only knobs do not affect held-out play and must not invalidate it.
        env | LC_ALL=C sort | awk -F= '$1 ~ /^STS_/ && $1 != "STS_XGB_DEVICE" && $1 != "STS_POLICY_MAXROWS" {print}'
    } | sha256sum | cut -d' ' -f1
}

gate_csv_count() {
    [ -f "$1" ] || { echo 0; return; }
    awk -F, 'NR>1{seen[$1]=1} END{for(k in seen)n++;print n+0}' "$1"
}

baseline_cache_valid() {
    [ -f "$1" ] || return 0
    awk -F, 'NR>1{
        s=$1+0; if(seen[s]++ || s<0)bad=1; if(n==0||s<mn)mn=s; if(n==0||s>mx)mx=s; n++
    } END{exit !(!bad && (n==0 || (mn==0 && mx==n-1)))}' "$1"
}

ensure_baseline_cache() { # cumulative target, per-iteration baseline CSV
    local target=$1 out=$2 done missing batch combined materialized
    if ! baseline_cache_valid "$BASE_CACHE"; then
        mv "$BASE_CACHE" "${BASE_CACHE}.invalid.iter${N}"
        echo "gate baseline cache invalid; preserved old file and rebuilding" >> "$SP/logs/gate_${N}.log"
    fi
    done=$(gate_csv_count "$BASE_CACHE")
    if [ "$done" -lt "$target" ]; then
        missing=$((target-done)); gate_base_cache=$([ "$done" -eq 0 ] && echo miss || echo grow)
        batch="${BASE_CACHE}.batch.${N}.$$"; combined="${BASE_CACHE}.new.${N}.$$"
        rm -f "$batch" "$combined"
        MEAS_POLICY_ENV=$POLICY_ENV; MEAS_COMBAT=$CUR_COMBAT
        if ! start_server "$SP/current/v_win.json" "$SP/current/rest_cf.json" \
           || ! run_gate_batch baseline "$done" "$missing" "$target" "$batch"; then
            rm -f "$batch" "$combined"; return 1
        fi
        if ! awk -F, -v lo="$done" -v hi="$target" -v want="$missing" '
            NR>1{n++; if($1<lo||$1>=hi||seen[$1]++)bad=1}
            END{exit !(n==want&&!bad)}' "$batch"; then
            echo "gate baseline cache batch validation failed" >> "$SP/logs/gate_${N}.log"
            rm -f "$batch" "$combined"; return 1
        fi
        if [ -f "$BASE_CACHE" ]; then
            { cat "$BASE_CACHE"; tail -n +2 "$batch"; } > "$combined"
        else
            cat "$batch" > "$combined"
        fi
        mv "$combined" "$BASE_CACHE"; rm -f "$batch"
        echo "gate baseline cache $gate_base_cache: now $target seeds ($BASE_CACHE_KEY)" >> "$SP/logs/gate_${N}.log"
    else
        gate_base_cache=hit
        echo "gate baseline cache hit: $target/$done seeds ($BASE_CACHE_KEY)" >> "$SP/logs/gate_${N}.log"
    fi
    materialized="${out}.tmp.$$"
    awk -F, -v hi="$target" 'NR==1 || $1<hi' "$BASE_CACHE" > "$materialized"
    mv "$materialized" "$out"
}

# Distinct seeds already written to a datagen CSV (resume support). OpenMP workers
# can finish out of order, so count alone is NOT a safe resume offset: an interrupted
# 278-run file may already contain seeds above SEED_OFF+277. Return both unique count
# and maximum seed, then append beyond the maximum to guarantee no collisions.
seed_stats() {   # $1 csv -> "distinct_count max_seed" (max=-1 when empty)
    [ -f "$1" ] || { echo "0 -1"; return; }
    awk -F, 'NR==1{for(i=1;i<=NF;i++)if($i=="seed")si=i;next}
             si{s[$si]=1;if($si>mx)mx=$si}
             END{n=0;for(k in s)n++;printf "%d %d\n",n,(n?mx:-1)}' "$1" 2>/dev/null \
        || echo "0 -1"
}

# A marker is authoritative only for the iteration size that created it. Older
# markers were empty; after RUNS_PER_ITER changes they deliberately fall back to
# counting the flushed CSV so the loop generates exactly the missing remainder.
done_for_target() { # marker -> success iff its first field records the current target
    [ -f "$1" ] && [ "$(awk 'NR==1{print $1}' "$1" 2>/dev/null)" = "$RUNS_PER_ITER" ]
}
marker_next_seed() { # marker fallback -> saved collision-free next seed, or fallback for legacy markers
    awk -v fb="$2" 'NR==1{if($2 ~ /^[0-9]+$/)print $2;else print fb;exit}' "$1" 2>/dev/null
}

# concat the last WINDOW iteration CSVs from dir $1 (prefix $2) into $3 (header from first).
# $4 optional low-bound override (defaults to global $lo) so callers can use a smaller window.
cat_window() {   # dir prefix out [lo]
    : > "$3"; local first=1 k f start=${4:-$lo}
    for k in $(seq $start $N); do f="$1/${2}${k}.csv"; [ -f "$f" ] || continue
        if [ $first -eq 1 ]; then cat "$f" > "$3"; first=0; else tail -n +2 "$f" >> "$3"; fi
    done
    echo $(( $(wc -l < "$3") - 1 ))          # data row count
}

echo "=== loop start $(date)  runs/iter=$RUNS_PER_ITER sims=$SIMS window=$WINDOW gate=$GATE_SEEDS combat=$COMBAT ===" >> $SP/logs/loop.log

while :; do
    . $STATE
    if [ "$MAX_ITERS" -gt 0 ] && [ "$ITER" -ge "$MAX_ITERS" ]; then
        set_status "STOPPED: reached MAX_ITERS=$MAX_ITERS at iter $ITER"; break; fi
    N=$ITER; T0=$(date +%s)
    lo=$(( N - WINDOW + 1 )); [ $lo -lt 0 ] && lo=0
    mlo=$(( N - META_WINDOW + 1 )); [ $mlo -lt 0 ] && mlo=0
    CUR_COMBAT=$(cenv $SP/current)

    # ---------- 1. SELF-PLAY DATAGEN (fair play, current stack; RESUMABLE) ----------
    # A killed datagen leaves a valid CSV (per-run flush).  We count runs already
    # done (distinct seeds) and generate only the REMAINDER at a disjoint seed
    # offset (append mode) -> mid-iteration stops lose nothing; complete passes are
    # skipped (also fixes append-dup-on-rerun).  A .done marker skips the rescan.
    dbuf=$SP/buffer/iter_${N}.csv; rbuf=$SP/rbuffer/iter_${N}.csv; dmk=$SP/buffer/iter_${N}.done
    nominal_next=$((SEED_OFF+RUNS_PER_ITER))
    if done_for_target "$dmk"; then
        md=$RUNS_PER_ITER; meta_seed_next=$(marker_next_seed "$dmk" "$nominal_next")
    else
        read md meta_seed_max <<<"$(seed_stats "$dbuf")"
        meta_seed_next=$SEED_OFF
        [ "$meta_seed_max" -ge "$meta_seed_next" ] && meta_seed_next=$((meta_seed_max+1))
    fi
    if [ "$COMBAT" = 1 ]; then
        cmk=$SP/cbuffer/iter_${N}.done
        if done_for_target "$cmk"; then
            cd_=$RUNS_PER_ITER; combat_seed_next=$(marker_next_seed "$cmk" "$nominal_next")
        else read cd_ combat_seed_max <<<"$(seed_stats $SP/cbuffer/iter_${N}.csv)"
             read pd policy_seed_max <<<"$(seed_stats $SP/pbuffer/iter_${N}.csv)"
             [ "$pd" -lt "$cd_" ] && cd_=$pd   # resume from min(value,policy) so neither file skips a run
             combat_seed_next=$SEED_OFF
             [ "$combat_seed_max" -ge "$combat_seed_next" ] && combat_seed_next=$((combat_seed_max+1))
             [ "$policy_seed_max" -ge "$combat_seed_next" ] && combat_seed_next=$((policy_seed_max+1))
        fi
    else cd_=$RUNS_PER_ITER; combat_seed_next=$nominal_next; fi
    set_status "iter $N | [1/3] datagen: meta $md/$RUNS_PER_ITER @${META_SIMS}s$([ $COMBAT = 1 ] && echo ", teacher combat $cd_/$RUNS_PER_ITER @${POLICY_SIMS}s") ..."
    if [ "$md" -lt "$RUNS_PER_ITER" ] || [ "$cd_" -lt "$RUNS_PER_ITER" ]; then
        start_server $SP/current/v_win.json $SP/current/rest_cf.json || { sleep 5; continue; }
    fi
    if [ "$md" -lt "$RUNS_PER_ITER" ]; then
        meta_generate=$((RUNS_PER_ITER-md))
        # Server-backed meta datagen: META_POLICY_ENV carries STS_NATIVE_OOC=0 so
        # the current V_win/rest models in v_server own meta OOC decisions (Issue 01).
        env $META_POLICY_ENV $CUR_COMBAT STS_DG_TEMP=${STS_DG_TEMP:-1.0} \
            "$BIN" datagen3 "$meta_generate" $META_SIMS $ASC $EPS "$dbuf" "$rbuf" \
                "$meta_seed_next" $REST_CF_SIMS $REST_CF_FUTURES $REST_CF_STRIDE \
            >> $SP/logs/datagen_${N}.log 2>&1
        meta_seed_next=$((meta_seed_next+meta_generate))
    fi
    printf '%s %s\n' "$RUNS_PER_ITER" "$meta_seed_next" > "$dmk"
    if [ "$COMBAT" = 1 ]; then
        if [ "$cd_" -lt "$RUNS_PER_ITER" ]; then
            combat_generate=$((RUNS_PER_ITER-cd_))
            # ONE pass emits BOTH value (endHp) + policy (visit-pi) CSVs -> 2x total datagen, not 3x
            env $POLICY_ENV $CUR_COMBAT "$BIN" fightgen "$combat_generate" $POLICY_SIMS $ASC $CEPS \
                $SP/cbuffer/iter_${N}.csv $SP/pbuffer/iter_${N}.csv "$combat_seed_next" >> $SP/logs/fightgen_${N}.log 2>&1
            combat_seed_next=$((combat_seed_next+combat_generate))
        fi
        printf '%s %s\n' "$RUNS_PER_ITER" "$combat_seed_next" > "$cmk"
    fi

    # ---------- 2. RETRAIN all heads on their replay windows ----------
    set_status "iter $N | [2/3] retrain (V_win$([ $COMBAT = 1 ] && echo +vnet+prior)) ..."
    meta_trained=no; rest_trained=no; value_trained=no; policy_trained=no
    meta_error=no; combat_error=no
    rm -f $SP/cand/rest_cf.json
    [ -f $SP/current/rest_cf.json ] && cp $SP/current/rest_cf.json $SP/cand/rest_cf.json
    # -- META: V_win (binary; needs both classes), on configured cadence --
    if [ $((N % META_RETRAIN_EVERY)) -eq 0 ]; then
        TR=$SP/buffer/_train.csv; NTOT=$(cat_window $SP/buffer iter_ $TR $mlo)
        WI=$(head -1 $TR | tr ',' '\n' | grep -n '^won$' | cut -d: -f1)
        NWIN=$(tail -n +2 $TR | awk -F, -v i="${WI:-0}" '$i==1{c++} END{print c+0}')
        CANDW=$SP/models/v_win_iter${N}.json
        # XGBoost chooses its serialization format from the final extension.  A
        # "$CANDW.tmp" path becomes UBJSON and must not later be renamed to .json.
        CANDW_TMP=$SP/models/v_win_iter${N}.tmp.json
        if [ "${WI:-0}" -gt 0 ] && [ "$NWIN" -ge 20 ] && [ "$NWIN" -lt "$NTOT" ]; then
            if python3 train_winrate.py "$TR" "$CANDW_TMP" >> $SP/logs/train_${N}.log 2>&1; then
                mv "$CANDW_TMP" "$CANDW"; cp "$CANDW" $SP/cand/v_win.json; meta_trained=yes
            else
                rm -f "$CANDW_TMP"; cp $SP/current/v_win.json $SP/cand/v_win.json
                meta_error=yes
                echo "iter $N: V_win training FAILED; iteration will retry" >> $SP/logs/loop.log
            fi
        else
            cp $SP/current/v_win.json $SP/cand/v_win.json
            echo "iter $N: V_win retrain skipped (wins=$NWIN/$NTOT)" >> $SP/logs/loop.log
        fi
    else
        cp $SP/current/v_win.json $SP/cand/v_win.json
        echo "iter $N: V_win retrain skipped by cadence (every $META_RETRAIN_EVERY iterations)" >> $SP/logs/loop.log
    fi
    # -- META action value: direct paired rest-vs-smith counterfactual target --
    if [ $((N % META_RETRAIN_EVERY)) -eq 0 ]; then
        rlo=$(( N - REST_WINDOW + 1 )); [ $rlo -lt 0 ] && rlo=0
        RTR=$SP/rbuffer/_train.csv; RROWS=$(cat_window $SP/rbuffer iter_ $RTR $rlo)
        if [ "$RROWS" -ge 100 ]; then
            REST_WIN_BONUS=$(awk -v w="$WIN_WEIGHT" 'BEGIN{print 100*w}')
            if STS_REST_WIN_BONUS=$REST_WIN_BONUS python3 train_rest_cf.py "$RTR" \
               $SP/models/rest_cf_iter${N}.json >> $SP/logs/rtrain_${N}.log 2>&1; then
                cp $SP/models/rest_cf_iter${N}.json $SP/cand/rest_cf.json
                rest_trained=yes; meta_trained=yes
            else
                meta_error=yes
                echo "iter $N: paired rest training FAILED; iteration will retry" >> $SP/logs/loop.log
            fi
        else
            echo "iter $N: paired rest retrain skipped (rows=$RROWS)" >> $SP/logs/loop.log
        fi
    fi
    if [ "$COMBAT" = 1 ]; then
        # -- COMBAT value net (regression endHp), accumulated on a slower cadence --
        if [ $((N % VALUE_RETRAIN_EVERY)) -eq 0 ]; then
            CTR=$SP/cbuffer/_train.csv; CROWS=$(cat_window $SP/cbuffer iter_ $CTR)
            if [ "$CROWS" -ge 500 ]; then
                CVAL=$SP/models/v_combat_val_iter${N}.csv
                if python3 train_value_combat.py $CTR $SP/models/v_combat_iter${N}.json $SP/pbuffer/iter_${N}.csv >> $SP/logs/vtrain_${N}.log 2>&1 \
                   && python3 export_combat_model.py $SP/models/v_combat_iter${N}.json $SP/cand/v_combat_trees.txt $CTR $CVAL $VNET_TREES >> $SP/logs/vtrain_${N}.log 2>&1; then
                    value_trained=yes
                else
                    cp $SP/current/v_combat_trees.txt $SP/cand/v_combat_trees.txt
                    combat_error=yes
                    echo "iter $N: vnet training FAILED; iteration will retry" >> $SP/logs/loop.log
                fi
            else
                cp $SP/current/v_combat_trees.txt $SP/cand/v_combat_trees.txt
                echo "iter $N: vnet retrain skipped (rows=$CROWS)" >> $SP/logs/loop.log
            fi
        else
            cp $SP/current/v_combat_trees.txt $SP/cand/v_combat_trees.txt
            echo "iter $N: vnet retrain skipped by cadence (every $VALUE_RETRAIN_EVERY iterations)" >> $SP/logs/loop.log
        fi
        # -- COMBAT policy prior (PUCT comparator) --
        if [ "$POLICY_RETRAIN" = 1 ] && [ $((N % POLICY_RETRAIN_EVERY)) -eq 0 ]; then
            plo=$(( N - POLICY_WINDOW + 1 )); [ $plo -lt 0 ] && plo=0
            PTR=$SP/pbuffer/_train.csv; PROWS=$(cat_window $SP/pbuffer iter_ $PTR $plo)
            if [ "$PROWS" -ge 500 ]; then
                if STS_POLICY_TREES=$POLICY_TREES python3 train_policy.py $PTR $SP/models/policy_iter${N}.json $SP/cand/policy_trees_c.txt >> $SP/logs/ptrain_${N}.log 2>&1; then
                    policy_trained=yes
                else
                    cp $SP/current/policy_trees_c.txt $SP/cand/policy_trees_c.txt
                    combat_error=yes
                    echo "iter $N: policy training FAILED; iteration will retry" >> $SP/logs/loop.log
                fi
            else
                cp $SP/current/policy_trees_c.txt $SP/cand/policy_trees_c.txt
                echo "iter $N: policy retrain skipped (rows=$PROWS)" >> $SP/logs/loop.log
            fi
        else
            cp $SP/current/policy_trees_c.txt $SP/cand/policy_trees_c.txt
            [ "$POLICY_RETRAIN" = 1 ] && echo "iter $N: policy retrain skipped by cadence (every $POLICY_RETRAIN_EVERY iterations)" >> $SP/logs/loop.log
        fi
    fi
    if [ "$meta_error" = yes ] || [ "$combat_error" = yes ]; then
        set_status "iter $N | [2/3] training error; iteration NOT checkpointed, retrying ..."
        sleep 30
        continue
    fi

    # ---------- 3. ADAPTIVE PAIRED GATES: META, VALUE, POLICY independently ----------
    # Evaluate common held-out seeds in batches. Clear regressions stop after the
    # first look; ambiguous candidates extend to GATE_SEEDS. Promotion requires the
    # conservative lower confidence bound of paired per-seed score deltas to beat
    # PROMOTE_MARGIN, but ONLY on the final hard-cap look (multiplicity guard, see
    # the gate loop below). Faster value nets use VALUE_MARGIN as a non-inferiority bar.
    set_status "iter $N | [3/3] adaptive paired gate (first $GATE_INITIAL, max $GATE_SEEDS seeds) ..."
    base_csv=$GATE_DIR/iter_${N}_base.csv
    meta_csv=$GATE_DIR/iter_${N}_meta.csv
    value_csv=$GATE_DIR/iter_${N}_value.csv
    policy_csv=$GATE_DIR/iter_${N}_policy.csv
    rm -f "$base_csv" "$meta_csv" "$value_csv" "$policy_csv" "$GATE_STATE"
    : > "$SP/logs/gate_${N}.log"

    meta_decision=not_trained; [ "$meta_trained" = yes ] && meta_decision=continue
    value_decision=disabled; policy_decision=disabled
    [ "$COMBAT" = 1 ] && value_decision=not_trained
    [ "$COMBAT" = 1 ] && policy_decision=not_trained
    [ "$COMBAT" = 1 ] && [ "$value_trained" = yes ] && value_decision=continue
    [ "$COMBAT" = 1 ] && [ "$policy_trained" = yes ] && policy_decision=continue
    meta_n=0; meta_delta=NA; meta_low=NA; meta_high=NA
    value_n=0; value_delta=NA; value_low=NA; value_high=NA
    policy_n=0; policy_delta=NA; policy_low=NA; policy_high=NA
    meta_bw=NA; meta_bf=NA; mw=NA; mf=NA
    value_bw=NA; value_bf=NA; vw=NA; vf=NA
    policy_bw=NA; policy_bf=NA; pw=NA; pf=NA
    gate_status=running; gate_done=0; stage=$GATE_INITIAL; gate_step=$GATE_STEP; looks=0
    gate_base_cache=unknown
    BASE_CACHE_KEY=$(baseline_cache_key)
    BASE_CACHE=$BASE_CACHE_DIR/${BASE_CACHE_KEY}.csv
    [ "$gate_step" -lt 1 ] && gate_step=1
    [ "$stage" -lt 2 ] && stage=2
    [ "$stage" -gt "$GATE_SEEDS" ] && stage=$GATE_SEEDS

    while [ "$meta_decision" = continue ] || [ "$value_decision" = continue ] || [ "$policy_decision" = continue ]; do
        looks=$((looks+1))
        batch=$((stage-gate_done))

        # Shared baseline: deterministic and cached while the deployed stack stays fixed.
        if ! ensure_baseline_cache "$stage" "$base_csv"; then
            [ "$meta_decision" = continue ] && meta_decision=error
            [ "$value_decision" = continue ] && value_decision=error
            [ "$policy_decision" = continue ] && policy_decision=error
            echo "iter $N: baseline gate batch failed" >> $SP/logs/loop.log
            break
        fi

        # META candidate + current combat, within the proven hybrid policy:
        # V_floor continues to own card/shop choices and candidate V_win is tested
        # only for rest decisions. Unified card/shop control is a separate ablation,
        # never an automatic graduation side effect of a rest-model promotion.
        if [ "$meta_decision" = continue ]; then
            MEAS_POLICY_ENV=$META_POLICY_ENV; MEAS_COMBAT=$CUR_COMBAT
            # Intended flow: META_POLICY_ENV carries STS_NATIVE_OOC=0, so every
            # V_win/rest decision in this batch is served by v_server from the
            # CANDIDATE models ($SP/cand/*); the fixed native trees are bypassed.
            # start_server polls the port and this batch errors out (above) if
            # the server never responds (Issue 01).
            echo "gate meta: server-backed candidate V_win/rest owns OOC decisions (STS_NATIVE_OOC=0); native trees bypassed" >> "$SP/logs/gate_${N}.log"
            if ! start_server $SP/cand/v_win.json $SP/cand/rest_cf.json \
               || ! run_gate_batch meta "$gate_done" "$batch" "$stage" "$meta_csv"; then
                meta_decision=error
                echo "iter $N: meta gate batch failed" >> $SP/logs/loop.log
            else
                read meta_n meta_bw meta_bf mw mf meta_delta meta_se meta_low meta_high meta_decision \
                    <<<"$(gate_stats "$base_csv" "$meta_csv")"
                echo "gate meta look $stage: n=$meta_n delta=$meta_delta se=$meta_se CI=[$meta_low,$meta_high] decision=$meta_decision" \
                    >> "$SP/logs/gate_${N}.log"
            fi
        fi

        # Candidate 400-tree combat VALUE with the deployed policy held fixed.
        if [ "$value_decision" = continue ]; then
            MEAS_POLICY_ENV=$POLICY_ENV
            MEAS_COMBAT=$(cenv_files "$SP/cand/v_combat_trees.txt" "$SP/current/policy_trees_c.txt")
            if ! start_server $SP/current/v_win.json $SP/current/rest_cf.json \
               || ! run_gate_batch value "$gate_done" "$batch" "$stage" "$value_csv"; then
                value_decision=error
                echo "iter $N: value gate batch failed" >> $SP/logs/loop.log
            else
                read value_n value_bw value_bf vw vf value_delta value_se value_low value_high value_decision \
                    <<<"$(gate_stats "$base_csv" "$value_csv" "$VALUE_MARGIN")"
                echo "gate value look $stage: n=$value_n delta=$value_delta se=$value_se CI=[$value_low,$value_high] decision=$value_decision" \
                    >> "$SP/logs/gate_${N}.log"
            fi
        fi

        # Candidate compact POLICY with the deployed combat value held fixed.
        if [ "$policy_decision" = continue ]; then
            MEAS_POLICY_ENV=$POLICY_ENV
            MEAS_COMBAT=$(cenv_files "$SP/current/v_combat_trees.txt" "$SP/cand/policy_trees_c.txt")
            if ! start_server $SP/current/v_win.json $SP/current/rest_cf.json \
               || ! run_gate_batch policy "$gate_done" "$batch" "$stage" "$policy_csv"; then
                policy_decision=error
                echo "iter $N: policy gate batch failed" >> $SP/logs/loop.log
            else
                read policy_n policy_bw policy_bf pw pf policy_delta policy_se policy_low policy_high policy_decision \
                    <<<"$(gate_stats "$base_csv" "$policy_csv")"
                echo "gate policy look $stage: n=$policy_n delta=$policy_delta se=$policy_se CI=[$policy_low,$policy_high] decision=$policy_decision" \
                    >> "$SP/logs/gate_${N}.log"
            fi
        fi

        # Sequential multiplicity guard (Issue 15): each adaptive look re-tests
        # the same accumulating data, so a "promote" signal before the final
        # hard-cap look is only advisory and is downgraded to continue. Promotion
        # is allowed ONLY on the hard-cap look (stage >= GATE_SEEDS); early
        # rejection stays decisive (conservative direction, no type-I inflation).
        if [ "$stage" -lt "$GATE_SEEDS" ]; then
            if [ "$meta_decision" = promote ]; then
                meta_decision=continue
                echo "gate meta look $stage: promote signal advisory (multiplicity guard); deferred to hard cap" >> "$SP/logs/gate_${N}.log"
            fi
            if [ "$value_decision" = promote ]; then
                value_decision=continue
                echo "gate value look $stage: promote signal advisory (multiplicity guard); deferred to hard cap" >> "$SP/logs/gate_${N}.log"
            fi
            if [ "$policy_decision" = promote ]; then
                policy_decision=continue
                echo "gate policy look $stage: promote signal advisory (multiplicity guard); deferred to hard cap" >> "$SP/logs/gate_${N}.log"
            fi
        fi

        # At the hard cap, an inconclusive candidate is rejected rather than promoted
        # on a noisy point estimate. Otherwise publish decisions and take another look.
        if [ "$stage" -ge "$GATE_SEEDS" ]; then
            [ "$meta_decision" = continue ] && meta_decision=reject_inconclusive
            [ "$value_decision" = continue ] && value_decision=reject_inconclusive
            [ "$policy_decision" = continue ] && policy_decision=reject_inconclusive
        fi
        gate_write_state decision "$stage"
        if [ "$meta_decision" != continue ] && [ "$value_decision" != continue ] && [ "$policy_decision" != continue ]; then break; fi
        gate_done=$stage
        stage=$((stage+gate_step)); [ "$stage" -gt "$GATE_SEEDS" ] && stage=$GATE_SEEDS
    done
    stop_server
    if [ "$meta_decision" = error ] || [ "$value_decision" = error ] || [ "$policy_decision" = error ]; then
        gate_status=error; gate_write_state error "$stage"
        set_status "iter $N | [3/3] gate error; iteration NOT checkpointed, retrying ..."
        sleep 5
        continue
    fi
    gate_status=done; gate_write_state done "$stage"

    read rw rf <<<"$(gate_summary "$base_csv")"
    read mw mf <<<"$(gate_summary "$meta_csv")"
    read vw vf <<<"$(gate_summary "$value_csv")"
    read pw pf <<<"$(gate_summary "$policy_csv")"
    meta_promo=no; value_promo=no; policy_promo=no
    if [ "$meta_trained" = yes ] && [ "$meta_decision" = promote ]; then
        cp $SP/cand/v_win.json $SP/current/v_win.json.tmp && mv $SP/current/v_win.json.tmp $SP/current/v_win.json
        if [ -f $SP/cand/rest_cf.json ]; then
            cp $SP/cand/rest_cf.json $SP/current/rest_cf.json.tmp \
                && mv $SP/current/rest_cf.json.tmp $SP/current/rest_cf.json
        fi
        meta_promo=yes
    fi
    if [ "$COMBAT" = 1 ] && [ "$value_trained" = yes ] && [ "$value_decision" = promote ]; then
        cp $SP/cand/v_combat_trees.txt $SP/current/v_combat_trees.txt.tmp \
            && mv $SP/current/v_combat_trees.txt.tmp $SP/current/v_combat_trees.txt
        value_promo=yes
    fi
    if [ "$COMBAT" = 1 ] && [ "$policy_trained" = yes ] && [ "$policy_decision" = promote ]; then
        if [ "$value_promo" = yes ]; then
            # Both arms were measured against the old deployed stack; combining them
            # without a paired gate would be an untested interaction. Re-gate policy
            # next iteration against the newly promoted value instead.
            policy_promo=deferred
            echo "iter $N: policy promotion deferred after simultaneous value promotion" >> $SP/logs/loop.log
        else
            cp $SP/cand/policy_trees_c.txt $SP/current/policy_trees_c.txt.tmp \
                && mv $SP/current/policy_trees_c.txt.tmp $SP/current/policy_trees_c.txt
            policy_promo=yes
        fi
    fi

    # ---------- 4. checkpoint (resumable) ----------
    printf "%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$N" "$((RUNS_TOTAL+RUNS_PER_ITER))" \
           "$rw" "$mw" "$vw" "$meta_promo" "$value_promo" "$(date +%H:%M)" "$rf" "$mf" "$vf" "$pw" "$policy_promo" "$pf" >> $HIST
    next_seed=$nominal_next
    [ "$meta_seed_next" -gt "$next_seed" ] && next_seed=$meta_seed_next
    [ "$combat_seed_next" -gt "$next_seed" ] && next_seed=$combat_seed_next
    { echo "ITER=$((N+1))"; echo "SEED_OFF=$next_seed"; echo "RUNS_TOTAL=$((RUNS_TOTAL+RUNS_PER_ITER))"; } > $STATE
    dt=$(( $(date +%s) - T0 ))
    echo "iter $N done in ${dt}s: base=$rw/${rf}f meta=$mw/${mf}f($meta_decision, promo $meta_promo) value=$vw/${vf}f($value_decision, promo $value_promo) policy=$pw/${pf}f($policy_decision, promo $policy_promo)" >> $SP/logs/loop.log
    set_status "iter $N done (${dt}s): base=${rw}%/${rf}f meta=${mw}%/${mf}f/$meta_promo value=${vw}%/${vf}f/$value_promo policy=${pw}%/${pf}f/$policy_promo"
done
