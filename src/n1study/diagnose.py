"""Why does losing Gen 39 not solve? Walk towards the outage in small warm-started steps.

Stage 1 ramps the machine's MW to zero while it still supplies vars. Stage 2 then
lowers its var ceiling, because a real outage removes both. Warm starts separate a
real solvability limit from a bad starting point for one big jump.
"""
import copy

import pandapower as pp

from .contingency import islands, live_gens
from .network import bus_idx, bus_no
from .study import solved_base


def _balance(net, target, others):
    """Solve, then share any slack excess across machines by headroom. Returns shortfall."""
    err = 0.0
    for _ in range(12):
        pp.runpp(net, enforce_q_lims=True, numba=False, init="results", max_iteration=40)
        err = float(net.res_ext_grid.p_mw.sum()) - target
        room = (net.gen.loc[others, "max_p_mw"] - net.gen.loc[others, "p_mw"]).clip(lower=0.0)
        if abs(err) < 0.5 or room.sum() < 0.5:
            break
        net.gen.loc[others, "p_mw"] += min(err, room.sum()) * room / room.sum()
    return max(0.0, err)


def _row(net, g, bus, stage, short):
    vm = net.res_bus.vm_pu
    return dict(
        stage=stage, gen_p_mw=float(net.gen.at[g, "p_mw"]), gen_q_mvar=float(net.res_gen.q_mvar[g]),
        solved=True, bus_vm_pu=float(vm[bus_idx(net, bus)]), min_vm_pu=float(vm.min()),
        min_vm_bus=bus_no(net, int(vm.idxmin())),
        max_loading_pct=float(max(net.res_line.loading_percent.max(), net.res_trafo.loading_percent.max())),
        reserve_shortfall_mw=short,
    )


def trace_gen_loss(bus=39, p_step_mw=50.0, q_step_mvar=10.0):
    base = solved_base(True)
    net = copy.deepcopy(base)
    target = float(base.res_ext_grid.p_mw.sum())
    g = net.gen.index[net.gen.bus == bus_idx(net, bus)][0]
    others = [i for i in live_gens(net, islands(net)[0]) if i != g]

    rows = []
    p = float(net.gen.at[g, "p_mw"])
    while p >= 0:
        net.gen.at[g, "p_mw"] = p
        try:
            short = _balance(net, target, others)
        except pp.LoadflowNotConverged:
            rows.append(dict(stage="ramp MW", gen_p_mw=p, solved=False))
            return rows
        rows.append(_row(net, g, bus, "ramp MW", short))
        p -= p_step_mw

    q = float(net.gen.at[g, "max_q_mvar"]) - q_step_mvar
    while q >= 0:
        net.gen.at[g, "max_q_mvar"] = q
        try:
            short = _balance(net, target, others)
        except pp.LoadflowNotConverged:
            rows.append(dict(stage="lower Mvar", gen_p_mw=0.0, gen_q_mvar=q, solved=False))
            return rows
        rows.append(_row(net, g, bus, "lower Mvar", short))
        q -= q_step_mvar
    return rows
