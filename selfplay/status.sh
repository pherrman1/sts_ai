#!/usr/bin/env bash
# Console dashboard for the self-play loop.  Live:  watch -n2 selfplay/status.sh
cd "$(dirname "$0")/.."
SP=selfplay
B=$'\e[1m'; G=$'\e[32m'; Y=$'\e[33m'; C=$'\e[36m'; R=$'\e[31m'; D=$'\e[2m'; Z=$'\e[0m'

echo "${B}${C}=== SELF-PLAY TRAINING ===${Z}   $(date '+%H:%M:%S')"
[ -f $SP/state.env ] || { echo "  (not initialized — run selfplay/loop.sh)"; exit 0; }
. $SP/state.env
RUNS_PER_ITER=2000; SIMS=?; META_SIMS=?; POLICY_SIMS=?; REST_CF_SIMS=?; REST_CF_STRIDE=?
GATE_SIMS=?; GATE_SEEDS=?; GATE_INITIAL=?; WINDOW=?; META_WINDOW=?; COMBAT=1; POLICY_TREES=?
PROMOTE_MARGIN=0.5; VALUE_MARGIN=0.5; WIN_WEIGHT=0.1
[ -f $SP/config.env ] && . $SP/config.env

# Distinct-run count + win% + avg final floor from a datagen CSV. Combat
# buffers don't carry finalFloor, so the fourth field is NA for those.
probe() {  # $1 = csv
    [ -f "$1" ] || { echo "0 0 0 NA"; return; }
    awk -F, 'NR==1{for(i=1;i<=NF;i++){if($i=="seed")si=i;if($i=="won")wi=i;if($i=="finalFloor")fi=i}next}
        si&&wi{w[$si]=$wi;if(fi)fl[$si]=$fi} END{
        n=0;win=0;fs=0;fn=0;for(s in w){n++;if(w[s]==1)win++;if(s in fl){fs+=fl[s];fn++}}
        printf "%d %d %.1f %s",n,win,(n?100*win/n:0),(fn?sprintf("%.1f",fs/fn):"NA")}' "$1" 2>/dev/null
}
gate_probe() { # $1 = per-seed gate CSV -> count win% avg_floor
    [ -f "$1" ] || { echo "0 0 NA"; return; }
    awk -F, 'NR>1{n++;w+=$2;f+=$3} END{printf "%d %.1f %s",n,(n?100*w/n:0),(n?sprintf("%.1f",f/n):"NA")}' "$1" 2>/dev/null
}
rest_probe() { # $1 = paired-rest CSV -> distinct source runs, decision rows
    [ -f "$1" ] || { echo "0 0"; return; }
    awk -F, 'NR==1{for(i=1;i<=NF;i++)if($i=="seed")si=i;next}
        si{seen[$si]=1;n++} END{for(s in seen)r++;printf "%d %d",r+0,n+0}' "$1" 2>/dev/null
}
bar() {  # $1 done $2 total  -> [####----] pct%
    local d=$1 t=$2 p=0 f i s=""; [ "$t" -gt 0 ] && p=$((100*d/t)); f=$((p/5))
    for ((i=0;i<20;i++)); do [ $i -lt $f ] && s+="#" || s+="-"; done
    printf "[%s] %d%%" "$s" "$p"
}

if pgrep -f "bash .*selfplay/loop.sh" >/dev/null 2>&1 || pgrep -f "selfplay/loop.sh" >/dev/null; then
    run="${G}running${Z}"; else run="${Y}stopped${Z}"; fi
echo "  loop: $run    ${B}iter $ITER${Z}    total runs ${B}${RUNS_TOTAL}${Z}    next seed $SEED_OFF"
echo "  ${D}budgets: deploy ${SIMS} sims | teacher ${POLICY_SIMS} | meta ${META_SIMS} | paired rest ${REST_CF_SIMS} on 1/${REST_CF_STRIDE} runs | gate ${GATE_SIMS}${Z}"
phase=""; [ -f $SP/status.txt ] && phase=$(cat $SP/status.txt)
[ -n "$phase" ] && echo "  ${Y}phase:${Z} $phase"

# --- adaptive gate progress (per-seed files are small, so this is cheap) ---
if [ -f $SP/gate/progress.env ] && [[ "$phase" == *"[3/3]"* ]]; then
    . $SP/gate/progress.env
    if [ "${GATE_ITER:-x}" = "$ITER" ]; then
        read gBN gBW gBF <<<"$(gate_probe $SP/gate/iter_${ITER}_base.csv)"
        read gMN gMW gMF <<<"$(gate_probe $SP/gate/iter_${ITER}_meta.csv)"
        read gVN gVW gVF <<<"$(gate_probe $SP/gate/iter_${ITER}_value.csv)"
        read gPN gPW gPF <<<"$(gate_probe $SP/gate/iter_${ITER}_policy.csv)"
        echo
        echo "  ${B}adaptive gate${Z}   look ${GATE_TARGET:-?}/${GATE_MAX:-?} seeds   active ${C}${GATE_ARM:-?}${Z}   baseline cache ${GATE_BASE_CACHE:-?}"
        printf "  %-14s %s   %s/%s   win %s%%   avg floor %s\n" baseline \
               "$(bar ${gBN:-0} ${GATE_TARGET:-1})" "${gBN:-0}" "${GATE_TARGET:-?}" "${gBW:-0}" "${gBF:-NA}"
        printf "  %-14s %s   %s/%s   win %s%%   avg floor %s   %s\n" meta \
               "$(bar ${gMN:-0} ${GATE_TARGET:-1})" "${gMN:-0}" "${GATE_TARGET:-?}" "${gMW:-0}" "${gMF:-NA}" "${META_DECISION:-pending}"
        if [ "$COMBAT" = 1 ]; then
            printf "  %-14s %s   %s/%s   win %s%%   avg floor %s   %s\n" value \
                   "$(bar ${gVN:-0} ${GATE_TARGET:-1})" "${gVN:-0}" "${GATE_TARGET:-?}" "${gVW:-0}" "${gVF:-NA}" "${VALUE_DECISION:-pending}"
            printf "  %-14s %s   %s/%s   win %s%%   avg floor %s   %s\n" policy \
                   "$(bar ${gPN:-0} ${GATE_TARGET:-1})" "${gPN:-0}" "${GATE_TARGET:-?}" "${gPW:-0}" "${gPF:-NA}" "${POLICY_DECISION:-pending}"
        fi
        [ "${META_DELTA:-NA}" != NA ] && echo "  ${D}meta score delta ${META_DELTA}, CI [${META_LOW}, ${META_HIGH}] (need > ${PROMOTE_MARGIN})${Z}"
        [ "${VALUE_DELTA:-NA}" != NA ] && echo "  ${D}value score delta ${VALUE_DELTA}, CI [${VALUE_LOW}, ${VALUE_HIGH}] (need > ${VALUE_MARGIN}, non-inferiority)${Z}"
        [ "${POLICY_DELTA:-NA}" != NA ] && echo "  ${D}policy score delta ${POLICY_DELTA}, CI [${POLICY_LOW}, ${POLICY_HIGH}] (need > ${PROMOTE_MARGIN})${Z}"
    fi
fi

# --- live per-pass progress for the CURRENT iteration ---
echo
read mN mW mP mF <<<"$(probe $SP/buffer/iter_${ITER}.csv)"
# A completed combat CSV is hundreds of MB. Its .done marker is authoritative;
# rescanning it every two seconds (and sometimes from several watch terminals)
# wastes a full CPU and heavy disk bandwidth merely to rediscover 500/500.
combat_marker_target=$(awk 'NR==1{print $1}' "$SP/cbuffer/iter_${ITER}.done" 2>/dev/null)
if [[ "$combat_marker_target" =~ ^[0-9]+$ ]]; then
    cN=$combat_marker_target; cW=NA; cP=NA; cF=NA
else
    read cN cW cP cF <<<"$(probe $SP/cbuffer/iter_${ITER}.csv)"
fi
read rN rRows <<<"$(rest_probe $SP/rbuffer/iter_${ITER}.csv)"
printf "  ${B}meta datagen${Z}   %s   %s/%s runs   win ${G}%s%%${Z} (%s/%s)   avg floor ${B}%s${Z}\n" \
       "$(bar ${mN:-0} $RUNS_PER_ITER)" "${mN:-0}" "$RUNS_PER_ITER" "${mP:-0}" "${mW:-0}" "${mN:-0}" "${mF:-NA}"
if [ "$COMBAT" = 1 ]; then
    printf "  ${B}teacher combat${Z} %s   %s/%s runs   win ${G}%s%%${Z} (%s/%s)  ${D}(value+policy @%s sims)${Z}\n" \
       "$(bar ${cN:-0} $RUNS_PER_ITER)" "${cN:-0}" "$RUNS_PER_ITER" "${cP:-NA}" "${cW:-NA}" "${cN:-0}" "$POLICY_SIMS"
fi
printf "  ${B}paired rest${Z}    %s source runs   %s rest/smith decisions  ${D}(%s sims/branch)${Z}\n" \
       "${rN:-0}" "${rRows:-0}" "$REST_CF_SIMS"
# time in the current phase (status.txt is rewritten at each phase transition)
if [ -f $SP/status.txt ]; then
    el=$(( $(date +%s) - $(stat -c %Y $SP/status.txt 2>/dev/null || date +%s) ))
    echo "  ${D}in this phase ~${el}s${Z}"
fi

# --- promotion history + win% trend ---
if [ -f $SP/history.tsv ] && [ "$(wc -l < $SP/history.tsv)" -gt 1 ]; then
    echo
    printf "  ${B}%-4s %-8s %-16s %-20s %-20s %-20s %s${Z}\n" it runs 'base win/floor' meta value policy at
    tail -n +2 $SP/history.tsv | tail -n 10 | awk -F'\t' -v g="$G" -v y="$Y" -v z="$Z" '{
        mp=($6=="yes")?g"^"z:y"."z; vp=($7=="yes")?g"^"z:y"."z; pp=($13=="yes")?g"^"z:y"."z;
        bf=($9==""?"NA":$9); mf=($10==""?"NA":$10); vf=($11==""?"NA":$11); pf=($14==""?"NA":$14);
        printf "  %-4s %-8s %-16s %-13s %s  %-13s %s  %-13s %s  %s\n",$1,$2,$3"%/"bf"f",$4"%/"mf"f",mp,$5"%/"vf"f",vp,($12==""?"NA":$12)"%/"pf"f",pp,$8}'
    # current stack strength = last row's best of {base, promoted meta, promoted combat}
    # (each side gated holding the other at current; a promoted side lifted the stack to
    # at least its measured win%). base_win alone under-reports after a promotion.
    read cur curFloor bestever <<<"$(awk -F'\t' -v ww="${WIN_WEIGHT:-0.1}" '
        function num(x){return x ~ /^-?[0-9]+([.][0-9]+)?$/}
        NR>1{
            w=$3; f=$9; score=num(w)?(num(f)?f+ww*w:ww*w):-1e9
            ms=num($4)?(num($10)?$10+ww*$4:ww*$4):-1e9
            cs=num($5)?(num($11)?$11+ww*$5:ww*$5):-1e9
            if($6=="yes"&&ms>score){w=$4;f=$10;score=ms}
            if($7=="yes"&&cs>score){w=$5;f=$11;score=cs}
            ps=num($12)?(num($14)?$14+ww*$12:ww*$12):-1e9
            if($13=="yes"&&ps>score){w=$12;f=$14;score=ps}
            cur=w; curf=f; if(num(w)&&w>be)be=w
        } END{printf "%s %s %.1f",cur,(num(curf)?sprintf("%.1f",curf):"NA"),be}' $SP/history.tsv)"
    echo
    echo "  ${B}current stack (held-out gate):${Z} win ${G}${cur:-NA}%${Z}   avg floor ${B}${curFloor:-NA}${Z}   best-ever win ${bestever:-NA}%   ${D}^=promoted${Z}"
else
    echo; echo "  ${D}(first iteration in progress — history appears after it completes)${Z}"
fi
