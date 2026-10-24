"""Paper figures from paper/generated/results.json.

leakage.pdf: per workflow, the attacker's balanced accuracy above chance (percentage
points) for the internal decision under each condition. Palette: validated reference
categorical slots 1-5 (light); hatching adds a second channel for grayscale print;
the same numbers are in the paper's leakage table.
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aggregate import NAMES, WORKFLOWS  # noqa: E402

SURFACE = "#fcfcfb"
TEXT, TEXT2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
CONDS = [("orig", "Undefended", "#2a78d6", ""), ("randpad", "Random padding", "#eb6834", "//"),
         ("padonly", "Pad-only", "#1baf7a", "\\\\"), ("noforce", "No-force", "#eda100", ".."),
         ("ours", "Shaped (OrchLang)", "#e87ba4", "")]


def main():
    res = json.load(open(sys.argv[1]))["workflows"]
    out = sys.argv[2]
    wfs = [w for w in WORKFLOWS if w in res]
    plt.rcParams.update({"font.size": 8, "font.family": "sans-serif", "axes.edgecolor": GRID,
                         "axes.labelcolor": TEXT2, "xtick.color": TEXT2, "ytick.color": TEXT2,
                         "hatch.linewidth": 0.6})
    fig, ax = plt.subplots(figsize=(7.0, 2.5), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    n = len(CONDS)
    width = 0.8 / n
    for k, (key, label, color, hatch) in enumerate(CONDS):
        xs, ys = [], []
        for i, w in enumerate(wfs):
            d = res[w]["leak"][key]["decision"]
            if d.get("balanced") is None:
                continue
            xs.append(i - 0.4 + width * (k + 0.5))
            ys.append(100 * (d["balanced"] - d["chance_balanced"]))
        ax.bar(xs, ys, width=width * 0.92, color=color, edgecolor=SURFACE, linewidth=0.8, hatch=hatch,
               label=label, zorder=3)
    ax.axhline(0, color=TEXT2, linewidth=0.8, zorder=4)
    ax.set_xticks(range(len(wfs)))
    ax.set_xticklabels([NAMES[w] for w in wfs], rotation=20, ha="right")
    ax.set_ylabel("Balanced accuracy\nabove chance (points)")
    ax.yaxis.grid(True, color=GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="both", length=0)
    leg = ax.legend(ncol=n, loc="upper center", bbox_to_anchor=(0.5, 1.2), frameon=False, fontsize=7,
                    handlelength=1.4, columnspacing=1.2)
    for t in leg.get_texts():
        t.set_color(TEXT)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    print("wrote", out)


if __name__ == "__main__":
    main()
