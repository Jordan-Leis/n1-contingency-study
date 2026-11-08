# N-1 contingency screening in Python, IEEE 39-bus

A scripted steady-state planning study on a public test system: a base-case AC load flow, every single outage (N-1) checked for thermal overloads and voltage violations, and a screening estimate of how much solar six buses could take before a new N-1 problem appears.

I built this as a student learning the layer under the dispatch work I've done before. My microgrid project only decided which units should run; it had no network model, so it couldn't say whether the grid could carry the result. This repo is my first pass at that question. **Claude Code wrote most of the code** (see [AI use](#ai-use)), and the study is a textbook exercise, not a real-system result.

**Worst ten single outages** (primary scenario: generator Q limits on, lost MW shared across machines by headroom). Problems already present before the outage are excluded.

<!-- n1_table -->
<!-- /n1_table -->

![One-line diagram of the IEEE 39-bus case with the worst N-1 results marked](figures/one_line.png)

## What the study found

- **22 of 56 outages are clean.** 24 cause an overload, 13 cause a new or worsened voltage violation, and 3 lose load. Two of the 13 voltage cases are only at the terminal bus of the tripped unit.
- **The worst overload is Line 23-24 at 157.7% with Line 21-22 out.** Buses 22 and 23 hold Gen 35 and Gen 36. With Line 21-22 out, Line 23-24 is their only path to the rest of the system. A hand estimate from the pocket's generation minus load (962.5 MW into a 600 MVA line) gives 160.4%.
- **Losing Gen 39 has no AC solution.** Gen 39 is the case's equivalent of the rest of the interconnection. Stepping it down in small warm-started steps shows why. With the unit at 0 MW, the case still solves while the unit supplies 230 Mvar, with bus 39 at 0.835 pu, and it fails at 220 Mvar. That points to a voltage-support limit, not a bad starting guess, but a failed Newton solve is not proof of voltage collapse.
- **Radial supply loses load.** Opening Line 16-19 cuts off buses 19, 20, 33 and 34, which carry 680 MW of load and 1,140 MW of generation. This study treats a cut-off island as de-energised.
- **How lost generation is replaced changes which line overloads.** Line 2-3 is the worst element in 7 of the 9 solved machine outages. That's mainly because 790 of the 1,101 MW of headroom sits on Gen 30, next to Line 2-3. If the swing machine picks up everything instead, 14 outages overload rather than 24, but bus 31 runs far past its 646 MW limit (for example 1,524 MW after losing Gen 38). Neither model is how a real system responds, and both are reported.
- **Solar hosting is small once N-1 is required.** It is a few hundred MW at most on this case, and the answer moves with the dispatch assumption. Bus 8 can take 200 MW if every machine backs off for the solar, or 550 MW if only the swing machine does.

![Bar chart: screening solar hosting capacity for six buses under two dispatch assumptions](figures/hosting_capacity.png)

## Check the data first

Before trusting any study, I checked the inputs. Both findings are in [`results/data_check.json`](results/data_check.json).

- **Thermal ratings.** `pandapower.networks.case14()` has placeholder ratings: lines at 42 to 27,480 kA and transformers at 9,900 MVA. Base-case loading peaks at 1.51%, so a thermal check on that case means nothing. `case39` carries real ratings from MATPOWER: lines 480 to 1,200 MVA and transformers 500 to 1,800 MVA. It is the main case here, so **no ratings are assumed.** The case has a single rating per branch, and I use it for post-contingency checks too, because there is no emergency rating to use.
- **Voltages.** The IEEE 14-bus case has generator setpoints above 1.05 pu (1.06, 1.07 and 1.09), so its base case already breaks the band at 9 buses. The 39-bus case has the same issue on a smaller scale: 7 buses sit above 1.05 pu before any outage, the highest at 1.0636 pu (bus 36's setpoint). The study separates these **base-case conditions** from violations an outage actually causes.
  - **new:** inside the band before the outage, outside after.
  - **worsened:** already outside, and more than 0.005 pu worse (1 percentage point for loading).
  - **pre-existing:** everything else. Reported in the violations file, never counted as caused.
- **Other base-case conditions.** MATPOWER's own file header notes two:
  - The swing machine at bus 31 runs at 678 MW against a 646 MW Pmax.
  - Gen 37 sits at its Qmin.

## Results

**N-1 summary, by scenario** (56 contingencies each):

<!-- scenario_table -->
<!-- /scenario_table -->

Q limits barely move the totals on this case. The dispatch assumption moves them a lot. Under swing-only pick-up, a fallback solver also returned one "solution" with a bus at 1.337 pu. The study flags any solved state outside 0.70 to 1.20 pu as non-physical rather than reporting it.

**Base case** ([`results/base_summary.json`](results/base_summary.json)): 6,254 MW load, 43.6 MW losses (0.70%), peak loading Xfmr 10-32 at 77%. Bus voltages range from 0.982 pu at bus 31 to 1.0636 pu at bus 36.

**Solar hosting capacity** ([`results/hosting_capacity.csv`](results/hosting_capacity.csv)). Solar at unity power factor, added in 50 MW steps up to 1,000 MW, with all 56 contingencies re-run at every step. Gen 39's outage is left out because it has no solution even at 0 MW.

<!-- hosting_table -->
<!-- /hosting_table -->

How to read the table:

- **The literal answer is 0 MW at every bus.** N-1 already fails at 0 MW, so "before an N-1 violation appears" has nothing left to measure.
- **Counting any new limit crossing gives under 50 MW at every bus.** Several buses sit just under 1.05 pu at 0 MW, and the first 50 MW tips one of them over by less than a thousandth of a pu.
- **The screening column is the number I'd quote.** A step fails on a new overload, a new voltage violation more than 0.005 pu past the band (the same margin the N-1 study uses for "worsened"), or a solve that fails.
- **What's excluded.** Problems already there at 0 MW are not scored, even when solar makes them worse. A real interconnection study assigns those with distribution-factor thresholds, which I did not model.
- **Resolution.** Each number is the last 50 MW step that passed, so the true limit lies between that number and the next step.
- **Steps not tested.** Steps past the first failure were not used to define hosting capacity.

This is a **steady-state screening estimate, not an interconnection study.**

## How to run

```bash
make reproduce   # about 15 minutes on one core: study, figures, memo, tests, number check
make quick       # about a minute: everything except the hosting sweep (reuses its committed results)
```

Needs [uv](https://docs.astral.sh/uv/) and Python 3.12. Dependencies are pinned in `uv.lock`. Every number in this README and the memo is read from `results/`, and `make check` fails if the README or memo quotes a number that does not match a value in the summary results files at the precision quoted. It accepts small integers such as bus numbers and counts, so it is a guard against typos and stale numbers, not a full audit.

| Output | What it is |
|---|---|
| [`memo/study_memo.pdf`](memo/study_memo.pdf) ([`.md`](memo/study_memo.md)) | One-page study memo: purpose, method, assumptions, results, conclusions, one-line diagram |
| `results/n1_contingencies.csv` | One row per contingency per scenario, ranked worst first |
| `results/n1_violations.csv` | Every limit breach with its pre-outage value and category |
| `results/gen39_trace.csv` | The step-down trace behind the Gen 39 result |
| `results/crosscheck.json` | The three checks below |
| `results/hosting_*.csv` | Hosting sweep: every breach at every step, and the summary |
| [`docs/PSSE_MAP.md`](docs/PSSE_MAP.md) | Each step mapped to its `psspy` call. **Untested**, because I have no PSS/E licence |

## Method

- **Tool.** pandapower AC Newton-Raphson. Each outage starts from the base-case solution, as a contingency engine would. If that fails, the solver retries with a DC start, then a flat start, then an Iwamoto damped Newton.
- **Contingencies.** Every element in turn: 35 lines, 11 transformers, 9 PV generators and the swing machine.
- **Islands.** Found with a graph search after each outage. Buses cut off from the main system are counted as lost load and lost generation, not solved as islands. If the swing bus is cut off (Xfmr 6-31 or Gen 31), the swing role moves to bus 39.
- **Lost generation (primary).** Shared across the remaining machines in proportion to headroom (Pmax − P), re-solving until the swing machine is back at its pre-outage output. Nobody is pushed past Pmax. In the comparison scenario, the swing machine takes everything.
- **Generator Q limits.** On in the primary scenario (`enforce_q_lims`) and off in a sensitivity run.
- **Criteria.** 0.95 to 1.05 pu at every energised bus, and 100% of the case's rating on every line and transformer. All four scenarios are set in [`src/n1study/config.py`](src/n1study/config.py).

## Checks

All three are in [`results/crosscheck.json`](results/crosscheck.json) and rebuilt by `make reproduce`.

1. **Against pandapower's own contingency tool.** 45 line and transformer outages, run through `pandapower.contingency.run_contingency` with the same options. Voltages agree to within 2.63e-10 pu and loadings to within 1.70e-07 percentage points. This checks the loop and bookkeeping, not the solver, which is shared. Xfmr 6-31 and the machine outages are not compared, because that tool can't move the slack.
2. **Against a separate solver.** `independent_newton()` in [`crosscheck.py`](src/n1study/crosscheck.py) builds the admittance matrix from the branch table in numpy and solves the Line 21-22 outage itself. It converges in 4 iterations and matches pandapower to 2.43e-11 pu. It shares the per-unit branch data, so it would not catch a modelling error in the case conversion.
3. **By hand.** Three cases:
   - **Pocket estimate.** The cut-set calculation above: 160.4% by hand against 157.7% solved. Reactive flow and losses account for the gap.
   - **Lost load.** Losing Xfmr 19-20 should lose 680 MW of load and 508 MW of generation, and the study reports exactly that.
   - **Slack pick-up.** Losing Gen 38 (830 MW) under swing-only pick-up raises the swing machine by 845.9 MW. The extra 15.9 MW is the rise in losses.

There are also 19 tests (`make test`) covering power balance, island handling, slack moves, the dispatch models and violation categories.

## Limitations

- **Steady-state AC load flow only.** No short circuit and no dynamic stability, which are the other two study types in a transmission planning scope. No protection, no remedial action schemes, no switched shunts or tap changers acting after the outage.
- **A textbook case, not a real system.** IEEE 39-bus is a reduced New England model from 1970s stability work. Bus 39 stands in for the rest of the interconnection, and pandapower labels every bus 345 kV, including generator terminals. One rating per branch, with no normal versus emergency distinction.
- **Simplified generation response.** It is neither governor response nor a real redispatch, and the results depend on it, so both bracketing models are shown.
- **Islands are not solved.** The Line 16-19 island has more generation than load, and what it would really do depends on dynamics this study does not model.
- **A failed Newton solve is not proof of collapse.** The Gen 39 trace supports a voltage-support limit, but a continuation power flow or PV curve would be the proper tool.
- **Hosting capacity is a screening estimate.** It covers six buses at 50 MW resolution and one load level, with no short-circuit, stability or distribution-factor criteria.
- **Not PSS/E.** The `psspy` mapping is untested.

## What I'd do next

1. Run the same study in PSS/E with ACCC, and compare the results with this repo case by case. That's the fastest way to learn where my modelling choices differ from the industry tool.
2. Add the other two study types: a fault study, with pandapower's short-circuit module as a start, and a basic dynamic run, to see whether the Gen 39 and Line 16-19 cases survive the transient at all.
3. Replace the dispatch bracket with a rating-proportional governor response, and add normal and emergency ratings.
4. Trace PV curves for the Gen 39 case instead of inferring the limit from failed Newton solves.
5. Learn how real interconnection studies attribute an existing overload to a new project, then redo the hosting screen with those rules instead of mine.

## AI use

Claude Code (Anthropic) wrote most of the code and ran it from a plan I approved, inside the brief I set: case choice, which checks to run, how to report negative results, and what not to claim. I own the design decisions and what I chose to trust. Claude Code also checked the `psspy` names against a public `help(psspy)` dump, drafted this README and the memo, and ran the cross-checks above. The checks are evidence the code does what it says. They are not my own line-by-line review of the code, which is still open.

## Data and licences

Network data: the IEEE 39-bus New England case as shipped in [pandapower](https://www.pandapower.org/) (BSD-3-Clause), converted from [MATPOWER](https://matpower.org/)'s `case39` (BSD-3-Clause). Original source: G. W. Bills et al., *On-Line Stability Analysis Study*, EEI RP90-1, 1970. Ratings: MATPOWER's case header credits the TC Calculator data from PSERC (Cornell).
