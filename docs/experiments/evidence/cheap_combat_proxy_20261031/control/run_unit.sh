#!/usr/bin/env bash
# Worker campaign for the X1 same-runner production control (../PREREG.md): arms RP FP of ../run_unit.sh.
# usage: run_unit.sh REPO RUN UNIT_OUT SEED
ARMS="RP FP" exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../run_unit.sh" "$@"
