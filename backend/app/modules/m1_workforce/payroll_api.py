import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_employee, require_owner, get_current_user
from app.core.pdf import MEDIA_ROOT, generate_payslip_pdf
from app.database import get_db
from app.modules.people_and_tenant.agencies.models import Agency
from app.modules.m1_workforce.models_attendance import AttendanceSession
from app.modules.m1_workforce.models_payroll import Payslip, PayrollRun
from app.modules.people_and_tenant.users.models import Employee, User, UserRole
from app.modules.m1_workforce.schemas_payroll import (
    PayrollRunCreate,
    PayrollRunResponse,
    PayrollRunSummary,
    PayslipResponse,
)

router = APIRouter(prefix="/payroll", tags=["payroll"])


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_employee_for_user(user: User, db: AsyncSession) -> Employee:
    result = await db.execute(
        select(Employee).where(Employee.user_id == user.id)
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Employee profile not found")
    return emp


async def _build_payslip_response(
    slip: Payslip, db: AsyncSession
) -> PayslipResponse:
    """Enriches a Payslip row with employee name and designation."""
    emp_result = await db.execute(
        select(Employee).where(Employee.id == slip.employee_id)
    )
    emp = emp_result.scalar_one_or_none()

    employee_name = "Unknown"
    designation = None
    if emp:
        user_result = await db.execute(
            select(User).where(User.id == emp.user_id)
        )
        user = user_result.scalar_one_or_none()
        employee_name = user.full_name if user else "Unknown"
        designation = emp.designation

    return PayslipResponse(
        id=slip.id,
        employee_id=slip.employee_id,
        employee_name=employee_name,
        designation=designation,
        period_month=slip.period_month,
        period_year=slip.period_year,
        days_present=slip.days_present,
        hours_worked=slip.hours_worked,
        gross_pay=slip.gross_pay,
        deductions=slip.deductions,
        allowances=slip.allowances,
        net_pay=slip.net_pay,
        has_pdf=slip.pdf_path is not None,
        created_at=slip.created_at,
    )


async def _calculate_payslip(
    employee: Employee,
    period_month: int,
    period_year: int,
    db: AsyncSession,
) -> dict:
    """
    Aggregates attendance for the period and calculates pay.
    Returns a dict ready to create a Payslip row.
    """
    # Fetch completed sessions for this employee in the period
    result = await db.execute(
        select(AttendanceSession).where(
            AttendanceSession.employee_id == employee.id,
            AttendanceSession.status == "complete",
            extract("month", AttendanceSession.clock_in_time) == period_month,
            extract("year", AttendanceSession.clock_in_time) == period_year,
        )
    )
    sessions = result.scalars().all()

    # Aggregate
    total_hours = sum(
        (s.hours_worked or Decimal("0")) for s in sessions
    )
    # Days present = unique calendar dates clocked in
    unique_dates = {s.clock_in_time.date() for s in sessions}
    days_present = len(unique_dates)

    # Calculate gross pay
    if employee.compensation_type == "fixed":
        gross_pay = employee.compensation_rate
    else:
        # Hourly
        gross_pay = total_hours * employee.compensation_rate

    # Deductions and allowances — 0 for now
    # Will be configurable per-employee in a future phase
    deductions = Decimal("0")
    allowances = Decimal("0")
    net_pay = gross_pay - deductions + allowances

    return {
        "days_present": days_present,
        "hours_worked": total_hours,
        "gross_pay": gross_pay.quantize(Decimal("0.01")),
        "deductions": deductions,
        "allowances": allowances,
        "net_pay": net_pay.quantize(Decimal("0.01")),
    }


# ── Owner: Trigger payroll run ───────────────────────────────────────────────

@router.post("/runs", response_model=PayrollRunResponse, status_code=201)
async def create_payroll_run(
    body: PayrollRunCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> PayrollRunResponse:
    """
    Owner triggers payroll calculation for a given month.
    System fetches all active employees, aggregates their attendance,
    calculates pay, and creates a draft PayrollRun with individual Payslips.
    Owner then reviews and approves.
    """
    # Prevent duplicate runs for same period
    existing = await db.execute(
        select(PayrollRun).where(
            PayrollRun.agency_id == current_user.agency_id,
            PayrollRun.period_month == body.period_month,
            PayrollRun.period_year == body.period_year,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            409,
            f"Payroll run for {body.period_month}/{body.period_year} already exists",
        )

    # Fetch all active employees
    emp_result = await db.execute(
        select(Employee).where(
            Employee.agency_id == current_user.agency_id,
            Employee.is_active.is_(True),
        )
    )
    employees = emp_result.scalars().all()

    if not employees:
        raise HTTPException(400, "No active employees found in your agency")

    # Create the run
    run = PayrollRun(
        agency_id=current_user.agency_id,
        period_month=body.period_month,
        period_year=body.period_year,
        status="draft",
        notes=body.notes,
    )
    db.add(run)
    await db.flush()  # need run.id

    # Create payslip for each employee
    total_gross = Decimal("0")
    total_net = Decimal("0")

    for employee in employees:
        calc = await _calculate_payslip(
            employee, body.period_month, body.period_year, db
        )
        slip = Payslip(
            payroll_run_id=run.id,
            agency_id=current_user.agency_id,
            employee_id=employee.id,
            period_month=body.period_month,
            period_year=body.period_year,
            **calc,
        )
        db.add(slip)
        total_gross += calc["gross_pay"]
        total_net += calc["net_pay"]

    run.total_gross = total_gross.quantize(Decimal("0.01"))
    run.total_net = total_net.quantize(Decimal("0.01"))
    run.total_employees = len(employees)

    await db.commit()
    await db.refresh(run, ["payslips"])

    payslip_responses = [
        await _build_payslip_response(s, db) for s in run.payslips
    ]

    return PayrollRunResponse(
        id=run.id,
        agency_id=run.agency_id,
        period_month=run.period_month,
        period_year=run.period_year,
        status=run.status,
        total_gross=run.total_gross,
        total_net=run.total_net,
        total_employees=run.total_employees,
        notes=run.notes,
        approved_at=run.approved_at,
        created_at=run.created_at,
        payslips=payslip_responses,
    )


# ── Owner: List all runs ─────────────────────────────────────────────────────

@router.get("/runs", response_model=list[PayrollRunSummary])
async def list_payroll_runs(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> list[PayrollRunSummary]:
    result = await db.execute(
        select(PayrollRun)
        .where(PayrollRun.agency_id == current_user.agency_id)
        .order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc())
    )
    runs = result.scalars().all()
    return [
        PayrollRunSummary(
            id=r.id,
            period_month=r.period_month,
            period_year=r.period_year,
            status=r.status,
            total_net=r.total_net,
            total_employees=r.total_employees,
            created_at=r.created_at,
        )
        for r in runs
    ]


# ── Owner: Get single run with payslips ──────────────────────────────────────

@router.get("/runs/{run_id}", response_model=PayrollRunResponse)
async def get_payroll_run(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> PayrollRunResponse:
    result = await db.execute(
        select(PayrollRun).where(
            PayrollRun.id == run_id,
            PayrollRun.agency_id == current_user.agency_id,
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Payroll run not found")

    await db.refresh(run, ["payslips"])
    payslip_responses = [
        await _build_payslip_response(s, db) for s in run.payslips
    ]

    return PayrollRunResponse(
        id=run.id,
        agency_id=run.agency_id,
        period_month=run.period_month,
        period_year=run.period_year,
        status=run.status,
        total_gross=run.total_gross,
        total_net=run.total_net,
        total_employees=run.total_employees,
        notes=run.notes,
        approved_at=run.approved_at,
        created_at=run.created_at,
        payslips=payslip_responses,
    )


# ── Owner: Approve run → generate all PDFs ───────────────────────────────────

@router.post("/runs/{run_id}/approve", response_model=PayrollRunResponse)
async def approve_payroll_run(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> PayrollRunResponse:
    """
    Locks the payroll run and generates a PDF payslip for every employee.
    Once approved, the run cannot be modified.
    """
    result = await db.execute(
        select(PayrollRun).where(
            PayrollRun.id == run_id,
            PayrollRun.agency_id == current_user.agency_id,
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Payroll run not found")

    if run.status == "approved":
        raise HTTPException(409, "Payroll run is already approved")

    # Fetch agency name for PDF header
    agency_result = await db.execute(
        select(Agency).where(Agency.id == current_user.agency_id)
    )
    agency = agency_result.scalar_one_or_none()
    agency_name = agency.name if agency else "Agency"

    # Fetch all payslips for this run
    slips_result = await db.execute(
        select(Payslip).where(Payslip.payroll_run_id == run.id)
    )
    payslips = slips_result.scalars().all()

    # Generate PDF for each payslip
    for slip in payslips:
        emp_result = await db.execute(
            select(Employee).where(Employee.id == slip.employee_id)
        )
        employee = emp_result.scalar_one_or_none()
        if not employee:
            continue

        user_result = await db.execute(
            select(User).where(User.id == employee.user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            continue

        pdf_path = generate_payslip_pdf(
            payslip_id=str(slip.id),
            agency_name=agency_name,
            employee_name=user.full_name,
            employee_email=user.email,
            designation=employee.designation,
            employee_id_short=str(employee.id)[:8].upper(),
            period_month=slip.period_month,
            period_year=slip.period_year,
            compensation_type=employee.compensation_type,
            compensation_rate=employee.compensation_rate,
            days_present=slip.days_present,
            hours_worked=slip.hours_worked,
            gross_pay=slip.gross_pay,
            deductions=slip.deductions,
            allowances=slip.allowances,
            net_pay=slip.net_pay,
        )
        slip.pdf_path = pdf_path

    # Lock the run
    run.status = "approved"
    run.approved_by = current_user.id
    run.approved_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(run, ["payslips"])

    payslip_responses = [
        await _build_payslip_response(s, db) for s in run.payslips
    ]

    return PayrollRunResponse(
        id=run.id,
        agency_id=run.agency_id,
        period_month=run.period_month,
        period_year=run.period_year,
        status=run.status,
        total_gross=run.total_gross,
        total_net=run.total_net,
        total_employees=run.total_employees,
        notes=run.notes,
        approved_at=run.approved_at,
        created_at=run.created_at,
        payslips=payslip_responses,
    )


# ── Employee: their own payslips ─────────────────────────────────────────────

@router.get("/payslips/my", response_model=list[PayslipResponse])
async def my_payslips(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_employee)],
) -> list[PayslipResponse]:
    employee = await _get_employee_for_user(current_user, db)

    result = await db.execute(
        select(Payslip)
        .join(PayrollRun, Payslip.payroll_run_id == PayrollRun.id)
        .where(
            Payslip.employee_id == employee.id,
            PayrollRun.status == "approved",  # only see approved payslips
        )
        .order_by(Payslip.period_year.desc(), Payslip.period_month.desc())
    )
    payslips = result.scalars().all()

    return [await _build_payslip_response(s, db) for s in payslips]


# ── Both: Download PDF payslip ───────────────────────────────────────────────

@router.get("/payslips/{payslip_id}/pdf")
async def download_payslip_pdf(
    payslip_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Download the PDF for a specific payslip.
    Employees can only download their own. Owner can download any.
    """
    result = await db.execute(
        select(Payslip).where(Payslip.id == payslip_id)
    )
    slip = result.scalar_one_or_none()
    if not slip:
        raise HTTPException(404, "Payslip not found")

    # Ownership check for employees
    if current_user.role == UserRole.EMPLOYEE:
        employee = await _get_employee_for_user(current_user, db)
        if slip.employee_id != employee.id:
            raise HTTPException(403, "You can only download your own payslips")

    # Agency check for owners
    if current_user.role == UserRole.OWNER:
        if slip.agency_id != current_user.agency_id:
            raise HTTPException(403, "Payslip does not belong to your agency")

    if not slip.pdf_path:
        raise HTTPException(404, "PDF not yet generated — run must be approved first")

    abs_path = MEDIA_ROOT / slip.pdf_path
    if not abs_path.exists():
        raise HTTPException(404, "PDF file not found on server")

    return FileResponse(
        path=str(abs_path),
        media_type="application/pdf",
        filename=f"payslip_{slip.period_month:02d}_{slip.period_year}.pdf",
    )