"""One-line diagram of the 39-bus case with the worst N-1 results marked.

Bus positions are hand-placed to follow the usual New England layout. Drawn straight
from results/, so any change in the study changes the picture.
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D

from . import config as C
from .network import bus_no, load_case

INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#a8a7a1", "#fcfcfb"
CRITICAL, SERIOUS, LOST = "#d03b3b", "#ec835a", "#6250d6"

POS = {
    30: (2.4, 13.4), 2: (2.4, 11.6), 25: (5.6, 11.6), 37: (5.6, 13.4), 1: (0.8, 8.8), 3: (4.2, 9.2),
    18: (6.6, 9.4), 26: (9.4, 11.6), 27: (9.4, 9.2), 17: (8.2, 8.0), 28: (12.6, 11.6), 29: (15.8, 11.6),
    38: (15.8, 13.4), 39: (0.8, 2.6), 9: (2.2, 1.6), 8: (2.8, 3.6), 7: (3.8, 2.6), 5: (2.8, 5.6),
    4: (4.2, 7.0), 6: (4.8, 4.6), 31: (4.8, 1.0), 11: (6.4, 4.6), 10: (7.8, 3.4), 32: (7.8, 1.0),
    12: (7.6, 5.8), 13: (8.4, 4.8), 14: (7.0, 7.0), 15: (9.0, 6.2), 16: (10.6, 7.0), 19: (10.6, 3.6),
    33: (10.6, 1.0), 20: (12.8, 3.6), 34: (12.8, 1.0), 21: (12.8, 6.0), 24: (12.8, 8.2), 22: (15.8, 6.0),
    23: (15.8, 8.2), 35: (17.8, 6.0), 36: (17.8, 8.2),
}
GEN_BUSES = {30, 31, 32, 33, 34, 35, 36, 37, 38, 39}
# Where each loading tag sits, relative to the middle of its branch.
TAG_OFFSET = {"Line 23-24": (0.0, 1.15), "Line 2-3": (1.85, 0.2), "Line 6-11": (0.0, 1.1)}
NUMBER_RIGHT = {13, 39}   # bus numbers drawn right of the bar, clear of nearby marks
NUMBER_BELOW = {21}


def _branches(net):
    out = []
    for i in net.line.index:
        a, b = bus_no(net, net.line.from_bus[i]), bus_no(net, net.line.to_bus[i])
        out.append((f"Line {min(a, b)}-{max(a, b)}", a, b))
    for i in net.trafo.index:
        a, b = bus_no(net, net.trafo.hv_bus[i]), bus_no(net, net.trafo.lv_bus[i])
        out.append((f"Xfmr {min(a, b)}-{max(a, b)}", a, b))
    return out


def draw(path):
    net = load_case()
    cases = pd.read_csv(C.RESULTS / "n1_contingencies.csv")
    cases = cases[cases.scenario == C.PRIMARY]
    vio = pd.read_csv(C.RESULTS / "n1_violations.csv")
    vio = vio[(vio.scenario == C.PRIMARY) & (vio.category != "pre-existing")]
    base = json.loads((C.RESULTS / "base_summary.json").read_text())

    over = vio[vio.kind == "overload"].sort_values("value", ascending=False).drop_duplicates("element")
    worst = over.set_index("element")
    top = over.head(3)

    fig, ax = plt.subplots(figsize=(10.4, 7.6), dpi=170)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    # Buses lost when Line 16-19 opens.
    lost = cases[cases.label == "Line 16-19"].iloc[0]
    island = [int(x) for x in str(lost.islanded_buses).split()]
    xs = [POS[b][0] for b in island]
    ys = [POS[b][1] for b in island]
    ax.add_patch(plt.Rectangle((min(xs) - 0.75, min(ys) - 0.72), max(xs) - min(xs) + 2.5, max(ys) - min(ys) + 1.4,
                               fc="#efedfb", ec=LOST, lw=1.0, ls=(0, (4, 3)), zorder=0))
    ax.text(min(xs) - 0.6, max(ys) + 0.76, f"Islands if Line 16-19 opens: {lost.load_lost_mw:.0f} MW load, "
            f"{lost.gen_lost_mw:,.0f} MW gen", fontsize=7.6, color=LOST, va="bottom")

    for label, a, b in _branches(net):
        (x1, y1), (x2, y2) = POS[a], POS[b]
        hot = label in worst.index
        ax.plot([x1, x2], [y1, y2], color=CRITICAL if hot else GRID, lw=2.6 if hot else 1.1,
                solid_capstyle="round", zorder=1 if not hot else 2)
        if label.startswith("Xfmr"):
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            ax.scatter([mx], [my], s=30, fc=SURFACE, ec=CRITICAL if hot else MUTED, lw=1.0, zorder=3)

    for label, row in top.set_index("element").iterrows():
        pair = next((a, b) for l, a, b in _branches(net) if l == label)
        (x1, y1), (x2, y2) = POS[pair[0]], POS[pair[1]]
        dx, dy = TAG_OFFSET.get(label, (0.1, 0.3))
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.annotate(f"{label}: {row.value:.0f}%\nafter {row.contingency}", xy=(mx, my), xytext=(mx + dx, my + dy),
                    fontsize=7.6, color=INK, ha="center", va="center", zorder=6, linespacing=1.15,
                    bbox=dict(boxstyle="round,pad=0.22", fc=SURFACE, ec=CRITICAL, lw=0.8),
                    arrowprops=dict(arrowstyle="-", color=CRITICAL, lw=0.8))

    high = set(base["buses_above_band"])
    caused = vio[vio.kind.isin(["low_voltage", "high_voltage"]) & ~vio.at_tripped_unit_terminal]
    low_buses = {int(e.split()[1]) for e in caused.element[caused.kind == "low_voltage"]}
    high_buses = {int(e.split()[1]) for e in caused.element[caused.kind == "high_voltage"]}
    for b, (x, y) in POS.items():
        ax.plot([x - 0.3, x + 0.3], [y, y], color=INK, lw=2.6, solid_capstyle="butt", zorder=4)
        if b in NUMBER_RIGHT:
            ax.text(x + 0.36, y + 0.1, str(b), fontsize=7.2, color=INK, ha="left", va="bottom", zorder=5)
        elif b in NUMBER_BELOW:
            ax.text(x - 0.36, y - 0.1, str(b), fontsize=7.2, color=INK, ha="right", va="top", zorder=5)
        else:
            ax.text(x - 0.36, y + 0.12, str(b), fontsize=7.2, color=INK, ha="right", va="bottom", zorder=5)
        for offset, marker, group in ((0.46, "v", low_buses), (0.68, "^", high_buses)):
            if b in group:
                ax.scatter([x + (0.46 if b not in low_buses else offset)], [y], marker=marker, s=26, color=SERIOUS, zorder=5, lw=0)
        if b in high:
            ax.scatter([x], [y - 0.2], s=12, fc=SURFACE, ec=MUTED, lw=0.9, zorder=5)
        if b in GEN_BUSES:
            gy = y + (0.42 if b in (30, 37, 38) else (-0.42 if b in (31, 32, 33, 34) else 0))
            gx = x + (0.5 if b in (35, 36) else (-0.5 if b == 39 else 0))
            ax.plot([x, gx], [y, gy], color=MUTED, lw=1.0, zorder=3)
            ax.scatter([gx], [gy], s=118, fc=SURFACE, ec=MUTED, lw=1.1, zorder=4)
            ax.text(gx, gy, "G", fontsize=6.4, ha="center", va="center", color=MUTED, zorder=5)

    g39 = cases[cases.label == "Gen 39"].iloc[0]
    ax.annotate("Gen 39 (external-system equivalent) out:\nno AC solution found; model boundary", xy=(0.3, 2.6), xytext=(-0.6, -0.55),
                fontsize=7.6, color=INK, ha="left", va="center", zorder=6,
                bbox=dict(boxstyle="round,pad=0.22", fc=SURFACE, ec=CRITICAL, lw=0.8),
                arrowprops=dict(arrowstyle="-", color=CRITICAL, lw=0.8))
    assert g39.status == "no_solution"

    keys = [
        Line2D([], [], color=CRITICAL, lw=2.6, label="Above 100% rating in at least one N-1 case"),
        Line2D([], [], color=GRID, lw=1.1, label="Stayed within rating"),
        Line2D([], [], marker="o", ls="", mfc=SURFACE, mec=MUTED, ms=5, label="Transformer"),
        Line2D([], [], marker="^", ls="", color=SERIOUS, ms=5, label="Voltage violation an outage caused: \u25b2 high"),
        Line2D([], [], marker="v", ls="", color=SERIOUS, ms=5, label="Voltage violation an outage caused: \u25bc low"),
        Line2D([], [], marker="o", ls="", mfc=SURFACE, mec=MUTED, ms=3.6, label="Above 1.05 pu before any outage"),
    ]
    ax.legend(handles=keys, loc="upper center", bbox_to_anchor=(0.5, -0.005), ncol=3, frameon=False, fontsize=7.6,
              labelcolor=MUTED, handlelength=2.0, columnspacing=1.6)
    ax.set_xlim(-0.9, 19.1)
    ax.set_ylim(-1.1, 14.5)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(path, bbox_inches="tight", facecolor=SURFACE, metadata={"Software": None})
    plt.close(fig)
