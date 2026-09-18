#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")" && pwd)
out="$root/build"
mod_the_spire=${1:-}
base_mod=${2:-}
game_jar=${3:-}

if [[ -z "$mod_the_spire" || -z "$base_mod" || -z "$game_jar" ]]; then
  echo "usage: $0 MODTHESPIRE.jar BASEMOD.jar desktop-1.0.jar" >&2
  exit 2
fi
for dependency in "$mod_the_spire" "$base_mod" "$game_jar"; do
  [[ -f "$dependency" ]] || { echo "missing dependency: $dependency" >&2; exit 2; }
done
javac_bin=${JAVAC:-$(command -v javac || true)}
if [[ -z "$javac_bin" ]]; then
  echo "no javac found; install/use a Java 8 JDK without changing system defaults" >&2
  exit 3
fi
rm -rf "$out/classes"
mkdir -p "$out/classes"
mapfile -t sources < <(find "$root/src/main/java" -name '*.java' -print)
"$javac_bin" -source 8 -target 8 -encoding UTF-8 \
  -cp "$mod_the_spire:$base_mod:$game_jar" -d "$out/classes" "${sources[@]}"
cp "$root/ModTheSpire.json" "$out/classes/"
(cd "$out/classes" && jar cf "$out/sts-model-inspector.jar" .)
echo "$out/sts-model-inspector.jar"
