"""
PDF generation using WeasyPrint + Jinja2.
Called after owner approves a payroll run.
Saves PDFs to: backend/media/payslips/YEAR/MONTH/payslip_id.pdf
"""
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

# Media root — all generated files live here
MEDIA_ROOT = Path(__file__).parent.parent.parent / "media"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _get_template_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


def generate_payslip_pdf(
    payslip_id: str,
    agency_name: str,
    employee_name: str,
    employee_email: str,
    designation: str,
    employee_id_short: str,
    period_month: int,
    period_year: int,
    compensation_type: str,
    compensation_rate: Decimal,
    days_present: int,
    hours_worked: Decimal,
    gross_pay: Decimal,
    deductions: Decimal,
    allowances: Decimal,
    net_pay: Decimal,
) -> str:
    """
    Renders the payslip HTML template and converts to PDF via WeasyPrint.

    Returns the relative file path (stored in Payslip.pdf_path).
    e.g. "payslips/2026/04/abc12345.pdf"
    """
    import calendar

    month_name = calendar.month_name[period_month]
    period_label = f"{month_name} {period_year}"
    generated_on = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    payslip_id_short = payslip_id[:8].upper()

    # Render HTML
    env = _get_template_env()
    template = env.get_template("payslip.html")
    html_content = template.render(
        agency_name=agency_name,
        employee_name=employee_name,
        employee_email=employee_email,
        designation=designation or "—",
        employee_id_short=employee_id_short,
        period_label=period_label,
        compensation_type=compensation_type,
        compensation_rate=f"{compensation_rate:,.2f}",
        days_present=days_present,
        hours_worked=f"{hours_worked:.2f}",
        gross_pay=float(gross_pay),
        deductions=float(deductions),
        allowances=float(allowances),
        net_pay=float(net_pay),
        payslip_id_short=payslip_id_short,
        generated_on=generated_on,
    )

    # Build output path
    relative_path = f"payslips/{period_year}/{period_month:02d}/{payslip_id_short}.pdf"
    abs_path = MEDIA_ROOT / relative_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate PDF
    HTML(string=html_content).write_pdf(str(abs_path))

    return relative_path

def generate_invoice_pdf(
    invoice_id: str,
    invoice_number: str,
    agency_name: str,
    client_company: str,
    client_contact: str,
    client_email: str,
    status: str,
    line_items: list[dict],
    subtotal: Decimal,
    tax_percent: Decimal,
    tax_amount: Decimal,
    total_amount: Decimal,
    due_date: str | None,
    notes: str | None,
) -> str:
    """
    Generates a PDF invoice using WeasyPrint.
    Returns relative path e.g. "invoices/INV-001.pdf"
    """
    from datetime import datetime, timezone

    generated_on = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    invoice_date = datetime.now(timezone.utc).strftime("%d %b %Y")

    env = _get_template_env()
    template = env.get_template("invoice.html")
    html_content = template.render(
        agency_name=agency_name,
        invoice_number=invoice_number,
        client_company=client_company,
        client_contact=client_contact,
        client_email=client_email,
        status=status,
        invoice_date=invoice_date,
        due_date=due_date,
        line_items=line_items,
        subtotal=float(subtotal),
        tax_percent=float(tax_percent),
        tax_amount=float(tax_amount),
        total_amount=float(total_amount),
        notes=notes,
        generated_on=generated_on,
    )

    relative_path = f"invoices/{invoice_number}.pdf"
    abs_path = MEDIA_ROOT / relative_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)

    HTML(string=html_content).write_pdf(str(abs_path))
    return relative_path