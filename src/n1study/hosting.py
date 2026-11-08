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
    return keep_informative(pd.DataFrame(rows, columns=cols)), pd.DataFrame(steps)


SOLVE_FAIL = ("no_solution", "implausible_solution")


def keep_informative(rows):
    """Drop rows that are already out at 0 MW and no worse now; no definition below uses them."""
    new = ~rows.already_out_at_0mw.astype("boolean").fillna(False)
    worse = ((rows.kind == "overload") & (rows.value > rows.reference)) | \
            ((rows.kind == "high_voltage") & (rows.value > rows.reference)) | \
            ((rows.kind == "low_voltage") & (rows.value < rows.reference))
    return rows[new | worse | rows.kind.isin(SOLVE_FAIL)].reset_index(drop=True)


DEFINITIONS = {
    "any_new": "any limit crossing the same contingency did not show at 0 MW, however small",
    "screening": ("the N-1 study's own rule: a new overload, a new voltage violation more than 0.005 pu past the "
                  "band, an existing violation made worse by more than 1 point or 0.005 pu, or a solve that fails"),
    "new_only": "screening, but ignoring existing violations that solar makes worse (an optimistic upper bound)",
    "no_outage_only": "the screening rule applied to the no-outage case alone, ignoring N-1",
}


def _fails(x, name):
    new = ~x.already_out_at_0mw.astype("boolean").fillna(False)
    solve_fail = x.kind.isin(SOLVE_FAIL)
    past = (x.value - C.V_MAX_PU).where(x.kind == "high_voltage", (C.V_MIN_PU - x.value))
    new_only = solve_fail | (new & ((x.kind == "overload") | (past > C.WORSENED_V_PU)))
    worse_by = (x.value - x.reference).where(x.kind != "low_voltage", x.reference - x.value)
    margin = pd.Series(C.WORSENED_V_PU, index=x.index).where(x.kind != "overload", C.WORSENED_LOADING_PCT)
    screening = new_only | (~new & (worse_by > margin))
    if name == "any_new":
        return solve_fail | new
    if name == "new_only":
        return new_only
    if name == "screening":
        return screening
    return screening & x.contingency.eq(BASE)


def percent_past_limit(x):
    """How far past its limit each row is, in percent of that limit, so overloads and voltages compare."""
    v = 100 * (x.value - C.V_MAX_PU) / C.V_MAX_PU
    v = v.where(x.kind == "high_voltage", 100 * (C.V_MIN_PU - x.value) / C.V_MIN_PU)
    return (x.value - C.THERMAL_LIMIT_PCT).where(x.kind == "overload", v)


def summarise(rows, steps):
    """One row per dispatch, bus and definition: hosting MW and what stopped it."""
    out = []
    for (d, b), g in rows.groupby(["dispatch", "bus"]):
        st = steps[(steps.dispatch == d) & (steps.bus == b)]
        tested = float(st.solar_mw[st.stopped.fillna("") == ""].max())
        for name in DEFINITIONS:
            hit = g[_fails(g, name)]
            if hit.empty:
                out.append(dict(dispatch=d, bus=b, definition=name, hosting_mw=tested, capped=True,
                                limit_mw=float("nan"), limit_contingency="", limit_element="", limit_kind="",
                                limit_value=float("nan"), limit_reference=float("nan")))
                continue
            first = float(hit.solar_mw.min())
            at = hit[hit.solar_mw == first]
            sf = at[at.kind.isin(SOLVE_FAIL)]
            if not sf.empty:
                r = sf.iloc[0]
            else:
                sev = percent_past_limit(at)
                r = at.loc[sev.idxmax()]
            out.append(dict(dispatch=d, bus=b, definition=name, hosting_mw=first - C.HOSTING_STEP_MW, capped=False,
                            limit_mw=first, limit_contingency=r.contingency, limit_element=r.element if isinstance(r.element, str) else "",
                            limit_kind=r.kind, limit_value=r.value, limit_reference=r.reference))
    return pd.DataFrame(out)
