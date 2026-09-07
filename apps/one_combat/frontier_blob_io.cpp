#include "frontier_blob_io.h"

namespace one_combat {

std::vector<std::uint8_t> readFgBlob(std::ifstream &file,
                                     std::uint64_t offset,
                                     std::uint32_t size) {
    std::vector<std::uint8_t> blob(size);
    if (size == 0) return blob;
    file.clear();
    file.seekg((std::streamoff)offset);
    file.read((char *)blob.data(), (std::streamsize)size);
    if (!file) blob.clear();
    return blob;
}

} // namespace one_combat
