"""In-memory export service for PDF and Excel reports.

Owner: Azaz (Student ID: 237). Module 3.
Complies with PROJECT_RULES.md:
"Never write to a file on the server's disk. Generate reports in memory and stream them."

Libraries:
- reportlab for PDF generation (in-memory BytesIO buffer)
- openpyxl for Excel spreadsheet generation (in-memory BytesIO buffer)
"""

from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


# ---------------------------------------------------------------------------
# PDF Generation Helpers
# ---------------------------------------------------------------------------


def _build_pdf_doc(title: str, subtitle: str, table_data: list[list[str]]) -> bytes:
    """Render a clean in-memory PDF document using ReportLab."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=6,
    )
    sub_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=14,
    )

    elements = [
        Paragraph(title, title_style),
        Paragraph(subtitle, sub_style),
        Spacer(1, 10),
    ]

    # Build Table
    t = Table(table_data, hAlign="LEFT")
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ])
    )
    elements.append(t)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Excel Generation Helpers
# ---------------------------------------------------------------------------


def _build_excel_doc(
    sheet_title: str, headers: list[str], rows: list[list[Any]]
) -> bytes:
    """Render a clean in-memory Excel workbook using openpyxl."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]

    header_font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    header_fill = PatternFill(
        start_color="1E293B", end_color="1E293B", fill_type="solid"
    )
    regular_font = Font(name="Arial", size=10)

    # Write headers
    ws.append(headers)
    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Write rows
    for row in rows:
        ws.append(row)
        for col_num in range(1, len(row) + 1):
            cell = ws.cell(row=ws.max_row, column=col_num)
            cell.font = regular_font

    # Adjust column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = col[0].column_letter
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Export Generators per Report Type
# ---------------------------------------------------------------------------


def export_daily_report(data: dict[str, Any], fmt: str) -> tuple[bytes, str, str]:
    """Export daily sales report as PDF or XLSX."""
    title = f"Daily Sales Report - {data['date']}"
    filename = f"daily_sales_{data['date']}.{fmt}"

    if fmt == "pdf":
        sub = f"Generated on {data['date']} · Hishabi Management System"
        table_data = [
            ["Metric", "Value"],
            ["Total Sales Amount", f"BDT {data['total_sales_amount']}"],
            ["Sales Count", str(data["sales_count"])],
            ["Total Profit", f"BDT {data['total_profit']}"],
            ["Cash Sales Amount", f"BDT {data['cash_sales_amount']}"],
            ["Credit Sales Amount", f"BDT {data['credit_sales_amount']}"],
        ]
        content = _build_pdf_doc(title, sub, table_data)
        media_type = "application/pdf"
    else:
        headers = ["Metric", "Value"]
        rows = [
            ["Report Date", str(data["date"])],
            ["Total Sales Amount (BDT)", float(data["total_sales_amount"])],
            ["Sales Count", data["sales_count"]],
            ["Total Profit (BDT)", float(data["total_profit"])],
            ["Cash Sales Amount (BDT)", float(data["cash_sales_amount"])],
            ["Credit Sales Amount (BDT)", float(data["credit_sales_amount"])],
        ]
        content = _build_excel_doc("Daily Sales", headers, rows)
        media_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    return content, filename, media_type


def export_monthly_report(data: dict[str, Any], fmt: str) -> tuple[bytes, str, str]:
    """Export monthly sales report as PDF or XLSX."""
    period = f"{data['year']}-{data['month']:02d}"
    title = f"Monthly Sales Report - {period}"
    filename = f"monthly_sales_{period}.{fmt}"

    if fmt == "pdf":
        sub = f"Aggregated for Month {period} · Total: BDT {data['total_sales_amount']} · Profit: BDT {data['total_profit']}"
        table_data = [["Date", "Sales Count", "Total Amount (BDT)", "Profit (BDT)"]]
        for d in data.get("days", []):
            table_data.append([
                str(d["date"]),
                str(d["sales_count"]),
                str(d["total_sales_amount"]),
                str(d["total_profit"]),
            ])
        content = _build_pdf_doc(title, sub, table_data)
        media_type = "application/pdf"
    else:
        headers = ["Date", "Sales Count", "Total Sales Amount (BDT)", "Profit (BDT)"]
        rows = []
        for d in data.get("days", []):
            rows.append([
                str(d["date"]),
                d["sales_count"],
                float(d["total_sales_amount"]),
                float(d["total_profit"]),
            ])
        content = _build_excel_doc(f"Month_{period}", headers, rows)
        media_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    return content, filename, media_type


def export_due_report(data: dict[str, Any], fmt: str) -> tuple[bytes, str, str]:
    """Export customer dues report as PDF or XLSX."""
    title = "Customer Dues Report"
    filename = f"customer_dues_report.{fmt}"

    if fmt == "pdf":
        sub = f"Total Dues: BDT {data['total_due_amount']} across {data['customer_count']} customers"
        table_data = [["Customer", "Phone", "Total Sales", "Total Paid", "Current Due"]]
        for c in data.get("customers", []):
            table_data.append([
                c["customer_name"],
                c.get("phone") or "-",
                f"BDT {c['total_sales']}",
                f"BDT {c['total_paid']}",
                f"BDT {c['current_due']}",
            ])
        content = _build_pdf_doc(title, sub, table_data)
        media_type = "application/pdf"
    else:
        headers = [
            "Customer ID",
            "Customer Name",
            "Phone",
            "Total Sales (BDT)",
            "Total Paid (BDT)",
            "Current Due (BDT)",
        ]
        rows = []
        for c in data.get("customers", []):
            rows.append([
                c["customer_id"],
                c["customer_name"],
                c.get("phone") or "",
                float(c["total_sales"]),
                float(c["total_paid"]),
                float(c["current_due"]),
            ])
        content = _build_excel_doc("Customer Dues", headers, rows)
        media_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    return content, filename, media_type


def export_profit_report(data: dict[str, Any], fmt: str) -> tuple[bytes, str, str]:
    """Export profit report as PDF or XLSX."""
    period = f"{data['start_date']}_to_{data['end_date']}"
    title = f"Profit Report ({data['start_date']} to {data['end_date']})"
    filename = f"profit_report_{period}.{fmt}"

    if fmt == "pdf":
        sub = "Gross Profit = Total Revenue - Cost of Goods Sold (COGS)"
        table_data = [
            ["Metric", "Amount (BDT)"],
            ["Total Revenue", f"BDT {data['total_revenue']}"],
            ["Cost of Goods Sold (COGS)", f"BDT {data['total_cogs']}"],
            ["Gross Profit", f"BDT {data['gross_profit']}"],
        ]
        content = _build_pdf_doc(title, sub, table_data)
        media_type = "application/pdf"
    else:
        headers = ["Metric", "Amount (BDT)"]
        rows = [
            ["Period Start", str(data["start_date"])],
            ["Period End", str(data["end_date"])],
            ["Total Revenue", float(data["total_revenue"])],
            ["Cost of Goods Sold (COGS)", float(data["total_cogs"])],
            ["Gross Profit", float(data["gross_profit"])],
        ]
        content = _build_excel_doc("Profit Report", headers, rows)
        media_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    return content, filename, media_type
