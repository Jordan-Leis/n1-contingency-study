"""Base case and N-1 sweep. Writes tidy tables; all reports are built from these."""
import pandas as pd

from . import config as C
from .contingency import classify, contingency_list, monitored, run_case
from .network import bus_no, gen_label, line_label, load_case, slack_label, solve, trafo_label


def solved_base(qlims):
    net = load_case()
    if solve(net, qlims) is None:
        raise RuntimeError("base case did not solve")
    return net


def base_tables(net):
    """Bus, branch and machine tables for the solved base case, plus a summary."""
    buses = pd.DataFrame({
        "bus": [bus_no(net, b) for b in net.bus.index],
        "vm_pu": net.res_bus.vm_pu.values,
        "va_degree": net.res_bus.va_degree.values,
    })
    buses["band"] = buses.vm_pu.map(
        lambda v: "high" if v > C.V_MAX_PU else ("low" if v < C.V_MIN_PU else "ok"))

    rows = []
    for i in net.line.index:
        rows.append(dict(element=line_label(net, i), p_mw=net.res_line.p_from_mw[i],
                         q_mvar=net.res_line.q_from_mvar[i], loading_pct=net.res_line.loading_percent[i],
                         rating_mva=(3 ** 0.5) * net.line.max_i_ka[i] * net.bus.vn_kv[net.line.from_bus[i]]))
    for i in net.trafo.index:
        rows.append(dict(element=trafo_label(net, i), p_mw=net.res_trafo.p_hv_mw[i],
                         q_mvar=net.res_trafo.q_hv_mvar[i], loading_pct=net.res_trafo.loading_percent[i],
                         rating_mva=net.trafo.sn_mva[i]))
    branches = pd.DataFrame(rows).sort_values("loading_pct", ascending=False)

    rows = []
    for i in net.gen.index:
        rows.append(dict(machine=gen_label(net, i), bus=bus_no(net, net.gen.bus[i]), role="PV",
                         p_mw=net.res_gen.p_mw[i], q_mvar=net.res_gen.q_mvar[i], vm_pu=net.res_gen.vm_pu[i],
                         p_max_mw=net.gen.max_p_mw[i], q_min_mvar=net.gen.min_q_mvar[i], q_max_mvar=net.gen.max_q_mvar[i]))
    rows.append(dict(machine=slack_label(net), bus=bus_no(net, net.ext_grid.bus[0]), role="slack",
                     p_mw=net.res_ext_grid.p_mw[0], q_mvar=net.res_ext_grid.q_mvar[0], vm_pu=net.ext_grid.vm_pu[0],
                     p_max_mw=net.ext_grid.max_p_mw[0], q_min_mvar=net.ext_grid.min_q_mvar[0], q_max_mvar=net.ext_grid.max_q_mvar[0]))
    gens = pd.DataFrame(rows).sort_values("bus")
    gens["headroom_mw"] = (gens.p_max_mw - gens.p_mw).clip(lower=0.0)

    pv = gens[gens.role == "PV"]
    at_q_limit = pv[(pv.q_mvar - pv.q_min_mvar).abs().lt(1e-3) | (pv.q_max_mvar - pv.q_mvar).abs().lt(1e-3)]
    high = buses[buses.band == "high"]
    summary = {
        "total_load_mw": float(net.res_load.p_mw.sum()),
        "total_load_mvar": float(net.res_load.q_mvar.sum()),
        "total_gen_mw": float(gens.p_mw.sum()),
        "losses_mw": float(net.res_line.pl_mw.sum() + net.res_trafo.pl_mw.sum()),
        "losses_pct_of_load": float(100 * (net.res_line.pl_mw.sum() + net.res_trafo.pl_mw.sum()) / net.res_load.p_mw.sum()),
        "vm_min_pu": float(buses.vm_pu.min()), "vm_min_bus": int(buses.bus[buses.vm_pu.idxmin()]),
        "vm_max_pu": float(buses.vm_pu.max()), "vm_max_bus": int(buses.bus[buses.vm_pu.idxmax()]),
        "buses_above_band": [int(b) for b in high.bus],
        "buses_below_band": [int(b) for b in buses.bus[buses.band == "low"]],
        "peak_branch": branches.element.iloc[0], "peak_branch_loading_pct": float(branches.loading_pct.iloc[0]),
        "branches_over_100pct": int((branches.loading_pct > C.THERMAL_LIMIT_PCT).sum()),
        "slack_p_mw": float(gens.p_mw[gens.role == "slack"].iloc[0]),
        "slack_p_max_mw": float(gens.p_max_mw[gens.role == "slack"].iloc[0]),
        "machines_at_q_limit": list(at_q_limit.machine),
        "total_headroom_mw": float(gens.headroom_mw.sum()),
        "gen30_headroom_mw": float(gens.headroom_mw[gens.bus == 30].iloc[0]),
        "headroom_excl_gen39_mw": float(gens.headroom_mw[gens.bus != 39].sum()),
    }
    return buses, branches, gens, summary


def _terminal_bus(net, label):
    return int(label.split()[1]) if label.startswith("Gen ") else None


def run_scenario(name):
    """All contingencies for one scenario. Returns (per-contingency table, violation table)."""
    opt = C.SCENARIOS[name]
    base = solved_base(opt["qlims"])
    target = float(base.res_ext_grid.p_mw.sum())
    ref_v, ref_th = monitored(base)

    cases, violations = [], []
    for c in contingency_list(base):
        net, facts = run_case(base, c, opt["dispatch"], opt["qlims"], target)
        rows = []
        if net is not None:
            v, th = monitored(net)
            rows = classify(v, th, ref_v, ref_th)
        tripped = _terminal_bus(base, c.label)
        for r in rows:
            r["contingency"] = c.label
            r["at_tripped_unit_terminal"] = r["element"] == f"Bus {tripped}"
        violations += rows

        caused = [r for r in rows if r["category"] != "pre-existing"]
        over = [r for r in caused if r["kind"] == "overload"]
        low = [r for r in caused if r["kind"] == "low_voltage"]
        high = [r for r in caused if r["kind"] == "high_voltage"]
        worst_over = max(over, key=lambda r: r["value"], default=None)
        worst_low = min(low, key=lambda r: r["value"], default=None)
        worst_high = max(high, key=lambda r: r["value"], default=None)
        facts.update(
            overloads=len(over), worst_overload_element=worst_over["element"] if worst_over else "",
            worst_overload_pct=worst_over["value"] if worst_over else float("nan"),
            low_voltage_buses=len(low), lowest_bus=worst_low["element"] if worst_low else "",
            lowest_vm_pu=worst_low["value"] if worst_low else float("nan"),
            high_voltage_buses=len(high), highest_bus=worst_high["element"] if worst_high else "",
            highest_vm_pu=worst_high["value"] if worst_high else float("nan"),
            preexisting_only=len(rows) - len(caused),
        )
        cases.append(facts)

    df = pd.DataFrame(cases)
    df.insert(0, "scenario", name)
    tier = df.status.map({"no_solution": 0, "implausible_solution": 0, "solved": 1})
    df = (df.assign(_t=tier, _o=df.worst_overload_pct.fillna(0.0),
                    _v=(C.V_MIN_PU - df.lowest_vm_pu.fillna(C.V_MIN_PU)) + (df.highest_vm_pu.fillna(C.V_MAX_PU) - C.V_MAX_PU))
          .sort_values(["_t", "load_lost_mw", "_o", "_v", "label"], ascending=[True, False, False, False, True])
          .drop(columns=["_t", "_o", "_v"]).reset_index(drop=True))
    df.insert(1, "rank", df.index + 1)
    cols = ["contingency", "kind", "element", "value", "reference", "category", "at_tripped_unit_terminal"]
    vio = pd.DataFrame(violations, columns=cols)
    vio.insert(0, "scenario", name)
    return df, vio


def scenario_totals(df, vio):
    caused = vio[vio.category != "pre-existing"]
    solved = df[df.status == "solved"]
    return {
        "scenario": df.scenario.iloc[0], "contingencies": len(df),
        "no_solution": int((df.status == "no_solution").sum()),
        "implausible_solution": int((df.status == "implausible_solution").sum()),
        "with_load_lost": int((df.load_lost_mw > 0.01).sum()),
        "with_islanding": int((df.islanded_buses.fillna("") != "").sum()),
        "with_overload": int((solved.overloads > 0).sum()),
        "with_voltage_violation": int(((solved.low_voltage_buses + solved.high_voltage_buses) > 0).sum()),
        "clean": int(((solved.overloads + solved.low_voltage_buses + solved.high_voltage_buses == 0)
                      & (solved.load_lost_mw <= 0.01)).sum()),
        "worst_overload_pct": float(solved.worst_overload_pct.max()),
        "worst_overload_contingency": solved.label[solved.worst_overload_pct.idxmax()],
        "worst_overload_element": solved.worst_overload_element[solved.worst_overload_pct.idxmax()],
        "lowest_vm_pu": float(solved.lowest_vm_pu.min()),
        "highest_vm_pu": float(solved.highest_vm_pu.max()),
        "caused_violation_rows": len(caused),
    }
