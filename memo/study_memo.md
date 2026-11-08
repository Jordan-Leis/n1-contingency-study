# Study memo: steady-state N-1 screening, IEEE 39-bus test system

**Date:** November 2026  
**From:** Jordan Leis (student practice study, built with Claude Code)  
**Status:** practice exercise on a public test case. Not a real system, not PSS/E.

**Purpose.** Screen the IEEE 39-bus test system for single-contingency (N-1) thermal and voltage problems, and estimate how much solar six buses could take before an N-1 problem appears.

**Method.** AC Newton-Raphson load flow in pandapower (tolerance 1e-8 MVA), constant-power loads at the case's single load level, taps and shunts fixed. Each of 56 elements was removed in turn (35 lines, 11 transformers, 10 machines) and re-solved from the base solution. Criteria: 0.95-1.05 pu at every energised bus (the normal band, also applied after the outage) and 100% of the case's single rating, with loading measured as current against the rating at nominal voltage. Var limits apply to PV machines; the swing machine's vars are unlimited. Lost generation is shared across PV machines by headroom (Pmax - P). Buses cut off by an outage are treated as de-energised. A problem counts against an outage only if it is new, or more than 1 point or 0.005 pu worse than before it.

**Base case.** 6,254 MW load, 43.6 MW losses (0.70%). Peak loading Xfmr 10-32 at 77%. 7 buses (19, 22, 25, 26, 28, 29, 36) already sit above 1.05 pu (highest 1.0636 pu at bus 36, a generator setpoint). The swing machine at bus 31 runs at 678 MW against a 646 MW Pmax. These are conditions of the case, not contingency results.

**Results.** 22 of 56 outages are clean; 24 cause an overload and 13 a new or worsened voltage violation (2 only at the terminal bus of the tripped unit); 3 lose load (categories overlap). The worst overload is Line 23-24 at 158% with Line 21-22 out, the only other exit from the Gen 35/36 pocket. Line 16-19 is the only tie to buses 19, 20, 33 and 34: losing it separates 1,140 MW of generation and 680 MW of load, counted here as lost. Losing Gen 39 has no AC solution, but bus 39 is the case's equivalent of the external system, so this is a model-boundary result, not a credible single contingency. Stepped down slowly, it solves until the unit's var support falls to 230 Mvar (bus 39 at 0.835 pu), when the other machines are also 62 MW short of real power.

**What the assumptions change.** Line 2-3 is the worst element in 7 of 9 solved machine outages mainly because 790 of the 1101 MW of headroom sits on Gen 30. With the swing machine taking all lost MW instead, 14 outages overload rather than 24. For solar, the rule matters as much as the bus: under the N-1 study's own rule, 8 of 12 bus and dispatch cases take under 50 MW, because they push existing overloads further. Counting only new problems gives up to 300 MW, and at bus 8 that is 200 MW if all machines back off or 550 MW if only the swing does.

**Limits.** Steady-state AC only: no short circuit, no dynamics, no protection or remedial actions. Public textbook case with one rating per branch, not a real system. Not PSS/E. Hosting numbers are a screening estimate, not an interconnection study.

**Conclusions.** The thermal issues that do not depend on the dispatch assumption are the outlet of the Gen 35/36 pocket (Line 23-24) and the corridor carrying Gen 31/32 output around buses 4-14 and 6-13, where 5 line outages overload a corridor line in both dispatch models (worst 133%). Line 2-3 overloads mainly under headroom sharing. Bus 20 hangs on one transformer. Because the case already fails N-1, any new solar near these elements would be judged against existing overloads, and how those are assigned decides the answer.

**Worst five contingencies** (primary scenario)

| Rank | Outage | Result | Worst problem caused |
|---:|---|---|---|
| 1 | Gen 39 | No AC solution found (1,000 MW lost). Model boundary: bus 39 is the external-system equivalent | not assessed (no solution) |
| 2 | Line 16-19 | Islands bus 19, 20, 33, 34: 680 MW load lost | Line 2-3 at 109% |
| 3 | Xfmr 19-20 | Islands bus 20, 34: 680 MW load lost | none |
| 4 | Xfmr 6-31 | Islands bus 31: 9 MW load lost | Line 2-3 at 133% (+1 more) |
| 5 | Line 21-22 | Solved | Line 23-24 at 158% (+2 more) |

![One-line diagram with the worst N-1 results marked](../figures/one_line.png)
