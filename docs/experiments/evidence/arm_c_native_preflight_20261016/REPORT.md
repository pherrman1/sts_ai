# Native Arm C preflight — BLOCKED before scientific dispatch

Runtime confirmed by platform status:
`ccarenv_b64_Y2NhcmVudl9iNTE0NmMzYjFlNzQ4MTkxYTJhNmI0ZDJlYTVmNTQ2ZQ`,
running/connected, current observed spec revision5. No cloud-provider identities.

Pinned source: `9d83adbbbcc0fabf2c8bcd8c6a87f9782d0acbc3` (fetched explicitly).
Submodules: json2222d386c905e6a6ebf73c61571a8a2cf196e843,
pybind11 63d627c5747befad7720a43ebbe5614fd5d83247; helper check PASS.
Initial untouched checkout HEAD:5d5e86b9cbf1dd758d3a4f5e014b13a66260be46.

GCC14.2.0, CMake4.4.4, Release preset, parallel4, build return0.
Actual commands used `PYTHONPATH=/workspace/preflight-deps` and
`/workspace/preflight-deps/bin/cmake --preset linux-gcc-release`, then
`cmake --build --preset linux-gcc-build --target one_combat --parallel 4`
using that same absolute CMake executable. Build/configuration logs retained.
New producer binary SHA256:
`0e183d657e4dfa54f19952b265895f2cafb50230a63459c54d17ba146290a7e4`.
This differs from the historical local binary and is not approved for pooling.

Checkpoint extracted using `git show
68fe88be8271fa1f9b515f7a9abcf0fb9755e25f:results/C_d64_trim/student.pt`.
SHA256 `53739a4375380001fce0323935c187906b5c1d5efd65691f9d75f2dd8884e020`.
Unchanged exporter invoked with `--allow-other-checkpoint --n-heads 4 --trim-map`;
SHA256 `eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509`.
Dimensions from checkpoint/export:64/4/256/2/trim_map1. Native `heart1score`
loaded that file and scored one synthetic public record (return0; finite logits
and value retained). No game, seed, canary, cohort, fit or TEST was invoked.
Actual tree-prior/rollout use and observational parity require later canaries.

AMD EPYC9V74 reported; affinity0..4, cgroup cpu.max400000/100000 = four
CPU-equivalents total; memory.max34359738368 bytes, swap reported0.
CPU/address-space/file-size process rlimits unlimited; process count136275,
file descriptors16384. These are observed process/cgroup bounds, not a platform
session lifetime guarantee. Session expiry and filesystem retention are unknown.
No inference of dedicated physical cores or64-worker capacity is supported.

Nine focused checks passed (unit-checks.log): two preparation-adapter checks,
public-record boundaries, prior/rollout contracts, repeated-child teacher use,
original canary hash binding and incomplete-group rejection. Full21-test suite
was deliberately not run because it contains fitting and TEST evaluator paths.
No native full-suite or authoritative Linux GCC Actions result is claimed.

The adapter is deliberately incomplete for execution: fixed coordinator
assignment and per-shard environment/guarded command/deadline specifications
only. It reads the literal environment from the byte-identical pinned runner
without importing or running it. Workers default1 as an assignment choice,
not observed capacity. Independent review must precede dispatch implementation,
frozen producer review, new canaries and completion-anchored artifact review.
There is no launch mode, fitting path, TEST reader or auto-promotion.
Future execution still needs coordinator leases preventing duplicate launch,
persisted immutable global deadline, completion/partial receipts, sealed TEST
custody, export/reimport verification and all original scientific gates.

Durable export is UNVERIFIED: available tools have no native artifact upload
capability. `gh auth status` reports the GH_TOKEN invalid; Git fetch succeeds
through the supported proxy, but that does not prove API upload authorization.
Sandbox evidence paths are preservation only, not delivery. No paid or
third-party infrastructure was provisioned, and no credentials were restored.
A native-platform download/export round trip remains a hard campaign blocker.

Knowledge impact: current research is blocked at preflight; historical scientific
verdicts and production defaults are unchanged. Independent implementation review
is pending with the coordinating local reviewer; no other chat was contacted.
