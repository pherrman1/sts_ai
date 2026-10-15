# Third-party notices

## Silver combat-model port

The Silver search and its supporting combat-engine changes are adapted from
the Silver fork: `src/sim/search/SilverSearcher.cpp`,
`src/sim/search/SilverRolloutAgent.cpp`, `src/sim/search/SearchRng.cpp` and
their headers, the information-set `include/combat/CardPile.h`, the search
equality and hashing in `BattleContext`/`CardManager`/`SearchStateHash`, the
deferred Runic Dome intents in `Monster`, and the value-only wire types in
`include/sim/search/SilverBridge.h`. The vendored copy that previously lived in
`third_party/silver_lightspeed/` was removed (ADR-0022). The source is
[`daniel-ziegler/sts_lightspeed`](https://github.com/daniel-ziegler/sts_lightspeed)
at commit `84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`.

The opt-in heart1 policy adapter (`apps/one_combat/heart1_policy.{h,cpp}`,
`tools/heart1/`) ports silverbot's observation/choice encoding and network
forward pass from the same repository and commit (`silverbot/playouts.py`,
`silverbot/network.py`, `bindings/bindings-util.cpp`). The released
`heart1.pt` weights are not included in this repository.

Copyright (c) 2021 gamerpuppy

Copyright (c) 2026 Daniel Ziegler

MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
