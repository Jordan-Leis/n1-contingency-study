"""Three checks that do not trust the main loop.

1. Re-run the outages through pandapower's own contingency tool and compare.
2. Solve the worst thermal case with a separate Newton-Raphson written here from
   the branch data, sharing no solver code with pandapower.
3. Arithmetic a person can do on paper: a cut-set, an island and a slack pick-up.
"""
import copy

import numpy as np
import pandapower as pp
import pandapower.contingency as pc

from .contingency import contingency_list, islands, monitored, run_case
from .network import bus_idx, bus_no, line_label, solve, trafo_label
from .study import solved_base


def against_pandapower():
    """Same outages, same options, single slack, no Q limits, through run_contingency."""
    base = solved_base(False)
    target = float(base.res_ext_grid.p_mw.sum())
    slack_bus = int(base.ext_grid.bus[0])

    lines, trafos = list(base.line.index), []
    for i in base.trafo.index:
        probe = copy.deepcopy(base)
        probe.trafo.at[i, "in_service"] = False
        if slack_bus in islands(probe)[0]:  # the tool cannot move the slack
            trafos.append(int(i))
        # skipped case is Xfmr 6-31, which strands the slack

    mine_v_max, mine_v_min, mine_th = {}, {}, {}
    ok = {c.label for c in contingency_list(base)}
    used = 0
    for c in contingency_list(base):
        if c.kind == "line" or (c.kind == "trafo" and c.index in trafos):
            net, _ = run_case(base, c, "single", False, target)
            used += 1
            v, th = monitored(net)
            for b, x in v.items():
                mine_v_max[b] = max(mine_v_max.get(b, x), x)
                mine_v_min[b] = min(mine_v_min.get(b, x), x)
            for e, x in th.items():
                mine_th[e] = max(mine_th.get(e, x), x)

    tool = copy.deepcopy(base)
    opts = dict(numba=False, init="dc")
    pc.run_contingency(tool, {"line": {"index": lines}, "trafo": {"index": trafos}},
                       pf_options=opts, pf_options_nminus1=opts)
    d_v = max(
        max(abs(tool.res_bus.max_vm_pu[b] - mine_v_max[bus_no(tool, b)]) for b in tool.bus.index),
        max(abs(tool.res_bus.min_vm_pu[b] - mine_v_min[bus_no(tool, b)]) for b in tool.bus.index))
    d_l = max(abs(tool.res_line.max_loading_percent[i] - mine_th[line_label(tool, i)]) for i in tool.line.index)
    d_t = max(abs(tool.res_trafo.max_loading_percent[i] - mine_th[trafo_label(tool, i)]) for i in tool.trafo.index)
    return {
        "scope": "line and transformer outages, single slack, no Q limits",
        "cases_compared": used, "cases_not_compared": ["Xfmr 6-31 (strands the slack)", "all generator outages"],
        "max_abs_diff_vm_pu": float(d_v), "max_abs_diff_line_loading_pct": float(d_l),
        "max_abs_diff_trafo_loading_pct": float(d_t),
    }


def independent_newton(net, tol=1e-9, max_iter=30):
    """Polar Newton-Raphson from net's internal per-unit branch table. Numpy only.

    Takes bus types and injections from the solved case's ppc tables, builds Ybus
    itself, and solves with a dense Jacobian. PV buses hold voltage (no Q limits).
    """
    ppc = net._ppc["internal"]
    bus, gen, br, base = ppc["bus"], ppc["gen"], ppc["branch"], ppc["baseMVA"]
    n = bus.shape[0]
    f, t = br[:, 0].real.astype(int), br[:, 1].real.astype(int)
    y = 1 / (br[:, 2].real + 1j * br[:, 3].real)
    bc = br[:, 4].real
    tap = np.where(br[:, 8].real == 0, 1.0, br[:, 8].real) * np.exp(1j * np.deg2rad(br[:, 9].real))
    Y = np.zeros((n, n), complex)
    for k in range(len(f)):
        if br[k, 10].real == 0:
            continue
        ys = y[k]
        Y[f[k], f[k]] += (ys + 1j * bc[k] / 2) / abs(tap[k]) ** 2
        Y[t[k], t[k]] += ys + 1j * bc[k] / 2
        Y[f[k], t[k]] += -ys / np.conj(tap[k])
        Y[t[k], f[k]] += -ys / tap[k]
    Y += np.diag((bus[:, 4].real + 1j * bus[:, 5].real) / base)

    sbus = -(bus[:, 2].real + 1j * bus[:, 3].real) / base
    for g in gen:
        if g[7].real > 0:
            sbus[int(g[0].real)] += (g[1].real + 1j * g[2].real) / base
    btype = bus[:, 1].real.astype(int)
    pv, pq, ref = np.where(btype == 2)[0], np.where(btype == 1)[0], np.where(btype == 3)[0]

    vm = np.ones(n)
    va = np.zeros(n)
    for g in gen:
        if g[7].real > 0:
            vm[int(g[0].real)] = g[5].real
    va[ref] = np.deg2rad(bus[ref, 8].real)
    pvpq = np.r_[pv, pq]
    for it in range(max_iter):
        v = vm * np.exp(1j * va)
        i = Y @ v
        mis = v * np.conj(i) - sbus
        fvec = np.r_[mis[pvpq].real, mis[pq].imag]
        if np.abs(fvec).max() < tol:
            return vm, va, it
        d_va = 1j * np.diag(v) @ np.conj(np.diag(i) - Y @ np.diag(v))
        d_vm = np.diag(v) @ np.conj(Y @ np.diag(v / vm)) + np.conj(np.diag(i)) @ np.diag(v / vm)
        J = np.block([[d_va[np.ix_(pvpq, pvpq)].real, d_vm[np.ix_(pvpq, pq)].real],
                      [d_va[np.ix_(pq, pvpq)].imag, d_vm[np.ix_(pq, pq)].imag]])
        dx = np.linalg.solve(J, -fvec)
        va[pvpq] += dx[:len(pvpq)]
        vm[pq] += dx[len(pvpq):]
    raise RuntimeError("independent Newton did not converge")


def independent_solver_check():
    """Worst thermal contingency solved twice: pandapower vs the numpy Newton above."""
    base = solved_base(False)
    target = float(base.res_ext_grid.p_mw.sum())
    c = next(c for c in contingency_list(base) if c.label == "Line 21-22")
    net, _ = run_case(base, c, "single", False, target)
    vm, va, iters = independent_newton(net)
    lookup = net._pd2ppc_lookups["bus"]
    live = [b for b in net.bus.index if not np.isnan(net.res_bus.vm_pu[b])]
    d_v = max(abs(vm[lookup[b]] - net.res_bus.vm_pu[b]) for b in live)
    d_a = max(abs(np.rad2deg(va[lookup[b]]) - net.res_bus.va_degree[b]) for b in live)
    return {"contingency": c.label, "newton_iterations": iters,
            "max_abs_diff_vm_pu": float(d_v), "max_abs_diff_angle_deg": float(d_a)}


def hand_checks():
    """Cut-set, island and generator pick-up arithmetic, each against the study value."""
    base = solved_base(True)
    target = float(base.res_ext_grid.p_mw.sum())
    by_label = {c.label: c for c in contingency_list(base)}

    # With Line 21-22 out, buses 22, 23, 35, 36 reach the rest of the system only through Line 23-24.
    gen_p = lambda b: float(base.gen.p_mw[base.gen.bus == bus_idx(base, b)].sum())
    load_p = lambda b: float(base.load.p_mw[base.load.bus == bus_idx(base, b)].sum())
    pocket_export = gen_p(35) + gen_p(36) - load_p(23)
    rating = (3 ** 0.5) * 345 * float(base.line.max_i_ka[[i for i in base.line.index if line_label(base, i) == "Line 23-24"][0]])
    net, _ = run_case(base, by_label["Line 21-22"], "shared", True, target)
    i = [i for i in net.line.index if line_label(net, i) == "Line 23-24"][0]
    solved_p = max(abs(net.res_line.p_from_mw[i]), abs(net.res_line.p_to_mw[i]))
    cutset = {
        "pocket_gen_minus_load_mw": pocket_export, "line_23_24_rating_mva": rating,
        "hand_estimate_loading_pct": 100 * pocket_export / rating,
        "solved_line_23_24_p_mw": solved_p, "solved_loading_pct": float(net.res_line.loading_percent[i]),
    }

    # Xfmr 19-20 strands bus 20 (680 MW load) with bus 34 (Gen 34, 508 MW).
    _, f = run_case(base, by_label["Xfmr 19-20"], "single", True, target)
    island = {
        "hand_load_lost_mw": load_p(20), "study_load_lost_mw": f["load_lost_mw"],
        "hand_gen_lost_mw": gen_p(34), "study_gen_lost_mw": f["gen_lost_mw"],
        "hand_slack_estimate_mw": target - (load_p(20) - gen_p(34)), "study_slack_mw": f["slack_mw"],
    }

    # Losing Gen 38 (830 MW) with one slack: bus 31 output rises by 830 MW plus any change in losses.
    _, f = run_case(base, by_label["Gen 38"], "single", True, target)
    pickup = {
        "lost_mw": gen_p(38), "slack_before_mw": target, "slack_after_mw": f["slack_mw"],
        "pickup_mw": f["slack_mw"] - target, "implied_extra_losses_mw": f["slack_mw"] - target - gen_p(38),
        "slack_p_max_mw": float(base.ext_grid.max_p_mw[0]),
    }
    return {"cutset_line_21_22": cutset, "island_xfmr_19_20": island, "single_slack_pickup_gen_38": pickup}
