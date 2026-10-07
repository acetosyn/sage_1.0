# SERVICE: SAGE Multi-Format Report Export Engine
# Converts one tenant-scoped reporting dataset into CSV, Excel or PDF so all formats share the exact same underlying rows.

import csv
import io
from datetime import datetime


def _cell(value): return "" if value is None else str(value)

def build_report_export(headers, rows, file_format, title, subtitle=""):
    file_format = str(file_format or "csv").strip().lower(); safe_rows = [[_cell(cell) for cell in row] for row in rows]; headers = [_cell(cell) for cell in headers]
    if file_format == "csv":
        text = io.StringIO(); writer = csv.writer(text); writer.writerow(headers); writer.writerows(safe_rows); payload = io.BytesIO(text.getvalue().encode("utf-8-sig")); payload.seek(0); return payload, "text/csv"
    if file_format == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
        workbook = Workbook(); sheet = workbook.active; sheet.title = "SAGE Report"; sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(1, len(headers))); sheet.cell(1, 1, title).font = Font(size=16, bold=True); sheet.cell(2, 1, subtitle or f"Generated {datetime.now().strftime('%d %b %Y %H:%M')}"); header_row = 4
        for col, heading in enumerate(headers, 1): cell = sheet.cell(header_row, col, heading); cell.font = Font(bold=True); cell.fill = PatternFill("solid", fgColor="E7F4EE"); cell.alignment = Alignment(vertical="top", wrap_text=True)
        for r_index, row in enumerate(safe_rows, header_row + 1):
            for c_index, value in enumerate(row, 1): sheet.cell(r_index, c_index, value).alignment = Alignment(vertical="top", wrap_text=True)
        sheet.freeze_panes = f"A{header_row + 1}"; sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(max(1,len(headers)))}{max(header_row, header_row + len(safe_rows))}"
        for c_index, heading in enumerate(headers, 1):
            sample = [len(str(heading))] + [len(str(row[c_index-1])) for row in safe_rows[:200] if c_index <= len(row)]; sheet.column_dimensions[get_column_letter(c_index)].width = min(42, max(12, max(sample, default=12) + 2))
        payload = io.BytesIO(); workbook.save(payload); payload.seek(0); return payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if file_format == "pdf":
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle, Paragraph
        payload = io.BytesIO(); page = landscape(A4) if len(headers) > 5 else A4; doc = SimpleDocTemplate(payload, pagesize=page, rightMargin=10*mm, leftMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm); styles = getSampleStyleSheet(); story = [Paragraph(title, styles["Title"]), Paragraph(subtitle or f"Generated {datetime.now().strftime('%d %b %Y %H:%M')}", styles["Normal"]), Spacer(1, 6*mm)]; data = [headers] + safe_rows
        table = Table(data, repeatRows=1, hAlign="LEFT"); table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E7F4EE")),("TEXTCOLOR",(0,0),(-1,0),colors.HexColor("#173B2D")),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7),("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#D9E1DD")),("VALIGN",(0,0),(-1,-1),"TOP"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F7FAF8")]),("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)])); story.append(table); doc.build(story); payload.seek(0); return payload, "application/pdf"
    raise ValueError("Unsupported export format.")
