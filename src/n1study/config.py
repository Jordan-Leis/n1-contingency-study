"""Study criteria and assumptions. Every number the study depends on is set here."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"
MEMO = ROOT / "memo"

# Monitoring criteria (from the study brief, not from a real utility's standard).
V_MIN_PU = 0.95
V_MAX_PU = 1.05
THERMAL_LIMIT_PCT = 100.0  # of the single rating in the case (MATPOWER rateA)

# A bus or branch that already breaks a limit before the outage only counts as
# contingency-caused if it gets worse by more than these margins.
WORSENED_V_PU = 0.005
WORSENED_LOADING_PCT = 1.0

# A converged Newton solve outside this band is reported as an implausible
# solution, not as a voltage result: Newton can land on a non-physical root.
V_PLAUSIBLE_PU = (0.70, 1.20)

# If bus 31 (the swing) is lost, the slack moves here: bus 39 is the case's
# equivalent of the rest of the interconnection.
BACKUP_SLACK_BUS = 39

# Hosting-capacity sweep. Buses were fixed for spread across the network before
# any hosting result existed, and were not changed afterwards.
HOSTING_BUSES = [3, 8, 15, 21, 27, 28]
HOSTING_STEP_MW = 50.0
HOSTING_MAX_MW = 1000.0

# Scenarios: how lost generation is replaced, and whether generator Q limits apply.
PRIMARY = "shared_qlim"
SCENARIOS = {
    "shared_qlim": {"dispatch": "shared", "qlims": True},
    "shared_noqlim": {"dispatch": "shared", "qlims": False},
    "single_qlim": {"dispatch": "single", "qlims": True},
    "single_noqlim": {"dispatch": "single", "qlims": False},
}
