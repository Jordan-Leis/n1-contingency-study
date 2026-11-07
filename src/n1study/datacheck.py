"""Step 0: inspect the data before trusting any study built on it."""
import warnings

import pandapower.networks as nw

from . import config as C
from .network import bus_no, solve


def _sqrt3_mva(net):
    return (3 ** 0.5) * net.line.max_i_ka * net.line.from_bus.map(net.bus.vn_kv)


def inspect(net, label):
    solve(net, qlims=False)
    vm = net.res_bus.vm_pu
    over = sorted(bus_no(net, b) for b in vm.index[vm > C.V_MAX_PU])
    under = sorted(bus_no(net, b) for b in vm.index[vm < C.V_MIN_PU])
    setpoints = {bus_no(net, b): float(v) for b, v in zip(net.gen.bus, net.gen.vm_pu)}
    setpoints.update({bus_no(net, b): float(v) for b, v in zip(net.ext_grid.bus, net.ext_grid.vm_pu)})
    return {
        "case": label,
        "buses": len(net.bus), "lines": len(net.line), "transformers": len(net.trafo),
        "generators_incl_slack": len(net.gen) + len(net.ext_grid),
        "line_max_i_ka_min": round(float(net.line.max_i_ka.min()), 4),
        "line_max_i_ka_max": round(float(net.line.max_i_ka.max()), 4),
        "line_rating_mva_min": round(float(_sqrt3_mva(net).min()), 1),
        "line_rating_mva_max": round(float(_sqrt3_mva(net).max()), 1),
        "trafo_sn_mva_min": round(float(net.trafo.sn_mva.min()), 1),
        "trafo_sn_mva_max": round(float(net.trafo.sn_mva.max()), 1),
        "base_peak_line_loading_pct": round(float(net.res_line.loading_percent.max()), 2),
        "base_peak_trafo_loading_pct": round(float(net.res_trafo.loading_percent.max()), 2),
        "gen_setpoints_above_1p05": {str(k): v for k, v in sorted(setpoints.items()) if v > C.V_MAX_PU},
        "base_buses_above_1p05": over,
        "base_buses_below_0p95": under,
        "base_vm_max": round(float(vm.max()), 4),
        "base_vm_min": round(float(vm.min()), 4),
    }


def run():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        c14, c39 = nw.case14(), nw.case39()
    return {"case14": inspect(c14, "IEEE 14-bus"), "case39": inspect(c39, "IEEE 39-bus")}
