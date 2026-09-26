#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
"$root/build.sh" "$@"
classes=$(mktemp -d)
trap 'rm -rf "$classes"' EXIT
javac_bin=${JAVAC:-$(command -v javac)}
"$javac_bin" -source 8 -target 8 -encoding UTF-8 \
  -cp "$root/build/classes:$1:$2:$3" -d "$classes" \
  "$root"/src/test/java/stsmodelinspector/*.java
java -cp "$classes:$root/build/classes:$1:$2:$3" stsmodelinspector.LiveOocCaptureTest
java -cp "$classes:$root/build/classes:$1:$2:$3" stsmodelinspector.OocOverlayTest
java -cp "$classes:$root/build/classes:$1:$2:$3" stsmodelinspector.CombatBoundaryTest
java -cp "$classes:$root/build/classes:$1:$2:$3" stsmodelinspector.PotionOverlayTest
java -cp "$classes:$root/build/classes:$1:$2:$3" stsmodelinspector.TargetLabelsTest
java -cp "$classes:$root/build/classes:$1:$2:$3" stsmodelinspector.SilverBudgetTest
java -cp "$classes:$root/build/classes:$1:$2:$3" stsmodelinspector.GraphExportSnapshotTest
java -cp "$classes:$root/build/classes:$1:$2:$3" stsmodelinspector.MapOverlayTest \
  "$root/../../tests/fixtures/live_combat_boundaries/fresh-a0.jsonl.gz"

java -cp "$classes:$root/build/classes:$1:$2:$3" stsmodelinspector.InlineChoicesTest
