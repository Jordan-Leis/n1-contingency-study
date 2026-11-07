"""Run the study. `python -m n1study.run` regenerates every file in results/."""
import json
import sys
import time
import warnings

import pandas as pd

from . import config as C
from . import crosscheck, datacheck, diagnose, hosting, study


def _csv(df, name):
    df.to_csv(C.RESULTS / name, index=False, float_format="%.4f")


def _json(obj, name):
    (C.RESULTS / name).write_text(json.dumps(_round(obj), indent=2) + "\n")


def _round(x):
    """Trim floats so tiny platform differences do not churn the committed files."""
    if isinstance(x, float):
        return float(f"{x:.6g}") if abs(x) < 1e-3 else round(x, 4)
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_round(v) for v in x]
    return x


def step(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    warnings.filterwarnings("ignore")
    C.RESULTS.mkdir(exist_ok=True)

    step("data check")
    _json(datacheck.run(), "data_check.json")

    step("base case")
    buses, branches, gens, summary = study.base_tables(study.solved_base(True))
    _csv(buses, "base_buses.csv")
    _csv(branches, "base_branches.csv")
    _csv(gens, "base_machines.csv")
    _json(summary, "base_summary.json")

    step("N-1, four scenarios")
    all_cases, all_vio, totals = [], [], []
    for name in C.SCENARIOS:
        df, vio = study.run_scenario(name)
        all_cases.append(df)
        all_vio.append(vio)
        totals.append(study.scenario_totals(df, vio))
    _csv(pd.concat(all_cases), "n1_contingencies.csv")
    _csv(pd.concat(all_vio), "n1_violations.csv")
    _csv(pd.DataFrame(totals), "n1_scenario_totals.csv")

    step("Gen 39 diagnosis")
    _csv(pd.DataFrame(diagnose.trace_gen_loss()), "gen39_trace.csv")

    step("cross-checks")
    _json({"pandapower_contingency_tool": crosscheck.against_pandapower(),
           "independent_newton": crosscheck.independent_solver_check(),
           "hand": crosscheck.hand_checks()}, "crosscheck.json")

    if "--skip-hosting" not in sys.argv:
        rows, steps = [], []
        for d in ("shared", "single"):
            step(f"hosting sweep, dispatch={d} (several minutes)")
            r, s = hosting.sweep(d)
            rows.append(r)
            steps.append(s)
        _csv(pd.concat(rows), "hosting_breaches.csv")
        _csv(pd.concat(steps), "hosting_steps.csv")
    step("done")


if __name__ == "__main__":
    main()
