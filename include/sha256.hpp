#pragma once

// SHA-256, so a certificate can name exactly the source text it was derived
// from.  A certificate that does not bind its source can be replayed against a
// different program; with the hash, a checker rejects it as stale.

#include <string>

namespace orchlang {

// Lower-case hexadecimal digest of the bytes of `data`.
std::string sha256Hex(const std::string& data);

}  // namespace orchlang
