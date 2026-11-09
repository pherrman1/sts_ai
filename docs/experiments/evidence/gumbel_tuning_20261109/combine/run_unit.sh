#!/usr/bin/env bash
# Stage 2 (combination) of the Gumbel tuning experiment: units are `SEED ACT SET [SEL]` from make_units.py
# (../PREREG.md, ../sets_combine.tsv); the unit script is ../run_unit.sh.
exec bash "$(dirname "$(realpath "$0")")/../run_unit.sh" "$@"
