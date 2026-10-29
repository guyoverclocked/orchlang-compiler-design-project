#pragma once

#include <cstddef>
#include <string>

namespace orchlang {

struct SourceLocation {
    std::string file;
    std::size_t line{0};
    std::size_t column{0};

    bool valid() const { return line != 0 && column != 0; }
};

std::string formatLocation(const SourceLocation& location);

}  // namespace orchlang
