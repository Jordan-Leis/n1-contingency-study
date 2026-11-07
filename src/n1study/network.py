"""Load the case and translate between pandapower indices and IEEE bus numbers."""
import contextlib
import io
import logging
import warnings

import numpy as np
import pandapower as pp
import pandapower.networks as nw


logging.getLogger("pandapower").setLevel(logging.ERROR)


def load_case():
    """IEEE 39-bus New England case as shipped by pandapower (MATPOWER case39)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return nw.case39()


def bus_no(net, idx):
    """pandapower bus index -> IEEE bus number used in every report."""
    return int(net.bus.at[idx, "name"])


def bus_idx(net, number):
    """IEEE bus number -> pandapower bus index."""
    return int(net.bus.index[net.bus["name"].astype(int) == number][0])


def line_label(net, i):
    a, b = sorted((bus_no(net, net.line.at[i, "from_bus"]), bus_no(net, net.line.at[i, "to_bus"])))
    return f"Line {a}-{b}"


def trafo_label(net, i):
    a, b = sorted((bus_no(net, net.trafo.at[i, "hv_bus"]), bus_no(net, net.trafo.at[i, "lv_bus"])))
    return f"Xfmr {a}-{b}"


def gen_label(net, i):
    return f"Gen {bus_no(net, net.gen.at[i, 'bus'])}"


def slack_label(net, i=0):
    return f"Gen {bus_no(net, net.ext_grid.at[i, 'bus'])}"


def solve(net, qlims):
    """AC Newton-Raphson with a fallback ladder. Returns the attempt that worked, or None.

    Failing every attempt is reported as a named study result, never raised.
    """
    attempts = [
        ("dc-start NR", dict(init="dc", algorithm="nr")),
        ("flat-start NR", dict(init="flat", algorithm="nr")),
        ("dc-start Iwamoto NR", dict(init="dc", algorithm="iwamoto_nr", max_iteration=50)),
    ]
    if len(net.res_bus) and net.res_bus.vm_pu.notna().any():
        # Start from the last solution, the way a contingency engine starts from the base case.
        attempts.insert(0, ("warm-start NR", dict(init="results", algorithm="nr")))
    for name, kw in attempts:
        try:
            with contextlib.redirect_stdout(io.StringIO()):  # Iwamoto prints every iteration
                pp.runpp(net, enforce_q_lims=qlims, numba=False, **kw)
            return name
        except (pp.LoadflowNotConverged, np.linalg.LinAlgError):
            continue  # Iwamoto raises LinAlgError when it diverges to NaN
    return None
