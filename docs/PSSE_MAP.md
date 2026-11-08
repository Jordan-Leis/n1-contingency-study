# Script steps mapped to PSS/E `psspy` calls

> **UNTESTED.** None of this has been run. Jordan has no PSS/E licence, so this repo contains no `psspy` code. It is a reading exercise: the same study steps, matched to the API names a PSS/E script would use.

**How the names were checked.** Each name and signature below was found by text search in a public `help(psspy)` dump from a PSS/E 34 install ([`psspy.txt`](https://raw.githubusercontent.com/jbarberia/psse_docs/1331cea8d47c17cd07fac15ae4bac3715612edc0/psspy.txt), file path `psse34\psspy39`). That is a third-party copy, not the Siemens manual, and I did not read the manual. **Suffixes change between releases.** For example, `machine_chng_2` is the variant in this v34 dump, and public scripts recorded on v35 use `machine_chng_4`.

| Step in this repo | pandapower here | `psspy` equivalent (v34 dump) | Status |
|---|---|---|---|
| Start the engine | not needed | `psseinit(buses)` | Name and signature confirmed |
| Load the case | `networks.case39()` | `case(sfile)` for a `.sav`; `read(numnam, ifile)` or `readrawversion(numnam, vernum, ifile)` for a `.raw` | Confirmed |
| Solve the load flow | `runpp(net)` | `fnsl(options)`, full Newton | Confirmed |
| Flat start | `runpp(init="flat")` | `fnsl`, `OPTIONS(6)` = 1 | Confirmed |
| Apply generator Q limits | `runpp(enforce_q_lims=True)` | `fnsl`, `OPTIONS(7)` = 0 to apply at once, n > 0 from iteration n, -1 to ignore | Confirmed. Pandapower's outer-loop PV-to-PQ switching is not claimed to match PSS/E's logic |
| Check it solved | `LoadflowNotConverged` exception | `solved()`: e.g. 0 met tolerance, 1 iteration limit, 2 blown up, 3 non-divergent stop, 5 singular Jacobian (the dump lists more codes) | Confirmed |
| Outage a line | `net.line.in_service = False` | `branch_chng_3(ibus, jbus, ckt, intgar1=0)`, where `INTGAR(1)` is status | Confirmed. The keyword form is from public scripts |
| Outage a transformer | `net.trafo.in_service = False` | `two_winding_chng_6(ibus, jbus, ckt, intgar1=0)`, where `INTGAR(1)` is status | Confirmed for the status field. Keyword form not checked on this function |
| Outage a generator | `net.gen.in_service = False` | `machine_chng_2(ibus, id, intgar1=0)`, where `INTGAR(1)` is status | Confirmed for v34. Keyword form not checked on this function |
| Find islands | `topology.create_nxgraph` + `networkx` | `tree(apiopt, option)` finds swingless islands; `fnsl` returns `IERR` 3 if one exists | Confirmed |
| Read bus voltages | `net.res_bus.vm_pu` | `abusreal(sid, flag, string)` with `string="PU"`; `abusint` for numbers | Confirmed |
| Read branch loading | `net.res_line.loading_percent` | `aflowreal(sid, owner, ties, flag, string)` with `PCTRATE` ("percent from bus current of default rating set") or `PCTMVARATE` (MVA); `abrnreal` for branch quantities | Confirmed. `PCTRATE` is current-based like pandapower, but it reads the from-bus end, while pandapower takes the larger of the two ends |
| Pick a rating set | one rating in the case | `rating_set(ival)`; `rate_2(sid, all, linflg, trnflg, brkflg, rating, fmax)` reports overloads | Confirmed |
| Whole N-1 loop | Python `for` loop in `study.py` | `dfax_2(options, subfile, monfile, confile, dfxfile)`, then `accc_with_dsp_3(tol, optacc, label, dfxfile, accfile, thrfile, inlfile, zipfile)` | Confirmed. This would replace the loop; the `.sub`, `.mon` and `.con` input files are not written here |
| Share lost generation | `rebalance()` in `contingency.py` | `accc_with_dsp_3`, `OPTACC(10)`: 0 disabled, 1 reserve, 2 Pmax, 3 inertia, 4 governor droop | Mode names confirmed. **How each mode allocates MW is unconfirmed**, so I do not claim `rebalance()` matches mode 1 |
| Read ACCC results | `n1_contingencies.csv` | `pssarrays.accc_solution`, `pssarrays.accc_summary` | **Unconfirmed.** These are not in the `psspy` dump (they live in a separate `pssarrays` module). The names come from public scripts and forum posts only; arguments and return fields unknown |
| Add a solar plant | `create_sgen(net, bus, p_mw, q_mvar=0)` | `plant_data_4(ibus, inode, intgar, realar)`, then `machine_data_2(i, id, intgar, realar)` with `REALAR(1)` = PG, `REALAR(2)` = QG | Confirmed names. A renewable machine would also need control-mode fields that I did not check |
| Sweep MW until a limit | `sweep()` in `hosting.py` | `pv_engine_6(...)` is the PV-analysis engine; `tltg(...)` does linear transfer limits | Names confirmed. Whether either is how an engineer would run this sweep is unknown to me |

## Known gaps

- I have not seen the Siemens API manual, only a `help()` dump and public scripts.
- One public PDF says `case` opens `.raw` files. The v34 dump says Saved Case files only, so this table follows the dump.
- The mapping is step by step, not behaviour by behaviour. Solver defaults, tolerances and Q-limit handling differ, and the numbers would not be identical even on the same case.
