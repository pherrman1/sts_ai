#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace one_combat {
// `one_combat heartleaftail SALT REPEATS OUT.jsonl ROOTS.jsonl...`: one row per
// MAP root snapshot with its exact heart-leaf features and, when REPEATS > 0,
// that many live-configured rollout3 tails (end-state features or terminal).
int heartLeafTailGen(std::uint64_t salt, unsigned repeats, const std::string &output,
                     const std::vector<std::string> &inputs);
// `one_combat heartleafparity MANIFEST ROWS.jsonl`: rows {"i","v","value"} of
// sparse heart features and the Python model value; exit 0 when they agree.
int heartLeafParity(const std::string &manifest, const std::string &input);
}
