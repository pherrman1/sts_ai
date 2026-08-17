# 2026-08-16 — Particle-conditioned leaf probe implementation

Implemented the Phase-1 diagnostic/offline probe only. It tests draw order as
the first hidden variable because the current Searcher3 particle generator
already varies draw order while `CombatObservation::visibleHash()` treats the
draw pile as a multiset. Full RNG conditioning, particle-averaged runtime
VNet inference, VNet-only search, policy priors, belief changes, and OOC changes
are deferred to a later phase and are not implemented here.

The probe runs from actual Searcher3 frontier-type-0 leaves, preserves all six
simulator RNG streams and the draw-pile multiset, serializes next-draw-first
(back-to-front), and evaluates every variant through the isolated common-RNG
rollout path. This document records implementation only; no Phase-1 scientific
verdict or gameplay promotion is claimed.