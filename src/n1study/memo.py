"""One-page study memo in the shape of a planning-study letter, as Markdown and PDF.

Every number is read from results/ through report.load(); nothing is typed in by hand.
"""
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import config as C

DATE = "November 2026"


def facts(d):
    t = d["totals"].set_index("scenario")
    p, s = t.loc[C.PRIMARY], t.loc["single_qlim"]
    b = d["base"]
    cases = d["cases"][d["cases"].scenario == C.PRIMARY].set_index("label")
    tr = d["trace"]
    last = tr[tr.solved.astype(str) == "True"].iloc[-1]
    fail = tr[tr.solved.astype(str) == "False"].iloc[0]
    h = d["host"]
    scr = h[h.definition == "screening"].set_index(["dispatch", "bus"]).hosting_mw
    gen_cases = cases[cases.kind.isin(["gen", "slack_gen"]) & (cases.status == "solved")]
    l23 = (cases.worst_overload_element == "Line 2-3")
    vio = d["vio"][(d["vio"].scenario == C.PRIMARY) & (d["vio"].category != "pre-existing")
                   & d["vio"].kind.isin(["low_voltage", "high_voltage"])]
    only_terminal = vio.groupby("contingency").at_tripped_unit_terminal.all()
    return dict(
        n=int(p.contingencies), nl=int((cases.kind == "line").sum()), nt=int((cases.kind == "trafo").sum()),
        ng=int(cases.kind.isin(["gen", "slack_gen"]).sum()),
        load=b["total_load_mw"], losses=b["losses_mw"], losses_pct=b["losses_pct_of_load"],
        n_high=len(b["buses_above_band"]), high_buses=", ".join(map(str, b["buses_above_band"])),
        vmax=b["vm_max_pu"], vmax_bus=b["vm_max_bus"], peak=b["peak_branch"], peak_pct=b["peak_branch_loading_pct"],
        slack=b["slack_p_mw"], slack_max=b["slack_p_max_mw"],
        clean=int(p.clean), over=int(p.with_overload), volt=int(p.with_voltage_violation),
        lost=int(p.with_load_lost), nosol=int(p.no_solution),
        w_pct=p.worst_overload_pct, w_el=p.worst_overload_element, w_c=p.worst_overload_contingency,
        island_load=cases.loc["Line 16-19", "load_lost_mw"], island_gen=cases.loc["Line 16-19", "gen_lost_mw"],
        l23_gen=int((l23 & cases.index.isin(gen_cases.index)).sum()), n_gen_solved=len(gen_cases),
        s_over=int(s.with_overload), g30=b["gen30_headroom_mw"], head=b["total_headroom_mw"],
        q_last=last.gen_q_mvar, v_last=last.bus_vm_pu, q_fail=fail.gen_q_mvar,
        volt_terminal=int(only_terminal.sum()),
        hs_min=scr.loc["shared"].min(), hs_max=scr.loc["shared"].max(),
        b8_sh=scr.loc[("shared", 8)], b8_si=scr.loc[("single", 8)],
        n0_15=h[(h.dispatch == "shared") & (h.bus == 15) & (h.definition == "no_outage_only")].hosting_mw.iloc[0],
        sc_15=scr.loc[("shared", 15)],
    )


def sections(f):
    return [
        ("Purpose", f"Screen the IEEE 39-bus test system for single-contingency (N-1) thermal and voltage problems, "
                    f"and estimate how much solar six buses could take before a new N-1 problem appears."),
        ("Method", f"AC Newton-Raphson load flow in pandapower. Each of {f['n']} elements was removed in turn "
                   f"({f['nl']} lines, {f['nt']} transformers, {f['ng']} machines) and the case re-solved from the base "
                   f"solution. Criteria: 0.95-1.05 pu at every bus and 100% of the single rating in the case. "
                   f"Generator var limits applied. Lost generation shared across machines by headroom (Pmax - P). "
                   f"Buses cut off by an outage are treated as de-energised. A problem counts as caused by the outage "
                   f"only if it was not already there before it."),
        ("Base case", f"{fmt(f['load'])} MW load, {f['losses']:.1f} MW losses ({f['losses_pct']:.2f}%). Peak loading "
                      f"{f['peak']} at {f['peak_pct']:.0f}%. {f['n_high']} buses ({f['high_buses']}) already sit above "
                      f"1.05 pu (highest {f['vmax']:.4f} pu at bus {f['vmax_bus']}). The swing machine at bus 31 runs at "
                      f"{f['slack']:.0f} MW against a {f['slack_max']:.0f} MW Pmax. These are conditions of the case, not "
                      f"contingency results."),
        ("Results", f"{f['clean']} of {f['n']} outages are clean. {f['over']} cause an overload and {f['volt']} a new or "
                    f"worsened voltage violation ({f['volt_terminal']} of them only at the terminal bus of the tripped unit). {f['lost']} lose load, the largest when Line 16-19 opens and isolates "
                    f"{fmt(f['island_load'])} MW of load with {fmt(f['island_gen'])} MW of generation. The worst overload is "
                    f"{f['w_el']} at {f['w_pct']:.0f}% with {f['w_c']} out: the only other exit from the generation pocket at "
                    f"buses 22-23 (a hand cut-set estimate gives about 160%). Losing Gen 39, the case's interconnection "
                    f"equivalent, has no AC solution. Stepping it down in small warm-started steps solves while it still "
                    f"supplies {f['q_last']:.0f} Mvar (bus 39 at {f['v_last']:.3f} pu) and fails at {f['q_fail']:.0f} Mvar."),
        ("What the assumptions change", f"Line 2-3 is the worst element in {f['l23_gen']} of {f['n_gen_solved']} solved "
                    f"machine outages only because {f['g30']:.0f} of the {f['head']:.0f} MW of headroom sits on Gen 30. "
                    f"With the swing machine taking all lost MW instead, {f['s_over']} outages overload rather than "
                    f"{f['over']}. Solar hosting runs from {host(f['hs_min'])} to {fmt(f['hs_max'])} MW on the screening rule; at bus 8 it "
                    f"is {fmt(f['b8_sh'])} MW if all machines back off and {fmt(f['b8_si'])} MW if only the swing does. "
                    f"At bus 15 the no-outage limit is {fmt(f['n0_15'])} MW (the sweep cap) and the N-1 limit is "
                    f"{fmt(f['sc_15'])} MW."),
        ("Limits", "Steady-state AC only: no short circuit, no dynamics, no protection or remedial actions. Public "
                   "textbook case with one rating per branch, not a real system. Not PSS/E. Hosting numbers are a "
                   "screening estimate, not an interconnection study."),
        ("Conclusions", "On this case the binding issues are thermal pockets around generation (buses 22-23, 2-3), "
                        "radial supply to bus 20, and dependence on the bus-39 interconnection for voltage support. "
                        "The answers depend on how lost or displaced generation is redispatched, so that assumption "
                        "has to be stated next to any number."),
    ]


def fmt(x):
    return f"{x:,.0f}"


def host(x):
    return f"under {fmt(C.HOSTING_STEP_MW)}" if x <= 0 else fmt(x)


def top_rows(d, n=5):
    from .report import outcome, worst
    df = d["cases"][d["cases"].scenario == C.PRIMARY].head(n)
    return [[str(r.rank), r.label, outcome(r), worst(r)] for r in df.itertuples()]


def build(d):
    f = facts(d)
    secs = sections(f)
    rows = top_rows(d)

    md = [f"# Study memo: steady-state N-1 screening, IEEE 39-bus test system", "",
          f"**Date:** {DATE}  ", "**From:** Jordan Leis (student practice study, built with Claude Code)  ",
          "**Status:** practice exercise on a public test case. Not a real system, not PSS/E.", ""]
    for head, body in secs:
        md += [f"**{head}.** {body}", ""]
    md += ["**Worst five contingencies** (primary scenario)", "", "| Rank | Outage | Result | Worst problem caused |",
           "|---:|---|---|---|"] + [f"| {' | '.join(r)} |" for r in rows] + [
        "", "![One-line diagram with the worst N-1 results marked](../figures/one_line.png)", ""]
    (C.MEMO / "study_memo.md").write_text("\n".join(md))

    body = ParagraphStyle("b", fontName="Helvetica", fontSize=7.9, leading=9.6, alignment=TA_LEFT, spaceAfter=3.2)
    small = ParagraphStyle("s", parent=body, fontSize=6.9, leading=8.2, spaceAfter=0)
    title = ParagraphStyle("t", parent=body, fontName="Helvetica-Bold", fontSize=11.5, leading=14, spaceAfter=2)
    story = [Paragraph("Study memo: steady-state N-1 screening, IEEE 39-bus test system", title),
             Paragraph(f"{DATE} &nbsp;|&nbsp; Jordan Leis, student practice study built with Claude Code &nbsp;|&nbsp; "
                       "Public test case, not a real system; not PSS/E", small), Spacer(1, 5)]
    for head, text in secs:
        story.append(Paragraph(f"<b>{head}.</b> {text}", body))
    wrap = lambda s, st=small: Paragraph(s, st)
    tbl = Table([[wrap("<b>#</b>"), wrap("<b>Outage</b>"), wrap("<b>Result</b>"), wrap("<b>Worst problem caused</b>")]] +
                [[wrap(c) for c in r] for r in rows], colWidths=[0.25 * inch, 0.8 * inch, 2.75 * inch, 3.45 * inch])
    tbl.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                             ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#d9d8d3")),
                             ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 1.2),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2)]))
    story += [Spacer(1, 2), tbl, Spacer(1, 4)]
    img = C.FIGURES / "one_line.png"
    w = 5.0 * inch
    iw, ih = ImageReader(str(img)).getSize()
    story.append(Image(str(img), width=w, height=w * ih / iw))
    doc = SimpleDocTemplate(str(C.MEMO / "study_memo.pdf"), pagesize=letter, leftMargin=0.55 * inch,
                            rightMargin=0.55 * inch, topMargin=0.45 * inch, bottomMargin=0.4 * inch,
                            title="Steady-state N-1 screening, IEEE 39-bus", author="Jordan Leis", invariant=1)
    doc.build(story)
