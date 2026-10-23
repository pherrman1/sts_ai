#!/usr/bin/env bash
# Rebuild a silver-leaf-a20 pack for the offline diagnostics, byte for byte: prod = the production-combat campaign
# (../silver_leaf_a20_prod_20261022, one_combat f4cc0752..., pack sha256 47efc292...), a20 = the first campaign
# (../silver_leaf_a20_data_20261022, one_combat 13055711..., pack sha256 408a864c...). About 4 minutes each on 4 cores.
# usage (repo root): W=WORKDIR build_pack.sh prod|a20
set -uo pipefail
W=${W:?set W to the work directory}
R=$(pwd); E=$R/docs/experiments/evidence
case ${1:-} in
  prod) BIN=f4cc0752630ab82d2310cc304cdb9ae3e6b543d8e4ace7a854b7040069b24e41 C=silver_leaf_a20_prod_20261022 PACK=a20prod_pack.npz ;;
  a20) BIN=1305571153a81adb7775ed10682661290b3470b49f1cd6948a313cd17d761ab8 C=silver_leaf_a20_data_20261022 PACK=a20_pack.npz ;;
  *) echo "usage: W=WORKDIR build_pack.sh prod|a20" >&2; exit 2 ;;
esac
mkdir -p "$W/bin"
cp "/mnt/project-files/bin-cache/one_combat-$BIN" "$W/bin/one_combat_$1" && chmod +x "$W/bin/one_combat_$1" || exit 3
sha256sum "$W/bin/one_combat_$1"
python3 tools/cloud/verify_campaign.py "$E/$C" --extract "$W/units_$1" 2>&1 | tail -3
python3 "$E/silver_leaf_a20_data_20261022/pack_a20.py" "$W/bin/one_combat_$1" "$R" "$W/units_$1" "$W/$PACK" \
  "$W/pack_$1.work" 4 2>&1 | tail -2
sha256sum "$W/$PACK"
rm -rf "$W/units_$1"
