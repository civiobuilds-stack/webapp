"""Civio-branded PDF report generation using reportlab."""
import io
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage,
)

FOREST = colors.HexColor("#0D1B3E")
EMERALD = colors.HexColor("#16306B")
SAGE = colors.HexColor("#1E6BFF")
BONE = colors.HexColor("#F8F9F6")
CHARCOAL = colors.HexColor("#1F2421")
MUTED = colors.HexColor("#5C6460")
CIVIO_LOGO = (Path(__file__).parent / "assets" / "civio-icon.png").read_bytes()


def _fmt_inr(v):
    if v is None:
        return "—"
    v = float(v)
    if v >= 1e7:
        return f"Rs {v/1e7:.2f} Cr"
    if v >= 1e5:
        return f"Rs {v/1e5:.2f} L"
    return f"Rs {v:,.0f}"


def _fmt_date(d):
    if not d:
        return "—"
    try:
        return datetime.fromisoformat(str(d).replace("Z", "+00:00")).strftime("%d %b %Y")
    except Exception:
        return str(d)[:10]


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("CivH1", parent=s["Heading1"], textColor=FOREST, fontSize=20, spaceAfter=4, leading=24))
    s.add(ParagraphStyle("CivH2", parent=s["Heading2"], textColor=EMERALD, fontSize=13, spaceBefore=14, spaceAfter=6))
    s.add(ParagraphStyle("CivBody", parent=s["BodyText"], textColor=CHARCOAL, fontSize=9.5, leading=14))
    s.add(ParagraphStyle("CivMuted", parent=s["BodyText"], textColor=MUTED, fontSize=8.5, leading=12))
    s.add(ParagraphStyle("CivCell", parent=s["BodyText"], textColor=CHARCOAL, fontSize=8.5, leading=11))
    s.add(ParagraphStyle("CivCellHead", parent=s["BodyText"], textColor=colors.white, fontSize=8.5, leading=11, fontName="Helvetica-Bold"))
    return s


def _header_footer(canvas, doc, meta, brand=None):
    brand = brand or {"name": "CIVIO", "tagline": "Project Management Consultancy"}
    canvas.saveState()
    w, h = A4
    # Header band
    canvas.setFillColor(FOREST)
    canvas.rect(0, h - 26 * mm, w, 26 * mm, fill=1, stroke=0)
    text_x = 27 * mm
    logo_drawn = False
    if brand.get("logo") or CIVIO_LOGO:
        try:
            canvas.setFillColor(colors.white)
            canvas.roundRect(13 * mm, h - 22 * mm, 18 * mm, 18 * mm, 2 * mm, fill=1, stroke=0)
            canvas.drawImage(ImageReader(io.BytesIO(brand.get("logo") or CIVIO_LOGO)), 14 * mm, h - 21 * mm, 16 * mm, 16 * mm,
                             preserveAspectRatio=True, anchor="c", mask="auto")
            text_x = 35 * mm
            logo_drawn = True
        except Exception:
            logo_drawn = False
    if not logo_drawn:
        canvas.setFillColor(SAGE)
        canvas.rect(15 * mm, h - 20 * mm, 9 * mm, 9 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 15)
    canvas.drawString(text_x, h - 15.5 * mm, brand["name"][:40])
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#B7C9BF"))
    canvas.drawString(text_x, h - 19.5 * mm, brand.get("tagline", "")[:70])
    if brand.get("contact"):
        canvas.drawString(text_x, h - 23 * mm, brand["contact"][:90])
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(w - 15 * mm, h - 15 * mm, meta.get("title", ""))
    canvas.drawRightString(w - 15 * mm, h - 19 * mm, meta.get("code", ""))
    # Footer
    canvas.setStrokeColor(colors.HexColor("#E2E5DF"))
    canvas.line(15 * mm, 15 * mm, w - 15 * mm, 15 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(15 * mm, 10 * mm, f"Generated {meta.get('generated', '')}  •  Rev {meta.get('revision', '')}")
    canvas.drawCentredString(w / 2, 10 * mm, meta.get("confidential", "Confidential"))
    canvas.drawRightString(w - 15 * mm, 10 * mm, f"Page {doc.page}")
    canvas.setFont("Helvetica", 6.5)
    canvas.drawCentredString(w / 2, 6.5 * mm, "Powered by CIVIO")
    canvas.restoreState()


def _kv_table(rows, styles, col=(45 * mm, 120 * mm)):
    data = [[Paragraph(f"<b>{k}</b>", styles["CivCell"]), Paragraph(str(v), styles["CivCell"])] for k, v in rows]
    t = Table(data, colWidths=col)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), BONE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E5DF")),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def _data_table(header, rows, styles, col_widths):
    data = [[Paragraph(h, styles["CivCellHead"]) for h in header]]
    for r in rows:
        data.append([Paragraph(str(c), styles["CivCell"]) for c in r])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), EMERALD),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BONE]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E5DF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _photo_row(photos, styles):
    """photos: list of (bytes, caption, date). Returns flowables with up to 3 per row."""
    flow = []
    cell_w = 55 * mm
    img_h = 42 * mm
    batch = []
    for b, cap, dt in photos:
        try:
            from PIL import Image as PILImage
            PILImage.open(io.BytesIO(b)).load()
            img = RLImage(io.BytesIO(b), width=cell_w - 4 * mm, height=img_h)
            img._restrictSize(cell_w - 4 * mm, img_h)
        except Exception:
            continue
        caption = Paragraph(f"<b>{cap or 'Site photo'}</b><br/>{_fmt_date(dt)}", styles["CivMuted"])
        batch.append([img, caption])
    rows = [batch[i:i + 3] for i in range(0, len(batch), 3)]
    for r in rows:
        cells = []
        for item in r:
            inner = Table([[item[0]], [item[1]]], colWidths=[cell_w])
            inner.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
            cells.append(inner)
        while len(cells) < 3:
            cells.append("")
        t = Table([cells], colWidths=[cell_w, cell_w, cell_w])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        flow.append(t)
        flow.append(Spacer(1, 4))
    return flow


def _fmt_time(rec):
    if not rec:
        return "—"
    try:
        return datetime.fromisoformat(rec["at"]).strftime("%d %b %H:%M UTC")
    except Exception:
        return "—"


def build_dpr(project, d, photos, meta, brand):
    buf = io.BytesIO()
    st = _styles()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=32 * mm, bottomMargin=20 * mm, leftMargin=15 * mm, rightMargin=15 * mm)
    s = [Paragraph("Daily Progress Report", st["CivH1"]),
         Paragraph(f"{project['name']}  ·  {project.get('code', '')}", st["CivH2"]),
         _kv_table([("Report date", _fmt_date(d["report_date"])), ("Weather", d.get("weather") or "—"),
                    ("Prepared by", d.get("created_by_name", "")), ("Status", d["status"].title()),
                    ("Reviewed by", d.get("reviewed_by_name") or "—"), ("Review comment", d.get("review_comment") or "—")], st)]

    def section(title, header, rows, widths, empty):
        s.append(Paragraph(title, st["CivH2"]))
        s.append(_data_table(header, rows or [[empty] + [""] * (len(header) - 1)], st, widths))

    section("Work Activities — Planned vs Actual", ["Activity", "Unit", "Planned qty", "Actual qty", "Planned %", "Actual %"],
            [[a["description"], a.get("unit", ""), a.get("planned_qty", 0), a.get("actual_qty", 0), f"{a.get('planned_pct', 0)}%", f"{a.get('actual_pct', 0)}%"] for a in d.get("activities", [])],
            [60 * mm, 18 * mm, 24 * mm, 24 * mm, 20 * mm, 20 * mm], "No activities recorded")
    if d.get("boq_entries"):
        section("BOQ Quantities — Daily & Cumulative", ["BOQ", "Description", "Today", "Cumulative (accepted)", "Approved", "Progress"],
                [[e["code"], f"{e['description']}{' (EXCESS — review)' if e.get('excess') else ''}" + (f" @ {e['location']}" if e.get("location") else ""),
                  f"{e['qty']} {e['unit']}", f"{e.get('cumulative_now', e.get('cumulative_before', 0))}", f"{e['approved_qty']}",
                  f"{round(min(e.get('cumulative_now', 0) / e['approved_qty'], 1) * 100, 1) if e['approved_qty'] else 0}%"] for e in d["boq_entries"]],
                [18 * mm, 62 * mm, 22 * mm, 28 * mm, 22 * mm, 18 * mm], "—")
    if d.get("labour"):
        section("Labour Attendance", ["Labour in-charge", "Masons", "Helpers", "Check-in", "Check-out"],
                [[l["labour_incharge"], l["masons"], l["helpers"], _fmt_time(l["check_in"]), _fmt_time(l.get("check_out"))] for l in d["labour"]],
                [55 * mm, 25 * mm, 25 * mm, 32 * mm, 32 * mm], "—")
    section("Manpower", ["Trade", "Count", "Hours"], [[m["name"], m.get("count", 0), m.get("hours", 0)] for m in d.get("manpower", [])],
            [90 * mm, 40 * mm, 40 * mm], "—")
    section("Equipment", ["Equipment", "Count", "Hours"], [[m["name"], m.get("count", 0), m.get("hours", 0)] for m in d.get("equipment", [])],
            [90 * mm, 40 * mm, 40 * mm], "—")
    section("Materials", ["Item", "Qty", "Status", "Note"], [[m["item"], f"{m.get('quantity', 0)} {m.get('unit', '')}", m.get("status", "").title(), m.get("note", "")] for m in d.get("materials", [])],
            [60 * mm, 30 * mm, 25 * mm, 55 * mm], "—")
    for title, key in [("Quality Observations", "quality_notes"), ("Safety Observations", "safety_notes"),
                       ("Delays & Hindrances", "delays"), ("Next-day Activities", "next_day_plan")]:
        s.append(Paragraph(title, st["CivH2"]))
        s.append(Paragraph((d.get(key) or "—").replace("\n", "<br/>"), st["CivBody"]))
    if photos:
        s.append(Paragraph("Site Photographs", st["CivH2"]))
        s.extend(_photo_row(photos, st))

    def on_page(canvas, dd):
        _header_footer(canvas, dd, meta, brand)
    doc.build(s, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


def build_inspection(project, stages, summary, docs, photos, meta, brand):
    buf = io.BytesIO()
    st = _styles()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=32 * mm, bottomMargin=20 * mm, leftMargin=15 * mm, rightMargin=15 * mm)
    label = {"pass": "PASS", "fail": "FAIL", "na": "N/A", "pending": "Pending"}
    s = [Paragraph("Inspection Report", st["CivH1"]),
         Paragraph(f"{project['name']}  ·  {project.get('code', '')}", st["CivH2"]),
         _kv_table([("Project address", project.get("address") or "—"), ("Report date", datetime.now().strftime("%d %b %Y")),
                    ("Prepared by", meta.get("prepared_by", "")),
                    ("Summary", f"{summary['total']} items · {summary['pass']} pass · {summary['fail']} fail · {summary['na']} N/A · {summary['pending']} pending")], st)]
    for g in stages:
        done = [i for i in g["items"] if i["status"] != "pending"]
        s.append(Paragraph(f"{g['stage']}  ({len(done)}/{len(g['items'])} inspected)", st["CivH2"]))
        if g.get("signoff"):
            so = g["signoff"]
            s.append(Paragraph(f"<b>Client sign-off:</b> Approved by {so['signed_by_name']} on {_fmt_date(so['signed_at'])}" + (f" — {so['remarks']}" if so.get("remarks") else ""), st["CivBody"]))
        s.append(_data_table(["Checklist item", "Status", "Remarks", "Responsible", "Photos"],
                             [[i["item"], label[i["status"]], i.get("remarks") or "—", i.get("responsible_name") or "—", len(i.get("photo_ids", []))] for i in g["items"]],
                             st, [62 * mm, 18 * mm, 52 * mm, 30 * mm, 18 * mm]))
    s.append(Paragraph("Drawings & Documents", st["CivH2"]))
    s.append(_data_table(["Title", "Type", "File", "Added by", "Date"],
                         [[d["title"], d["category"].title(), d["filename"], d.get("uploaded_by_name", ""), _fmt_date(d["created_at"])] for d in docs] or [["None on record", "", "", "", ""]],
                         st, [55 * mm, 22 * mm, 45 * mm, 32 * mm, 26 * mm]))
    if photos:
        s.append(Paragraph("Inspection Photographs", st["CivH2"]))
        s.extend(_photo_row(photos, st))

    def on_page(canvas, dd):
        _header_footer(canvas, dd, meta, brand)
    doc.build(s, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


def build_labour_cost(projects, meta, brand):
    buf = io.BytesIO()
    st = _styles()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=32 * mm, bottomMargin=20 * mm, leftMargin=15 * mm, rightMargin=15 * mm)
    s = [Paragraph("Labour Cost Report", st["CivH1"]),
         Paragraph(f"Month-to-date with last 7 days breakdown · {meta.get('code', '')}", st["CivMuted"])]
    tot = lambda k: sum(p["mtd"][k] for p in projects)  # noqa: E731
    s.append(Paragraph("Company Summary (month-to-date)", st["CivH2"]))
    s.append(_data_table(["Project", "Mason-days", "Helper-days", "Mason cost", "Helper cost", "Total"],
                         [[f"{p['project']['name']} ({p['project']['code']})", p["mtd"]["mason_days"], p["mtd"]["helper_days"],
                           _fmt_inr(p["mtd"]["mason_cost"]), _fmt_inr(p["mtd"]["helper_cost"]), _fmt_inr(p["mtd"]["total"])] for p in projects]
                         + [["<b>All projects</b>", tot("mason_days"), tot("helper_days"), _fmt_inr(tot("mason_cost")),
                             _fmt_inr(tot("helper_cost")), f"<b>{_fmt_inr(tot('total'))}</b>"]],
                         st, [60 * mm, 22 * mm, 22 * mm, 25 * mm, 25 * mm, 26 * mm]))
    for p in projects:
        r = p["rates"]
        s.append(Paragraph(f"{p['project']['name']} · {p['project']['code']}", st["CivH2"]))
        s.append(_kv_table([("Wage rates", f"Mason {_fmt_inr(r['mason_rate'])}/day · Helper {_fmt_inr(r['helper_rate'])}/day"),
                            ("Month-to-date", f"{p['mtd']['mason_days']} mason-days · {p['mtd']['helper_days']} helper-days · {_fmt_inr(p['mtd']['total'])}"),
                            ("Last 7 days", f"{p['week']['mason_days']} mason-days · {p['week']['helper_days']} helper-days · {_fmt_inr(p['week']['total'])}")], st))
        s.append(Spacer(1, 4))
        s.append(_data_table(["Date", "Masons", "Helpers", "Mason cost", "Helper cost", "Day total"],
                             [[_fmt_date(d["date"]), d["mason_days"], d["helper_days"], _fmt_inr(d["mason_cost"]), _fmt_inr(d["helper_cost"]), _fmt_inr(d["total"])]
                              for d in p["days"]], st, [34 * mm, 22 * mm, 22 * mm, 32 * mm, 32 * mm, 38 * mm]))
    if not projects:
        s.append(Paragraph("No active projects.", st["CivBody"]))

    def on_page(canvas, dd):
        _header_footer(canvas, dd, meta, brand)
    doc.build(s, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


def build_report(report_type, ctx):
    """ctx: dict with project, meta, activities, milestones, progress, defects, photos, cost."""
    buf = io.BytesIO()
    styles = _styles()
    meta = ctx["meta"]
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=32 * mm, bottomMargin=20 * mm, leftMargin=15 * mm, rightMargin=15 * mm,
    )
    story = []
    p = ctx["project"]
    title = meta["title"]
    story.append(Paragraph(title, styles["CivH1"]))
    period = ""
    if meta.get("period_start") or meta.get("period_end"):
        period = f"Reporting period: {_fmt_date(meta.get('period_start'))} — {_fmt_date(meta.get('period_end'))}"
    story.append(Paragraph(f"{p['name']}  ·  {p.get('code','')}", styles["CivH2"]))
    if period:
        story.append(Paragraph(period, styles["CivMuted"]))
    story.append(Spacer(1, 8))

    story.append(_kv_table([
        ("Project", p.get("name", "")),
        ("Project code", p.get("code", "")),
        ("Address", p.get("address", "—")),
        ("Type / Status", f"{p.get('type','')}  ·  {p.get('status','')}"),
        ("Start / Completion", f"{_fmt_date(p.get('start_date'))}  →  {_fmt_date(p.get('planned_completion_date'))}"),
        ("Overall progress", f"{p.get('progress_percent', 0)}% (weighted)"),
        ("Contract value", _fmt_inr(p.get("contract_value"))),
    ], styles))
    story.append(Spacer(1, 6))

    if report_type in ("progress", "completion"):
        story.append(Paragraph("Activity Progress", styles["CivH2"]))
        rows = [[a["name"], a.get("phase", ""), str(a.get("weight", 1)), f"{a.get('progress_percent',0)}%", a.get("status","").replace("_"," ")] for a in ctx["activities"]]
        if not rows:
            rows = [["No activities defined", "", "", "", ""]]
        story.append(_data_table(["Activity", "Phase", "Weight", "Progress", "Status"], rows, styles,
                                 [60 * mm, 30 * mm, 18 * mm, 22 * mm, 30 * mm]))
        story.append(Spacer(1, 6))

        if ctx.get("milestones"):
            story.append(Paragraph("Milestones", styles["CivH2"]))
            mrows = [[m["name"], _fmt_date(m.get("due_date")), m.get("status","")] for m in ctx["milestones"]]
            story.append(_data_table(["Milestone", "Due date", "Status"], mrows, styles, [90 * mm, 40 * mm, 30 * mm]))
            story.append(Spacer(1, 6))

    if report_type == "progress" and ctx.get("progress"):
        story.append(Paragraph("Recent Progress Updates", styles["CivH2"]))
        prows = [[u.get("activity_name","—"), f"{u.get('percent_complete',0)}%", u.get("status","").replace("_"," "), u.get("engineer_name","—"), _fmt_date(u.get("created_at"))] for u in ctx["progress"]]
        story.append(_data_table(["Activity", "Reported", "Status", "Engineer", "Date"], prows, styles,
                                 [52 * mm, 20 * mm, 32 * mm, 36 * mm, 24 * mm]))
        story.append(Spacer(1, 6))

    story.append(Paragraph("Outstanding Issues — Open Defects", styles["CivH2"]))
    drows = [[d.get("defect_code",""), d.get("severity","").title(), d.get("location",""), d.get("status","").replace("_"," "), _fmt_date(d.get("target_date"))] for d in ctx.get("defects", [])]
    if not drows:
        drows = [["—", "None", "No open defects", "", ""]]
    story.append(_data_table(["ID", "Severity", "Location", "Status", "Target"], drows, styles,
                             [20 * mm, 24 * mm, 56 * mm, 34 * mm, 30 * mm]))
    story.append(Spacer(1, 6))

    if report_type == "cost" or ctx.get("cost"):
        c = ctx.get("cost") or {}
        story.append(Paragraph("Cost Summary (INR)", styles["CivH2"]))
        story.append(_data_table(["Budget", "Committed", "Actual (paid)", "Forecast", "Variance"], [[
            _fmt_inr(c.get("budget")), _fmt_inr(c.get("committed")), _fmt_inr(c.get("actual")),
            _fmt_inr(c.get("forecast")), _fmt_inr(c.get("variance")),
        ]], styles, [34 * mm, 34 * mm, 34 * mm, 32 * mm, 32 * mm]))
        story.append(Paragraph("Figures include entered estimates and verified transactions; this is not a certified accounting statement.", styles["CivMuted"]))
        story.append(Spacer(1, 6))

    photos = ctx.get("photos", [])
    if photos:
        story.append(Paragraph("Dated Site Photographs", styles["CivH2"]))
        story.extend(_photo_row(photos, styles))

    if report_type == "completion":
        story.append(Spacer(1, 10))
        story.append(Paragraph("Recommendations & Sign-off", styles["CivH2"]))
        story.append(Paragraph(meta.get("recommendations") or "Project works are recorded as above. Final handover is subject to closure of all outstanding defects and client acceptance.", styles["CivBody"]))
        story.append(Spacer(1, 18))
        sign = Table([[Paragraph("<b>Project Manager</b><br/><br/>______________________", styles["CivBody"]),
                       Paragraph("<b>Client Acceptance</b><br/><br/>______________________", styles["CivBody"])]],
                     colWidths=[85 * mm, 85 * mm])
        story.append(sign)

    def on_page(canvas, d):
        _header_footer(canvas, d, meta, ctx.get("brand"))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buf.seek(0)
    return buf.read()
