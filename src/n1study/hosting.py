"""Solar hosting-capacity sweep: a steady-state screening estimate, not an interconnection study.

For each bus, add unity-power-factor solar in steps and re-run the whole N-1 set out
to the sweep cap, with no early stop. Every limit breach at every step is recorded
next to the value the same contingency gave at 0 MW, so hosting capacity under any
definition is a query over one fixed table (see hosting_definitions).
"""
import copy

import pandapower as pp
import pandas as pd

from . import config as C
from .contingency import classify, contingency_list, monitored, run_case
from .network import bus_idx, solve
from .study import solved_base

BASE = "BASE (no outage)"


def with_solar(base, bus_number, mw, dispatch):
    """Base net with solar added. Returns (solved net or None, slack target)."""
    net = copy.deepcopy(base)
    slack0 = float(base.res_ext_grid.p_mw.sum())
    pp.create_sgen(net, bus=bus_idx(net, bus_number), p_mw=mw, q_mvar=0.0, name="solar")
    if dispatch == "shared":
        # Every machine, the slack included, backs off in proportion to its output.
        scale = 1.0 - mw / (float(net.gen.p_mw.sum()) + slack0)
        net.gen["p_mw"] *= scale
        target = slack0 * scale
    else:
        target = slack0 - mw  # only the swing machine backs off
    return (net if solve(net, True) else None), target


def references(base, dispatch):
    """Solved state of every contingency at 0 MW solar: what solar is judged against."""
    target = float(base.res_ext_grid.p_mw.sum())
    refs = {BASE: monitored(base)}
    for c in contingency_list(base):
        out, _ = run_case(base, c, dispatch, True, target)
        refs[c.label] = monitored(out) if out is not None else None
    return refs


def _breaches(state, ref):
    """Rows for everything outside limits in state, with its 0 MW value and whether it was already out."""
    rows = classify(*state, *ref)
    return [dict(kind=r["kind"], element=r["element"], value=r["value"], reference=r["reference"],
                 already_out_at_0mw=r["category"] != "new") for r in rows]


def sweep(dispatch):
    """Returns (breach rows, one row per step). Contingencies unsolved at 0 MW are skipped."""
    base = solved_base(True)
    refs = references(base, dispatch)
    labels = [c for c in contingency_list(base) if refs[c.label] is not None]
    slack0 = float(base.res_ext_grid.p_mw.sum())
    rows, steps = [], []
    for b in C.HOSTING_BUSES:
        mw = C.HOSTING_STEP_MW
        while mw <= C.HOSTING_MAX_MW + 1e-9:
            if dispatch == "single" and mw > slack0:
                steps.append(dict(dispatch=dispatch, bus=b, solar_mw=mw, stopped="swing machine at 0 MW"))
                break  # the swing has nothing left to back off
            tag = dict(dispatch=dispatch, bus=b, solar_mw=mw)
            net, target = with_solar(base, b, mw, dispatch)
            if net is None:
                rows.append(dict(tag, contingency=BASE, kind="no_solution"))
            else:
                rows += [dict(tag, contingency=BASE, **r) for r in _breaches(monitored(net), refs[BASE])]
                for c in labels:
                    out, facts = run_case(net, c, dispatch, True, target)
                    if out is None:
                        rows.append(dict(tag, contingency=c.label, kind=facts["status"]))
                    else:
                        rows += [dict(tag, contingency=c.label, **r) for r in _breaches(monitored(out), refs[c.label])]
            steps.append(dict(tag, stopped=""))
            mw += C.HOSTING_STEP_MW
    cols = ["dispatch", "bus", "solar_mw", "contingency", "kind", "element", "value", "reference", "already_out_at_0mw"]
    return pd.DataFrame(rows, columns=cols), pd.DataFrame(steps)
