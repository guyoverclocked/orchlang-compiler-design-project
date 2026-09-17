#pragma once

// Security labels for OrchLang's information-flow type system.
//
// A label is a point in the product lattice
//     L = Confidentiality x Integrity
//       = ({Public <= Secret}, {Untrusted <= Trusted})
//
// Confidentiality orders "how restricted" a value is: Public flows anywhere,
// Secret may not reach a prompt, a sink, or the workflow output.  Integrity
// orders "how trustworthy" a value is: Trusted may drive a sink, Untrusted may
// not.  Both components are two-point lattices, so the join is a max in the
// confidentiality direction and a min in the integrity direction.

#include <string>

namespace orchlang {

enum class Confidentiality { Public, Secret };
enum class Integrity { Trusted, Untrusted };

struct Label {
    Confidentiality confidentiality{Confidentiality::Public};
    Integrity integrity{Integrity::Trusted};

    bool operator==(const Label& other) const {
        return confidentiality == other.confidentiality && integrity == other.integrity;
    }
    bool operator!=(const Label& other) const { return !(*this == other); }

    bool isSecret() const { return confidentiality == Confidentiality::Secret; }
    bool isUntrusted() const { return integrity == Integrity::Untrusted; }
};

// The bottom of the lattice: public and trusted data, which flows anywhere.
inline Label publicTrusted() { return {Confidentiality::Public, Integrity::Trusted}; }

// Least upper bound.  Secret dominates Public; Untrusted dominates Trusted.
inline Label join(const Label& left, const Label& right) {
    return {left.isSecret() || right.isSecret() ? Confidentiality::Secret : Confidentiality::Public,
            left.isUntrusted() || right.isUntrusted() ? Integrity::Untrusted : Integrity::Trusted};
}

// left <= right in the product order.
inline bool flowsTo(const Label& left, const Label& right) {
    const bool confidentialityOk = !left.isSecret() || right.isSecret();
    const bool integrityOk = !left.isUntrusted() || right.isUntrusted();
    return confidentialityOk && integrityOk;
}

std::string labelName(const Label& label);

}  // namespace orchlang
