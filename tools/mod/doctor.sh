#!/usr/bin/env bash
set -euo pipefail

java_bin=$(command -v java || true)
javac_bin=$(command -v javac || true)
for candidate in \
  "${HOME}/.local/share/Steam/steamapps/common/SlayTheSpire/jre/bin/java" \
  "${HOME}/.steam/steam/steamapps/common/SlayTheSpire/jre/bin/java"; do
  if [[ -z "$java_bin" && -x "$candidate" ]]; then java_bin="$candidate"; fi
done
echo "java=${java_bin:-missing}"
echo "javac=${javac_bin:-missing}"
if [[ -n "$java_bin" ]]; then "$java_bin" -version 2>&1 | head -1; fi
for root in \
  "${HOME}/.steam/steam/steamapps/common/SlayTheSpire" \
  "${HOME}/.local/share/Steam/steamapps/common/SlayTheSpire" \
  "${HOME}/.var/app/com.valvesoftware.Steam/data/Steam/steamapps/common/SlayTheSpire"; do
  if [[ -d "$root" ]]; then
    echo "game=$root"
    [[ -f "$root/desktop-1.0.jar" ]] && echo "gameJar=$root/desktop-1.0.jar"
    [[ -f "$root/mts-launcher.jar" ]] && echo "launcher=$root/mts-launcher.jar"
  fi
done
for jar in \
  "${HOME}/.local/share/Steam/steamapps/workshop/content/646570/1605060445/ModTheSpire.jar" \
  "${HOME}/.local/share/Steam/steamapps/workshop/content/646570/1605833019/BaseMod.jar"; do
  [[ -f "$jar" ]] && echo "dependency=$jar"
done
echo "advisor=${STS_MODEL_INSPECTOR_ADVISOR:-unset}"
