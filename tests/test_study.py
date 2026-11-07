"""Physics and bookkeeping checks. These pin behaviour, not published numbers."""
import pytest

from n1study import config as C
from n1study.contingency import classify, contingency_list, islands, run_case
from n1study.crosscheck import independent_newton
from n1study.hosting import with_solar
from n1study.network import bus_idx, load_case, solve
from n1study.study import solved_base


@pytest.fixture(scope="module")
def base():
    return solved_base(True)


@pytest.fixture(scope="module")
def target(base):
    return float(base.res_ext_grid.p_mw.sum())


def case(base, label):
    return next(c for c in contingency_list(base) if c.label == label)


def test_every_element_is_a_contingency(base):
    cases = contingency_list(base)
    assert len(cases) == len(base.line) + len(base.trafo) + len(base.gen) + len(base.ext_grid)
    assert len({c.label for c in cases}) == len(cases)


def test_base_case_power_balance(base):
    gen = base.res_gen.p_mw.sum() + base.res_ext_grid.p_mw.sum()
    losses = base.res_line.pl_mw.sum() + base.res_trafo.pl_mw.sum()
    assert gen == pytest.approx(base.res_load.p_mw.sum() + losses, abs=1e-6)


def test_ratings_are_real_not_placeholders(base):
    # The reason this case was chosen over case14 (9,900 MVA placeholders).
    mva = 3 ** 0.5 * 345 * base.line.max_i_ka
    assert mva.max() < 2000 and base.trafo.sn_mva.max() < 2000


def test_radial_outage_islands_named_buses(base, target):
    _, f = run_case(base, case(base, "Xfmr 19-20"), "shared", True, target)
    assert f["status"] == "solved"
    assert f["islanded_buses"] == "20 34"
    assert f["load_lost_mw"] == pytest.approx(680.0)
    assert f["gen_lost_mw"] == pytest.approx(508.0)


def test_stranded_slack_moves_to_backup(base, target):
    _, f = run_case(base, case(base, "Xfmr 6-31"), "single", True, target)
    assert f["status"] == "solved"
    assert f["new_slack_bus"] == C.BACKUP_SLACK_BUS
    assert f["islanded_buses"] == "31"


def test_shared_dispatch_keeps_slack_at_target_and_units_under_pmax(base, target):
    net, f = run_case(base, case(base, "Gen 38"), "shared", True, target)
    assert f["slack_mw"] == pytest.approx(target, abs=0.5)
    live = net.gen[net.gen.in_service]
    assert (live.p_mw <= live.max_p_mw + 1e-6).all()


def test_single_dispatch_puts_everything_on_slack(base, target):
    net, f = run_case(base, case(base, "Gen 38"), "single", True, target)
    assert f["slack_mw"] - target == pytest.approx(830.0, abs=30.0)  # plus change in losses
    assert net.gen.p_mw[net.gen.in_service].sum() == pytest.approx(base.gen.p_mw.sum() - 830.0)


def test_outage_does_not_mutate_the_base_net(base, target):
    before = base.gen.p_mw.copy()
    run_case(base, case(base, "Gen 38"), "shared", True, target)
    assert base.gen.p_mw.equals(before) and base.line.in_service.all()


def test_gen39_is_reported_not_raised(base, target):
    net, f = run_case(base, case(base, "Gen 39"), "shared", True, target)
    assert net is None and f["status"] == "no_solution"


def test_classify_separates_new_worsened_and_preexisting():
    ref_v, ref_th = {1: 1.00, 2: 1.06, 3: 1.06}, {"L": 50.0, "M": 120.0, "N": 120.0}
    v, th = {1: 1.06, 2: 1.07, 3: 1.061}, {"L": 101.0, "M": 125.0, "N": 120.5}
    got = {r["element"]: r["category"] for r in classify(v, th, ref_v, ref_th)}
    assert got == {"Bus 1": "new", "Bus 2": "worsened", "Bus 3": "pre-existing",
                   "L": "new", "M": "worsened", "N": "pre-existing"}


def test_classify_ignores_values_inside_limits():
    assert classify({1: 1.05, 2: 0.95}, {"L": 100.0}, {1: 1.0, 2: 1.0}, {"L": 10.0}) == []


def test_islands_sees_a_single_system_at_base(base):
    assert len(islands(base)) == 1


def test_independent_newton_matches_pandapower():
    net = solved_base(False)
    vm, va, _ = independent_newton(net)
    lookup = net._pd2ppc_lookups["bus"]
    for b in net.bus.index:
        assert vm[lookup[b]] == pytest.approx(net.res_bus.vm_pu[b], abs=1e-7)


@pytest.mark.parametrize("dispatch", ["shared", "single"])
def test_solar_is_balanced_by_the_stated_machines(base, target, dispatch):
    net, new_target = with_solar(base, 15, 200.0, dispatch)
    assert net.res_sgen.p_mw.sum() == pytest.approx(200.0)
    assert net.res_sgen.q_mvar.sum() == pytest.approx(0.0)  # unity power factor
    assert float(net.res_ext_grid.p_mw.sum()) == pytest.approx(new_target, abs=5.0)  # up to change in losses
    if dispatch == "single":
        assert net.gen.p_mw.sum() == pytest.approx(base.gen.p_mw.sum())
    else:
        total = base.gen.p_mw.sum() + target
        assert net.gen.p_mw.sum() == pytest.approx(base.gen.p_mw.sum() * (1 - 200.0 / total))


def test_warm_start_used_after_a_first_solve():
    net = load_case()
    assert solve(net, True) == "dc-start NR"
    assert solve(net, True) == "warm-start NR"


def test_solver_divergence_is_a_result_not_a_crash(monkeypatch):
    import numpy as np
    import pandapower as pp

    def diverged(*a, **k):
        raise np.linalg.LinAlgError("Array must not contain infs or NaNs")

    monkeypatch.setattr(pp, "runpp", diverged)
    assert solve(load_case(), True) is None


def test_bus_numbers_are_ieee_not_pandapower_indices():
    net = load_case()
    assert bus_idx(net, 39) == 38
