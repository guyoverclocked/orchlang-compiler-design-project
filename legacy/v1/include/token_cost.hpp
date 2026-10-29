#pragma once

// Saturating token arithmetic for OrchLang's static cost analysis.
//
// Every bound the compiler derives is an upper bound, so the only safe
// direction to round is up.  Saturating at the maximum representable value
// keeps that property when a workflow's declared repetition counts would
// otherwise overflow: a saturated bound still over-approximates the real cost,
// and it always exceeds any budget a source file can name.

#include <cstddef>
#include <limits>

namespace orchlang {

// A workflow whose bound reaches this value has an unusable (saturated) bound.
inline constexpr std::size_t saturatedTokens() { return std::numeric_limits<std::size_t>::max(); }

inline bool isSaturated(std::size_t value) { return value == saturatedTokens(); }

// Upper-bounded addition.  Never wraps.
inline std::size_t addTokens(std::size_t left, std::size_t right) {
    if (left > saturatedTokens() - right) {
        return saturatedTokens();
    }
    return left + right;
}

// Upper-bounded multiplication, used for bounded repetition.
inline std::size_t multiplyTokens(std::size_t value, std::size_t factor) {
    if (value == 0 || factor == 0) {
        return 0;
    }
    if (value > saturatedTokens() / factor) {
        return saturatedTokens();
    }
    return value * factor;
}

// Upper bound of two alternatives, used for branches.
inline std::size_t maxTokens(std::size_t left, std::size_t right) {
    return left > right ? left : right;
}

}  // namespace orchlang
