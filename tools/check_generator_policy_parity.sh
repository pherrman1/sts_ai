#!/usr/bin/env bash
# Pins the strategic generators' main trajectory to the deployed policy
# (ledger §431): strategicgen, strategicgen2 and bestbench play the same seed
# and must end in the same (won, floor, hp).
# Usage: check_generator_policy_parity.sh ONE_COMBAT SEED SIMS ASC OUTDIR
set -euo pipefail
exe="$1"; seed="$2"; sims="$3"; asc="$4"; out="$5"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$out"
export OMP_NUM_THREADS=1 STRATEGIC_BRANCH_FIGHTS=1 STRATEGIC_BRANCH_SIMS=10
bash "$here/seed_guard.sh" "$exe" bestbench "$sims" 1 "$asc" "$seed" "$out/bestbench.csv" > /dev/null
bash "$here/seed_guard.sh" "$exe" strategicgen 1 "$sims" "$asc" "$out/strategicgen.csv" "$seed" > /dev/null
bash "$here/seed_guard.sh" "$exe" strategicgen2 1 "$sims" "$asc" "$out/strategicgen2.csv" "$seed" > /dev/null

# bestbench rows: seed,won,floor,act,hp,...  Generator rows end with
# ...,won,floor,hp; strategicgen2 appends four label columns to sampled rows.
bb="$(awk -F, -v s="$seed" '$1 == s { print $2 "," $3 "," $5 }' "$out/bestbench.csv" | tail -1)"
sg="$(tail -1 "$out/strategicgen.csv" | awk -F, '{ print $(NF-2) "," $(NF-1) "," $NF }')"
sg2="$(awk -F, 'NR == 1 { h = NF; next } { last = (NF == h) ? $(NF-6) "," $(NF-5) "," $(NF-4) : $(NF-2) "," $(NF-1) "," $NF } END { print last }' "$out/strategicgen2.csv")"
echo "bestbench=$bb strategicgen=$sg strategicgen2=$sg2"
if [ -z "$bb" ] || [ "$bb" != "$sg" ] || [ "$bb" != "$sg2" ]; then
    echo "GENERATOR_POLICY_PARITY: FAIL" >&2
    exit 1
fi
echo "GENERATOR_POLICY_PARITY: PASS"
