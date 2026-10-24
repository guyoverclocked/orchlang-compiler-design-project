"""Competent structural baseline on the production IR's primitive cost facts.

Independent max/sum/multiply traversal; not an external prior-art implementation.
Shares the trusted frontend and primitive assumptions with the production tool.
Historical flat/retry-omitting functions in evaluate.py are negative controls.
"""
from collections import defaultdict


def structural_bound(workflow):
    regions = defaultdict(list)
    identifiers = set()
    for node in workflow["nodes"]:
        if node["id"] in identifiers:
            raise ValueError("duplicate IR node identity")
        identifiers.add(node["id"])
        regions[node["region"]].append(node)
    visited = set()

    def block(region):
        if region in visited:
            raise ValueError("duplicate region traversal")
        visited.add(region)
        # (input maximum, output maximum, total maximum), not sum of maxima
        result = [0, 0, 0]
        for node in regions[region]:
            kind = node["kind"]
            attrs = node["attributes"]
            cost = [0, 0, 0]
            if kind == "Call":
                i, o = int(attrs["in_tokens"]), int(attrs["out_tokens"])
                if i < 0 or o < 0:
                    raise ValueError("negative primitive cost")
                cost = [i, o, i + o]
            elif kind in {"Branch", "Retry"}:
                # Current IR uses line#node-id. Resolve from the explicit
                # child paths rather than assuming source lines are unique.
                prefix = region + ("/then@" if kind == "Branch" else "/retry@")
                suffix = "#" + str(node["id"])
                matches = [r for r in list(regions) if r.startswith(prefix) and
                           "/" not in r[len(prefix):] and r.endswith(suffix)]
                if len(matches) > 1:
                    raise ValueError("ambiguous region ownership")
                if matches:
                    child = matches[0]
                    cost = block(child)
                    if kind == "Retry":
                        bound = int(attrs["bound"])
                        if bound < 0:
                            raise ValueError("negative retry bound")
                        cost = [n * bound for n in cost]
                    else:
                        other = block(region + "/else@" + child[len(prefix):])
                        cost = [max(a, b) for a, b in zip(cost, other)]
                elif kind == "Branch":
                    # A then block can be empty while the else block has work.
                    eprefix = region + "/else@"
                    alternatives = [r for r in list(regions) if r.startswith(eprefix) and
                                    "/" not in r[len(eprefix):] and r.endswith(suffix)]
                    if len(alternatives) > 1:
                        raise ValueError("ambiguous else ownership")
                    if alternatives:
                        cost = block(alternatives[0])
            elif kind not in {"Input", "Secret", "Model", "Prompt", "Tool", "Requirement",
                              "Emit", "Reclassify", "Output"}:
                raise ValueError("unknown IR node kind")
            result = [a + b for a, b in zip(result, cost)]
        return result

    value = block("root")
    if any(nodes and region not in visited for region, nodes in regions.items()):
        raise ValueError("orphan IR region")
    return dict(input=value[0], output=value[1], total=value[2])
