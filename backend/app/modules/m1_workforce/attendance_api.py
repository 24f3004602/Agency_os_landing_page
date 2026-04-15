import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_, func, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, require_employee, require_owner
from app.core.geofence import is_within_zone
from app.database import get_db
from app.modules.m1_workforce.models_attendance import AttendanceSession, GeofenceZone
from app.modules.people_and_tenant.users.models import Employee, User, UserRole
from app.modules.m1_workforce.schemas_attendance import (
    AttendanceSessionResponse,
    ClockInRequest,
    ClockInResponse,
    ClockOutResponse,
    TodayStatusResponse,
    EmployeeAttendanceSummary,
)

router = APIRouter(prefix="/attendance", tags=["attendance"])


#  Helpers

async def _get_employee(user: User, db: AsyncSession) -> Employee:
    """Resolve the Employee profile for the current user."""
    result = await db.execute(
        select(Employee).where(Employee.user_id == user.id)
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return employee


async def _get_open_session(employee_id: uuid.UUID, db: AsyncSession) -> AttendanceSession | None:
    """Return the currently open session for an employee, or None."""
    result = await db.execute(
        select(AttendanceSession).where(
            AttendanceSession.employee_id == employee_id,
            AttendanceSession.status == "open",
        )
    )
    return result.scalar_one_or_none()


def _calculate_hours(clock_in: datetime, clock_out: datetime) -> Decimal:
    """Returns hours worked rounded to 2 decimal places."""
    delta = clock_out - clock_in
    hours = delta.total_seconds() / 3600
    return Decimal(str(round(hours, 2)))


# ─── Clock In ──────────────────────────────────────────────────────────────────

@router.post("/clock-in", response_model=ClockInResponse)
async def clock_in(
    body: ClockInRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_employee)],
) -> ClockInResponse:
    """
    Employee clocks in. GPS coordinates are checked against all active
    geofence zones for the agency. First matching zone is recorded.
    """
    employee = await _get_employee(current_user, db)

    # Guard — only one open session at a time
    open_session = await _get_open_session(employee.id, db)
    if open_session:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already clocked in. Clock out before starting a new session.",
        )

    # Fetch all active zones for this agency
    result = await db.execute(
        select(GeofenceZone).where(
            GeofenceZone.agency_id == employee.agency_id,
            GeofenceZone.is_active.is_(True),
        )
    )
    zones = result.scalars().all()

    # Check each zone — first match wins
    matched_zone: GeofenceZone | None = None
    matched_distance: float | None = None

    for zone in zones:
        inside, distance = is_within_zone(
            employee_lat=body.latitude,
            employee_lon=body.longitude,
            zone_lat=zone.latitude,
            zone_lon=zone.longitude,
            radius_metres=zone.radius_metres,
        )
        if inside:
            matched_zone = zone
            matched_distance = distance
            break

    if not matched_zone:
        # Find the nearest zone for a helpful error message
        if zones:
            distances = [
                is_within_zone(body.latitude, body.longitude, z.latitude, z.longitude, z.radius_metres)
                for z in zones
            ]
            nearest_dist = min(d for _, d in distances)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"You are not within any approved work zone. "
                    f"Nearest zone is {nearest_dist:.0f}m away. "
                    f"Contact your manager if this is incorrect."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No geofence zones configured for your agency. Contact your manager.",
        )

    # Create session
    now = datetime.now(timezone.utc)
    session = AttendanceSession(
        agency_id=employee.agency_id,
        employee_id=employee.id,
        zone_id=matched_zone.id,
        clock_in_latitude=body.latitude,
        clock_in_longitude=body.longitude,
        clock_in_time=now,
        status="open",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return ClockInResponse(
        session_id=session.id,
        status="clocked_in",
        zone_name=matched_zone.name,
        clock_in_time=session.clock_in_time,
        distance_to_zone_metres=matched_distance,
        message=f"Clocked in at {matched_zone.name}. Have a great day!",
    )


# ─── Clock Out ─────────────────────────────────────────────────────────────────

@router.post("/clock-out", response_model=ClockOutResponse)
async def clock_out(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_employee)],
) -> ClockOutResponse:
    """Employee clocks out. Calculates hours worked and closes the session."""
    employee = await _get_employee(current_user, db)

    open_session = await _get_open_session(employee.id, db)
    if not open_session:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are not currently clocked in.",
        )

    now = datetime.now(timezone.utc)
    hours = _calculate_hours(open_session.clock_in_time, now)

    open_session.clock_out_time = now
    open_session.hours_worked = hours
    open_session.status = "complete"

    await db.commit()
    await db.refresh(open_session)

    return ClockOutResponse(
        session_id=open_session.id,
        status="clocked_out",
        clock_in_time=open_session.clock_in_time,
        clock_out_time=now,
        hours_worked=hours,
        message=f"Clocked out. You worked {hours} hours today.",
    )


# ─── Today's Status ────────────────────────────────────────────────────────────

@router.get("/today", response_model=TodayStatusResponse)
async def today_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_employee)],
) -> TodayStatusResponse:
    """Returns the employee's current clock-in status and today's session."""
    employee = await _get_employee(current_user, db)
    open_session = await _get_open_session(employee.id, db)

    if open_session:
        # Load zone name
        zone_name = None
        if open_session.zone_id:
            zone_result = await db.execute(
                select(GeofenceZone).where(GeofenceZone.id == open_session.zone_id)
            )
            zone = zone_result.scalar_one_or_none()
            zone_name = zone.name if zone else None

        session_data = AttendanceSessionResponse(
            id=open_session.id,
            employee_id=open_session.employee_id,
            zone_id=open_session.zone_id,
            zone_name=zone_name,
            clock_in_latitude=open_session.clock_in_latitude,
            clock_in_longitude=open_session.clock_in_longitude,
            clock_in_time=open_session.clock_in_time,
            clock_out_time=None,
            hours_worked=None,
            status=open_session.status,
            notes=open_session.notes,
            created_at=open_session.created_at,
        )
        return TodayStatusResponse(
            is_clocked_in=True,
            session=session_data,
            message="You are currently clocked in.",
        )

    return TodayStatusResponse(
        is_clocked_in=False,
        session=None,
        message="You are not clocked in.",
    )


# ─── My Session History ────────────────────────────────────────────────────────

@router.get("/my-sessions", response_model=list[AttendanceSessionResponse])
async def my_sessions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_employee)],
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2020),
) -> list[AttendanceSessionResponse]:
    """
    Returns the employee's own attendance history.
    Optionally filtered by month and year.
    Defaults to current month if no filter given.
    """
    employee = await _get_employee(current_user, db)

    now = datetime.now(timezone.utc)
    filter_month = month or now.month
    filter_year = year or now.year

    query = (
        select(AttendanceSession)
        .where(
            AttendanceSession.employee_id == employee.id,
            extract("month", AttendanceSession.clock_in_time) == filter_month,
            extract("year", AttendanceSession.clock_in_time) == filter_year,
        )
        .order_by(AttendanceSession.clock_in_time.desc())
    )
    result = await db.execute(query)
    sessions = result.scalars().all()

    # Build response with zone names
    responses = []
    for s in sessions:
        zone_name = None
        if s.zone_id:
            zone_res = await db.execute(
                select(GeofenceZone).where(GeofenceZone.id == s.zone_id)
            )
            zone = zone_res.scalar_one_or_none()
            zone_name = zone.name if zone else None

        responses.append(AttendanceSessionResponse(
            id=s.id,
            employee_id=s.employee_id,
            zone_id=s.zone_id,
            zone_name=zone_name,
            clock_in_latitude=s.clock_in_latitude,
            clock_in_longitude=s.clock_in_longitude,
            clock_in_time=s.clock_in_time,
            clock_out_time=s.clock_out_time,
            hours_worked=s.hours_worked,
            status=s.status,
            notes=s.notes,
            created_at=s.created_at,
        ))

    return responses


# ─── Owner: Team Attendance ────────────────────────────────────────────────────

@router.get("/team", response_model=list[EmployeeAttendanceSummary])
async def team_attendance(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
    date_filter: date | None = Query(None, description="Filter by specific date (YYYY-MM-DD)"),
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2020),
    employee_id: uuid.UUID | None = Query(None),
) -> list[EmployeeAttendanceSummary]:
    """
    Owner view: all employees' attendance.
    Defaults to current month. Can filter by date, month/year, or employee.
    """
    now = datetime.now(timezone.utc)
    filter_month = month or now.month
    filter_year = year or now.year

    # Get all employees in this agency
    emp_query = select(Employee).where(
        Employee.agency_id == current_user.agency_id,
        Employee.is_active.is_(True),
    )
    if employee_id:
        emp_query = emp_query.where(Employee.id == employee_id)

    emp_result = await db.execute(emp_query)
    employees = emp_result.scalars().all()

    summaries = []
    for emp in employees:
        # Fetch user for name
        user_result = await db.execute(select(User).where(User.id == emp.user_id))
        user = user_result.scalar_one_or_none()
        employee_name = user.full_name if user else "Unknown"

        # Build session query
        sess_query = select(AttendanceSession).where(
            AttendanceSession.employee_id == emp.id,
        )
        if date_filter:
            sess_query = sess_query.where(
                func.date(AttendanceSession.clock_in_time) == date_filter
            )
        else:
            sess_query = sess_query.where(
                extract("month", AttendanceSession.clock_in_time) == filter_month,
                extract("year", AttendanceSession.clock_in_time) == filter_year,
            )
        sess_query = sess_query.order_by(AttendanceSession.clock_in_time.desc())

        sess_result = await db.execute(sess_query)
        sessions = sess_result.scalars().all()

        # Total hours this month
        total_hours = sum(
            (s.hours_worked or Decimal("0")) for s in sessions
        )

        # Build session responses with zone names
        session_responses = []
        for s in sessions:
            zone_name = None
            if s.zone_id:
                zr = await db.execute(select(GeofenceZone).where(GeofenceZone.id == s.zone_id))
                z = zr.scalar_one_or_none()
                zone_name = z.name if z else None

            session_responses.append(AttendanceSessionResponse(
                id=s.id,
                employee_id=s.employee_id,
                zone_id=s.zone_id,
                zone_name=zone_name,
                clock_in_latitude=s.clock_in_latitude,
                clock_in_longitude=s.clock_in_longitude,
                clock_in_time=s.clock_in_time,
                clock_out_time=s.clock_out_time,
                hours_worked=s.hours_worked,
                status=s.status,
                notes=s.notes,
                created_at=s.created_at,
            ))

        summaries.append(EmployeeAttendanceSummary(
            employee_id=emp.id,
            employee_name=employee_name,
            sessions=session_responses,
            total_hours_this_month=total_hours,
        ))

    return summaries
