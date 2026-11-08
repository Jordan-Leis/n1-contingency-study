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
        return f"No AC solution found ({fmt_mw(row.gen_lost_mw)} MW lost)"
    if row.status == "implausible_solution":
        return "Solver returned a non-physical answer"
    if isinstance(row.islanded_buses, str) and row.islanded_buses:
        buses = ", ".join(row.islanded_buses.split())
        lost = f"{fmt_mw(row.load_lost_mw)} MW load lost" if row.load_lost_mw > 0.01 else "no load lost"
        return f"Islands bus {buses}: {lost}"
    return "Solved"


def worst(row):
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
    lines = ["| Bus | Screening MW, shared back-off | What stops it | Screening MW, swing-only back-off | No-outage only, shared | Any new crossing, shared |",
             "|---:|---:|---|---:|---:|---:|"]
    for b in C.HOSTING_BUSES:
        s, g = get("shared", b, "screening"), get("single", b, "screening")
        lines.append(f"| {b} | {_mw(s)} | {_limit(s)} | {_mw(g)} | {_mw(get('shared', b, 'no_outage_only'))} | "
                     f"{_mw(get('shared', b, 'any_new'))} |")
    return "\n".join(lines)


def hosting_chart(d, path):
    h = d["host"][d["host"].definition == "screening"]
    buses = list(C.HOSTING_BUSES)
    fig, ax = plt.subplots(figsize=(7.2, 3.5), dpi=170)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    bar_h = 0.36
    for k, (disp, label) in enumerate((("shared", "All machines back off"), ("single", "Only the swing machine backs off"))):
        for i, b in enumerate(buses):
            r = h[(h.dispatch == disp) & (h.bus == b)].iloc[0]
            y = i + (k - 0.5) * (bar_h + 0.04)
            ax.barh(y, max(r.hosting_mw, 0.0), height=bar_h, color=SERIES[disp], label=label if i == 0 else None,
                    edgecolor=SURFACE, linewidth=1.0)
            ax.text(max(r.hosting_mw, 0.0) + 12, y, host_text(r.hosting_mw, r.capped),
                    va="center", fontsize=7.6, color=INK)
    ax.set_yticks(range(len(buses)), [f"Bus {b}" for b in buses], fontsize=8, color=INK)
    ax.invert_yaxis()
    ax.set_xlabel("Solar MW the bus takes before a new N-1 problem appears (50 MW steps)", fontsize=8, color=MUTED)
    ax.tick_params(axis="x", labelsize=7.6, colors=MUTED)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_xlim(0, max(700, h.hosting_mw.max() + 120))
    ax.set_title("Screening estimate of solar hosting capacity, IEEE 39-bus", fontsize=9.5, color=INK, loc="left")
    ax.legend(frameon=False, fontsize=7.6, loc="lower right", labelcolor=MUTED)
    fig.savefig(path, bbox_inches="tight", facecolor=SURFACE, metadata={"Software": None})
    plt.close(fig)


def fill_readme(d):
    if not README.exists():
        return
    text = README.read_text()
    blocks = {"n1_table": n1_table(d), "scenario_table": scenario_table(d), "hosting_table": hosting_table(d)}
    for name, body in blocks.items():
        text = re.sub(rf"(<!-- {name} -->\n).*?(\n<!-- /{name} -->)", lambda m: m.group(1) + body + m.group(2),
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
