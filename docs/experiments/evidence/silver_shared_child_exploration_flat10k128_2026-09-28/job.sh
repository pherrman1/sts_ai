#!/usr/bin/env bash
arm=$1; off=$2; x=""
[ "$arm" = shared ] && x="STS_SILVER_SHARED_CHILD_EXPLORATION=1"
cd /home/user/sts_ai
env -i HOME=/root PATH=/root/.local/bin:/root/.cargo/bin:/usr/local/go/bin:/opt/node22/bin:/opt/maven/bin:/opt/gradle/bin:/opt/rbenv/bin:/root/.bun/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin OMP_NUM_THREADS=1 STS_EXECUTABLE_GIT_SHA=a1e9a1a10cae815218c3481bd19b52ce8daf5634 STS_SILVER_ADAPTIVE=0 $x bash tools/seed_guard.sh build/linux-gcc-release/one_combat bestbench 10000 4 0 $off /tmp/claude-0/-home-user-sts-ai/1f2ac725-e5d5-5293-8a42-060605adc1d0/scratchpad/sce10k32/${arm}_$off.csv > /tmp/claude-0/-home-user-sts-ai/1f2ac725-e5d5-5293-8a42-060605adc1d0/scratchpad/sce10k32/${arm}_$off.log 2>&1
echo "$arm $off exit=$?" >> /tmp/claude-0/-home-user-sts-ai/1f2ac725-e5d5-5293-8a42-060605adc1d0/scratchpad/sce10k32/status.txt
