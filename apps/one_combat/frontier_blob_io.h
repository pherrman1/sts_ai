#ifndef STS_LIGHTSPEED_ONE_COMBAT_FRONTIER_BLOB_IO_H
#define STS_LIGHTSPEED_ONE_COMBAT_FRONTIER_BLOB_IO_H

#include <cstdint>
#include <fstream>
#include <vector>

namespace one_combat {

std::vector<std::uint8_t> readFgBlob(std::ifstream &file,
                                     std::uint64_t offset,
                                     std::uint32_t size);

} // namespace one_combat

#endif
