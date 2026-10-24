#pragma once

#include <string>

namespace orchlang {

// JSON strings must escape every ASCII control byte, not just newlines/tabs.
inline std::string escapeJsonText(const std::string& text) {
    constexpr char hex[] = "0123456789abcdef";
    std::string result;
    for (const unsigned char c : text) {
        switch (c) {
            case '"': result += "\\\""; break;
            case '\\': result += "\\\\"; break;
            case '\n': result += "\\n"; break;
            case '\r': result += "\\r"; break;
            case '\t': result += "\\t"; break;
            default:
                if (c < 0x20) {
                    result += "\\u00";
                    result += hex[c >> 4];
                    result += hex[c & 15];
                } else {
                    result += static_cast<char>(c);
                }
        }
    }
    return result;
}

}  // namespace orchlang
