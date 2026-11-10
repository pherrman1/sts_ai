#!/usr/bin/env bash
# Scout run of the Gumbel tuning experiment: units are `SEED 3 scout` (../PREREG.md); the unit script is ../run_unit.sh.
exec bash "$(dirname "$(realpath "$0")")/../run_unit.sh" "$@"
