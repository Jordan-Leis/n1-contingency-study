"""Build figures, README tables and the study memo from results/. No study code runs here."""
import json
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from . import config as C
from . import oneline

README = C.ROOT / "README.md"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#d9d8d3", "#fcfcfb"
SERIES = {"shared": "#2a78d6", "single": "#eb6834"}  # dataviz reference slots 1 and 2


def load():
    r = C.RESULTS
    return dict(
        cases=pd.read_csv(r / "n1_contingencies.csv"), vio=pd.read_csv(r / "n1_violations.csv"),
        totals=pd.read_csv(r / "n1_scenario_totals.csv"), host=pd.read_csv(r / "hosting_capacity.csv"),
        trace=pd.read_csv(r / "gen39_trace.csv"), base=json.loads((r / "base_summary.json").read_text()),
        data=json.loads((r / "data_check.json").read_text()), xc=json.loads((r / "crosscheck.json").read_text()),
    )


def fmt_mw(x):
    return f"{x:,.0f}"


def outcome(row):
    if row.status == "no_solution":
        boundary = " Model boundary: bus 39 is the external-system equivalent" if row.label == "Gen 39" else ""
        return f"No AC solution found ({fmt_mw(row.gen_lost_mw)} MW lost).{boundary}"
    if row.status == "implausible_solution":
        return "Solver returned a non-physical answer"
    if isinstance(row.islanded_buses, str) and row.islanded_buses:
        buses = ", ".join(row.islanded_buses.split())
        lost = f"{fmt_mw(row.load_lost_mw)} MW load lost" if row.load_lost_mw > 0.01 else "no load lost"
        return f"Islands bus {buses}: {lost}"
    return "Solved"


def worst(row):
    if row.status != "solved":
        return "not assessed (no solution)"
    parts = []
    if row.overloads > 0:
        more = f" (+{row.overloads - 1} more)" if row.overloads > 1 else ""
        parts.append(f"{row.worst_overload_element} at {row.worst_overload_pct:.0f}%{more}")
    if row.low_voltage_buses > 0:
        parts.append(f"{row.lowest_bus} low at {row.lowest_vm_pu:.3f} pu")
    if row.high_voltage_buses > 0:
        parts.append(f"{row.highest_bus} high at {row.highest_vm_pu:.3f} pu")
    return "; ".join(parts) or "none"


def n1_table(d, n=10):
    df = d["cases"][d["cases"].scenario == C.PRIMARY].head(n)
    lines = ["| Rank | Outage | Result | Worst problem the outage causes |", "|---:|---|---|---|"]
    for r in df.itertuples():
        lines.append(f"| {r.rank} | {r.label} | {outcome(r)} | {worst(r)} |")
    return "\n".join(lines)


SCEN_NAMES = {"shared_qlim": "**Primary**: lost MW shared by headroom, Q limits on",
              "shared_noqlim": "Shared, Q limits off", "single_qlim": "Swing machine takes all, Q limits on",
              "single_noqlim": "Swing machine takes all, Q limits off"}


def scenario_table(d):
    lines = ["| Scenario | No solution | Non-physical solution | Load lost | Overload | Voltage violation | Clean | Worst overload |",
             "|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in d["totals"].itertuples():
        lines.append(f"| {SCEN_NAMES[r.scenario]} | {r.no_solution} | {r.implausible_solution} | {r.with_load_lost} | "
                     f"{r.with_overload} | {r.with_voltage_violation} | {r.clean} | "
                     f"{r.worst_overload_element} {r.worst_overload_pct:.1f}% after {r.worst_overload_contingency} |")
    return "\n".join(lines)


def _limit(r):
    worse = isinstance(r.limit_reference, float) and r.limit_reference == r.limit_reference and (
        (r.limit_kind == "overload" and r.limit_reference > C.THERMAL_LIMIT_PCT) or
        (r.limit_kind == "high_voltage" and r.limit_reference > C.V_MAX_PU) or
        (r.limit_kind == "low_voltage" and r.limit_reference < C.V_MIN_PU))
    if worse and r.limit_kind == "overload":
        return f"{r.limit_element} {r.limit_reference:.1f}% \u2192 {r.limit_value:.1f}% with {r.limit_contingency} out"
    if worse:
        return f"{r.limit_element} {r.limit_reference:.3f} \u2192 {r.limit_value:.3f} pu with {r.limit_contingency} out"
    if r.capped:
        return "nothing up to the sweep cap"
    if r.limit_kind in ("no_solution", "implausible_solution"):
        return f"no solution with {r.limit_contingency} out"
    if r.limit_kind == "overload":
        return f"{r.limit_element} {r.limit_value:.1f}% with {r.limit_contingency} out"
    word = "high" if r.limit_kind == "high_voltage" else "low"
    where = "no outage" if r.limit_contingency.startswith("BASE") else f"{r.limit_contingency} out"
    return f"{r.limit_element} {word} at {r.limit_value:.3f} pu, {where}"


def host_text(mw, capped):
    """Last passing step. Failing the first step means 'under one step', not zero."""
    if capped:
        return f"\u2265 {fmt_mw(mw)}"
    return f"< {fmt_mw(C.HOSTING_STEP_MW)}" if mw <= 0 else fmt_mw(mw)


def _mw(r):
    return host_text(r.hosting_mw, r.capped)


def hosting_table(d):
    h = d["host"]
    get = lambda disp, bus, dfn: h[(h.dispatch == disp) & (h.bus == bus) & (h.definition == dfn)].iloc[0]
    lines = ["| Bus | N-1 rule, all back off | What stops it first | N-1 rule, swing only | New problems only, all back off | New problems only, swing only | No outage, all back off | Any new crossing |",
             "|---:|---:|---|---:|---:|---:|---:|---:|"]
    for b in C.HOSTING_BUSES:
        s = get("shared", b, "screening")
        lines.append(f"| {b} | {_mw(s)} | {_limit(s)} | {_mw(get('single', b, 'screening'))} | "
                     f"{_mw(get('shared', b, 'new_only'))} | {_mw(get('single', b, 'new_only'))} | "
                     f"{_mw(get('shared', b, 'no_outage_only'))} | {_mw(get('shared', b, 'any_new'))} |")
    return "\n".join(lines)


RULES = (("new_only", "New problems only (upper bound)", "#2a78d6"),
         ("screening", "Also existing problems made worse (N-1 study rule)", "#eb6834"))


def hosting_chart(d, path):
    h = d["host"]
    buses = list(C.HOSTING_BUSES)
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.7), dpi=170, sharey=True)
    fig.patch.set_facecolor(SURFACE)
    bar_h = 0.36
    xmax = h[h.definition.isin(["new_only", "screening"])].hosting_mw.max() + 140
    for ax, (disp, title) in zip(axes, (("shared", "All machines back off for the solar"),
                                        ("single", "Only the swing machine backs off"))):
        ax.set_facecolor(SURFACE)
        for k, (dfn, label, color) in enumerate(RULES):
            for i, b in enumerate(buses):
                r = h[(h.dispatch == disp) & (h.bus == b) & (h.definition == dfn)].iloc[0]
                y = i + (k - 0.5) * (bar_h + 0.04)
                ax.barh(y, max(r.hosting_mw, 0.0), height=bar_h, color=color, label=label if i == 0 else None,
                        edgecolor=SURFACE, linewidth=1.0)
                ax.text(max(r.hosting_mw, 0.0) + 10, y, host_text(r.hosting_mw, r.capped), va="center",
                        fontsize=7.2, color=INK)
        ax.set_title(title, fontsize=8.6, color=INK, loc="left")
        ax.set_yticks(range(len(buses)), [f"Bus {b}" for b in buses], fontsize=8, color=INK)
        ax.tick_params(axis="x", labelsize=7.4, colors=MUTED)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.set_xlim(0, xmax)
    axes[0].invert_yaxis()
    fig.supxlabel("Solar MW at unity power factor before the rule fails, all N-1 outages checked (50 MW steps)",
                  fontsize=8, color=MUTED, y=0.1)
    fig.suptitle("Screening estimate of solar hosting capacity, IEEE 39-bus", fontsize=9.8, color=INK, x=0.01,
                 ha="left", y=0.99)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=7.6, loc="lower center", ncol=2, labelcolor=MUTED,
               bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.1, 1, 0.95))
    fig.savefig(path, bbox_inches="tight", facecolor=SURFACE, metadata={"Software": None})
    plt.close(fig)


def fill_readme(d):
    if not README.exists():
        return
    text = README.read_text()
    blocks = {"n1_table": n1_table(d), "scenario_table": scenario_table(d), "hosting_table": hosting_table(d)}
    for name, body in blocks.items():
        text = re.sub(rf"(<!-- {name} -->\n).*?(<!-- /{name} -->)", lambda m: m.group(1) + body + "\n" + m.group(2),
                      text, flags=re.S)
    README.write_text(text)


def main():
    d = load()
    C.FIGURES.mkdir(exist_ok=True)
    C.MEMO.mkdir(exist_ok=True)
    oneline.draw(C.FIGURES / "one_line.png")
    hosting_chart(d, C.FIGURES / "hosting_capacity.png")
    fill_readme(d)
    from . import memo
    memo.build(d)
    print("report: figures, README tables and memo rebuilt")


if __name__ == "__main__":
    main()
