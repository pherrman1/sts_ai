#!/usr/bin/env bash
set -uo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: run_balanced_wave.sh WAVE START_SEED PAIR_COUNT" >&2
  exit 2
fi

wave="$1"
start_seed="$2"
pair_count="$3"
case "$wave:$start_seed:$pair_count" in
  1:976032:12|2:976044:12|3:976056:8) ;;
  *) echo "refusing undeclared wave $wave:$start_seed:$pair_count" >&2; exit 2 ;;
esac

root=/home/philippherrmann/sts_sweep
checkout="$root/checkouts/silver-visit-prior-grouped-repair-screen-976032-976063"
binary="$checkout/build/linux-gcc-release/one_combat"
model="$checkout/models/silver_rank4_visit_policy_runtime_v1.bin"
git_dir="$root/.git/worktrees/silver-visit-prior-grouped-repair-screen-976032-976063"
run_id=silver-visit-prior-grouped-repair-screen-976032-976063-attempt3
results_dir="$root/results/$run_id"
logs_dir="$root/logs/$run_id"
mkdir -p "$results_dir" "$logs_dir"

declare -a pids labels
wave_start_ns="$(date +%s%N)"
for ((offset=0; offset<pair_count; ++offset)); do
  seed=$((start_seed + offset))
  for mode in off grouped; do
    stem="${mode}_${seed}"
    result="$results_dir/${stem}.csv"
    log="$logs_dir/${stem}.log"
    timing="$logs_dir/${stem}.time"
    if [[ -e "$result" || -e "$result.meta.json" || -e "$log" || -e "$timing" ]]; then
      echo "refusing existing output for $stem" >&2
      exit 3
    fi
    policy_env=(STS_SILVER_VISIT_POLICY="$mode")
    if [[ "$mode" == grouped ]]; then
      policy_env+=(STS_SILVER_VISIT_POLICY_MODEL="$model")
    fi
    (
      process_start_ns="$(date +%s%N)"
      env \
          OMP_NUM_THREADS=1 \
          OPENBLAS_NUM_THREADS=1 \
          MKL_NUM_THREADS=1 \
          OMP_DYNAMIC=FALSE \
          GIT_DIR="$git_dir" \
          GIT_WORK_TREE="$checkout" \
          STS_EXECUTABLE_GIT_SHA=0a8ec2087d5af7e9fec53323e84e5dc36a003f44 \
          STS_FAIR=1 \
          STS_COLLECT_KEYS=0 \
          STS_STOP_AFTER_ACT=3 \
          STS_SILVER_SEARCH=1 \
          STS_SILVER_REUSE_CAP_MODE=allocated \
          STS_SILVER_EXACT_ROOT_BUDGETS=1 \
          STS_SILVER_TELEMETRY=1 \
          STS_EXPERIMENT_ARM="$mode" \
          STS_EXPERIMENT_WAVE="$wave" \
          STS_EXPERIMENT_SOURCE_NPZ_SHA256=a9f4ba81b200ec7ac7510970e7279ba7b46b1a0f53af521e5bebb98eba3986cf \
          "${policy_env[@]}" \
          "$checkout/tools/seed_guard.sh" --gcp-research \
          "$binary" bestbench 1000 1 0 "$seed" "$result" >"$log" 2>&1
      rc=$?
      process_end_ns="$(date +%s%N)"
      printf 'start_ns=%s\nend_ns=%s\nwall_seconds=%s\nexit_code=%s\n' \
        "$process_start_ns" "$process_end_ns" \
        "$(( (process_end_ns - process_start_ns) / 1000000000 ))" "$rc" > "$timing"
      exit "$rc"
    ) &
    pids+=("$!")
    labels+=("$stem")
  done
done

if (( ${#pids[@]} > 24 )); then
  echo "internal error: launched ${#pids[@]} processes" >&2
  exit 4
fi

status_file="$logs_dir/wave_${wave}_status.tsv"
: > "$status_file"
failed=0
for i in "${!pids[@]}"; do
  if wait "${pids[$i]}"; then
    printf '%s\t0\n' "${labels[$i]}" >> "$status_file"
  else
    rc=$?
    printf '%s\t%d\n' "${labels[$i]}" "$rc" >> "$status_file"
    failed=1
  fi
done
wave_end_ns="$(date +%s%N)"
printf 'wave=%s\nstart_seed=%s\npair_count=%s\nprocess_count=%s\nstart_ns=%s\nend_ns=%s\nwall_seconds=%s\nfailed=%s\n' \
  "$wave" "$start_seed" "$pair_count" "${#pids[@]}" "$wave_start_ns" "$wave_end_ns" \
  "$(( (wave_end_ns - wave_start_ns) / 1000000000 ))" "$failed" \
  > "$logs_dir/wave_${wave}_summary.txt"
exit "$failed"
