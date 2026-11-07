"""N-1 engine: apply an outage, find islands, re-balance, solve, classify violations."""
import copy
from dataclasses import dataclass

import networkx as nx
import pandapower as pp
import pandapower.topology as top

from . import config as C
from .network import (bus_idx, bus_no, gen_label, line_label, slack_label, solve,
                      trafo_label)


@dataclass(frozen=True)
class Contingency:
    label: str
    kind: str  # line | trafo | gen | slack_gen
    index: int


def contingency_list(net):
    """Every line, every transformer, every generator including the swing machine."""
    out = [Contingency(line_label(net, i), "line", i) for i in net.line.index]
    out += [Contingency(trafo_label(net, i), "trafo", i) for i in net.trafo.index]
    out += [Contingency(gen_label(net, i), "gen", i) for i in net.gen.index]
    out += [Contingency(slack_label(net, i), "slack_gen", i) for i in net.ext_grid.index]
    return out


def apply_outage(net, c):
    table = {"line": net.line, "trafo": net.trafo, "gen": net.gen, "slack_gen": net.ext_grid}[c.kind]
    table.at[c.index, "in_service"] = False


def islands(net):
    """Connected bus sets after the outage, biggest load first (buses as pandapower indices)."""
    graph = top.create_nxgraph(net, respect_switches=True)
    comps = [set(c) for c in nx.connected_components(graph)]
    load_at = net.load[net.load.in_service].groupby("bus").p_mw.sum()
    return sorted(comps, key=lambda s: (-sum(load_at.get(b, 0.0) for b in s), -len(s), min(s)))


def live_gens(net, main):
    return net.gen.index[net.gen.in_service & net.gen.bus.isin(main)]


def rebalance(net, main, target_mw, qlims, tol_mw=0.5, max_iter=10):
    """Share a power imbalance across the live machines, leaving the slack near its target.

    Surplus is taken off machines in proportion to their output. A deficit is shared
    in proportion to headroom (Pmax - P), so nobody is pushed past Pmax. Any deficit
    beyond total headroom stays on the slack and is returned as a shortfall.
    """
    shortfall = 0.0
    attempt = solve(net, qlims)
    for _ in range(max_iter):
        if attempt is None:
            return None, shortfall
        err = float(net.res_ext_grid.p_mw[net.ext_grid.in_service].sum()) - target_mw
        if abs(err) < tol_mw:
            return attempt, shortfall
        gens = live_gens(net, main)
        room = (net.gen.loc[gens, "max_p_mw"] - net.gen.loc[gens, "p_mw"]).clip(lower=0.0) \
            if err > 0 else net.gen.loc[gens, "p_mw"].clip(lower=0.0)
        total = float(room.sum())
        move = min(abs(err), total)
        shortfall = max(0.0, err - total) if err > 0 else 0.0
        if move < tol_mw:
            return attempt, shortfall
        sign = 1.0 if err > 0 else -1.0
        net.gen.loc[gens, "p_mw"] += sign * move * room / total
        attempt = solve(net, qlims)
    return attempt, shortfall


def run_case(base_net, c, dispatch, qlims, slack_target_mw):
    """Run one contingency on a copy of base_net. Returns (net or None, facts)."""
    net = copy.deepcopy(base_net)
    load_before = float(net.load.loc[net.load.in_service, "p_mw"].sum())
    gen_before = float(net.gen.loc[net.gen.in_service, "p_mw"].sum()) + \
        float(net.sgen.loc[net.sgen.in_service, "p_mw"].sum()) + slack_target_mw
    apply_outage(net, c)

    comps = islands(net)
    main = comps[0]
    dead = sorted(b for comp in comps[1:] for b in comp)
    slack_bus = int(net.ext_grid.at[0, "bus"])
    slack_lost = c.kind == "slack_gen" or slack_bus not in main

    target = slack_target_mw
    new_slack = None
    if slack_lost:
        # Promote the backup machine: it stops being a PV gen and becomes the slack.
        b = bus_idx(net, C.BACKUP_SLACK_BUS)
        g = net.gen.index[net.gen.bus == b][0]
        target = float(net.gen.at[g, "p_mw"])
        vm = float(net.gen.at[g, "vm_pu"])
        net.gen.at[g, "in_service"] = False
        net.ext_grid.at[0, "in_service"] = False
        pp.create_ext_grid(net, bus=b, vm_pu=vm, va_degree=0.0)
        new_slack = C.BACKUP_SLACK_BUS

    load_after = net.load[net.load.in_service & net.load.bus.isin(main)].p_mw.sum()
    gen_after = float(net.gen.loc[live_gens(net, main), "p_mw"].sum()) + \
        float(net.sgen[net.sgen.in_service & net.sgen.bus.isin(main)].p_mw.sum()) + target

    lost_load = load_before - float(load_after)
    lost_gen = gen_before - gen_after
    unbalanced = abs(lost_gen - lost_load) > 1e-6

    shortfall = 0.0
    if dispatch == "shared" and unbalanced:
        attempt, shortfall = rebalance(net, main, target, qlims)
    else:
        attempt = solve(net, qlims)

    status = "solved"
    if attempt is None:
        status = "no_solution"
    else:
        vm = net.res_bus.vm_pu.dropna()
        if vm.min() < C.V_PLAUSIBLE_PU[0] or vm.max() > C.V_PLAUSIBLE_PU[1]:
            status = "implausible_solution"

    facts = dict(
        label=c.label, kind=c.kind, status=status, solver=attempt or "",
        islanded_buses=" ".join(str(bus_no(net, b)) for b in dead), load_lost_mw=lost_load,
        gen_lost_mw=lost_gen, new_slack_bus=new_slack or "", reserve_shortfall_mw=shortfall,
        slack_mw=float(net.res_ext_grid.p_mw[net.ext_grid.in_service].sum()) if attempt else float("nan"),
    )
    return (net if status == "solved" else None), facts


def monitored(net):
    """Post-solve values of everything we check. NaN (de-energised) rows drop out."""
    v = {bus_no(net, b): float(x) for b, x in net.res_bus.vm_pu.dropna().items()}
    th = {line_label(net, i): float(x) for i, x in net.res_line.loading_percent.dropna().items()}
    th.update({trafo_label(net, i): float(x) for i, x in net.res_trafo.loading_percent.dropna().items()})
    return v, th


def classify(v, th, ref_v, ref_th):
    """Compare a solved state with a reference state and list violations.

    new         inside limits in the reference, outside now
    worsened    outside in the reference, and worse by more than the margin
    pre-existing outside in the reference and not meaningfully worse
    """
    rows = []
    for bus, x in v.items():
        for kind, bad, ref_bad, excess in (
            ("low_voltage", x < C.V_MIN_PU, ref_v.get(bus, 1.0) < C.V_MIN_PU, ref_v.get(bus, 1.0) - x),
            ("high_voltage", x > C.V_MAX_PU, ref_v.get(bus, 1.0) > C.V_MAX_PU, x - ref_v.get(bus, 1.0)),
        ):
            if bad:
                cat = "new" if not ref_bad else ("worsened" if excess > C.WORSENED_V_PU else "pre-existing")
                rows.append(dict(kind=kind, element=f"Bus {bus}", value=x, reference=ref_v.get(bus), category=cat))
    for el, x in th.items():
        if x > C.THERMAL_LIMIT_PCT:
            ref = ref_th.get(el, 0.0)
            ref_bad = ref > C.THERMAL_LIMIT_PCT
            cat = "new" if not ref_bad else ("worsened" if x - ref > C.WORSENED_LOADING_PCT else "pre-existing")
            rows.append(dict(kind="overload", element=el, value=x, reference=ref, category=cat))
    return rows
