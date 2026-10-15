# Silver A/B/C runtime calibration

Frozen implementation: `f6ad92dd46df4b0c97312557fadef21be164dcd0`.

Pilot seeds were 0–7 only. Budget selection used wall time, never outcomes.
The local 8-thread calibration selected `N_C=3700`: A at 1000 simulations
took 459.9 s and C at 3700 took 435.0 s (`C/A=0.946`, inside ±10%).
The primary experiment was later run on the designated GCP host with 24
logical CPUs. On that host, the observed primary A/C wall ratio was 89.5/57.8
= 1.548. Therefore C remains the predeclared 3700 arm, but the primary A/C
comparison must not be described as equal-runtime evidence. This host change
is a protocol deviation and is recorded explicitly in the main report.

The initial C=2700 and correction C=4300 measurements were retained as
runtime-only calibration records. Their pilot outcomes are not performance
evidence.
