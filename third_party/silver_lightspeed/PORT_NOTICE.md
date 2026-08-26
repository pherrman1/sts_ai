# Silver combat-model source port

This directory vendors the minimum currently identified C++ combat/search
dependency closure from:

`daniel-ziegler/sts_lightspeed@84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`

The source is MIT licensed. The complete attribution and license notice is in
the repository-root `THIRD_PARTY_NOTICES.md`.

The CMake target compiles this code under a private namespace (`sts_silver`)
and does not link it into the ordinary sts_ai simulator. The excluded reference
components are apps, bindings, Python/communication integration, console and
full-run controller sources, training, and deployment scripts. Additional
source files may be added only when a concrete unresolved symbol or required
combat semantic proves them to be in the transitive closure.
