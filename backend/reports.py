"""Civio-branded PDF report generation using reportlab."""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage,
)

FOREST = colors.HexColor("#132E23")
EMERALD = colors.HexColor("#1B4332")
SAGE = colors.HexColor("#40916C")
BONE = colors.HexColor("#F8F9F6")
CHARCOAL = colors.HexColor("#1F2421")
MUTED = colors.HexColor("#5C6460")


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


def _header_footer(canvas, doc, meta):
    canvas.saveState()
    w, h = A4
    # Header band
    canvas.setFillColor(FOREST)
    canvas.rect(0, h - 26 * mm, w, 26 * mm, fill=1, stroke=0)
    canvas.setFillColor(SAGE)
    canvas.rect(15 * mm, h - 20 * mm, 9 * mm, 9 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 15)
    canvas.drawString(27 * mm, h - 17 * mm, "CIVIO BUILD")
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#B7C9BF"))
    canvas.drawString(27 * mm, h - 21 * mm, "Project Management Consultancy")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(w - 15 * mm, h - 15 * mm, meta.get("title", ""))
    canvas.drawRightString(w - 15 * mm, h - 19 * mm, meta.get("code", ""))
    # Footer
    canvas.setStrokeColor(colors.HexColor("#E2E5DF"))
    canvas.line(15 * mm, 15 * mm, w - 15 * mm, 15 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(15 * mm, 10 * mm, f"Generated {meta.get('generated', '')}  •  Rev {meta.get('revision', '')}")
    canvas.drawCentredString(w / 2, 10 * mm, meta.get("confidential", "Confidential — Civio PMC"))
    canvas.drawRightString(w - 15 * mm, 10 * mm, f"Page {doc.page}")
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
        _header_footer(canvas, d, meta)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buf.seek(0)
    return buf.read()
