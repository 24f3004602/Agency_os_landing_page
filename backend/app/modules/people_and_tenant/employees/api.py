import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_employee, require_owner
from app.core.security import hash_password
from app.database import get_db
from app.modules.people_and_tenant.users.models import Employee, User, UserRole
from app.modules.people_and_tenant.employees.schemas import EmployeeCreate, EmployeeResponse, EmployeeUpdate

router = APIRouter(prefix="/employees", tags=["employees"])


# ── Helper: build EmployeeResponse from Employee + User rows ─────────────────

async def _build_response(emp: Employee, db: AsyncSession) -> EmployeeResponse:
    user_result = await db.execute(select(User).where(User.id == emp.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(500, "Employee user record missing")

    return EmployeeResponse(
        id=emp.id,
        user_id=emp.user_id,
        agency_id=emp.agency_id,
        designation=emp.designation,
        compensation_type=emp.compensation_type,
        compensation_rate=emp.compensation_rate,
        is_active=emp.is_active,
        created_at=emp.created_at,
        full_name=user.full_name,
        email=user.email,
        last_login=user.last_login,
    )


# ── Create employee ──────────────────────────────────────────────────────────

@router.post("", response_model=EmployeeResponse, status_code=201)
async def create_employee(
    body: EmployeeCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> EmployeeResponse:
    """
    Owner creates a new employee.
    This automatically creates their login account (User row)
    and their employee profile (Employee row).
    """
    # Check email not already taken platform-wide
    existing = await db.execute(
        select(User).where(User.email == body.email.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Email {body.email} is already registered")

    # Create User account
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=UserRole.EMPLOYEE,
        agency_id=current_user.agency_id,
        is_active=True,
    )
    db.add(user)
    await db.flush()  # need user.id for Employee FK

    # Create Employee profile
    employee = Employee(
        user_id=user.id,
        agency_id=current_user.agency_id,
        designation=body.designation,
        compensation_type=body.compensation_type,
        compensation_rate=body.compensation_rate,
        is_active=True,
    )
    db.add(employee)
    await db.commit()
    await db.refresh(employee)

    return await _build_response(employee, db)


# ── List employees ───────────────────────────────────────────────────────────

@router.get("", response_model=list[EmployeeResponse])
async def list_employees(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
    include_inactive: bool = False,
) -> list[EmployeeResponse]:
    query = select(Employee).where(
        Employee.agency_id == current_user.agency_id
    )
    if not include_inactive:
        query = query.where(Employee.is_active.is_(True))
    query = query.order_by(Employee.created_at.desc())

    result = await db.execute(query)
    employees = result.scalars().all()

    return [await _build_response(emp, db) for emp in employees]


# ── Get single employee ──────────────────────────────────────────────────────

@router.get("/me", response_model=EmployeeResponse)
async def get_my_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_employee)],
) -> EmployeeResponse:
    """Employee views their own profile."""
    result = await db.execute(
        select(Employee).where(Employee.user_id == current_user.id)
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(404, "Employee profile not found")

    return await _build_response(employee, db)


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> EmployeeResponse:
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.agency_id == current_user.agency_id,
        )
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(404, "Employee not found")

    return await _build_response(employee, db)


# ── Update employee ──────────────────────────────────────────────────────────

@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: uuid.UUID,
    body: EmployeeUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> EmployeeResponse:
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.agency_id == current_user.agency_id,
        )
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(404, "Employee not found")

    update_data = body.model_dump(exclude_unset=True)

    # full_name lives on User, not Employee — handle separately
    if "full_name" in update_data:
        user_result = await db.execute(
            select(User).where(User.id == employee.user_id)
        )
        user = user_result.scalar_one_or_none()
        if user:
            user.full_name = update_data.pop("full_name")

    # is_active on Employee also disables their User login
    if "is_active" in update_data:
        user_result = await db.execute(
            select(User).where(User.id == employee.user_id)
        )
        user = user_result.scalar_one_or_none()
        if user:
            user.is_active = update_data["is_active"]

    for field, value in update_data.items():
        setattr(employee, field, value)

    await db.commit()
    await db.refresh(employee)
    return await _build_response(employee, db)


# ── Deactivate employee ──────────────────────────────────────────────────────

@router.delete("/{employee_id}", status_code=204)
async def deactivate_employee(
    employee_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> None:
    """
    Soft delete — sets is_active=False on both Employee and User.
    Data is preserved. Employee cannot log in after this.
    """
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.agency_id == current_user.agency_id,
        )
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(404, "Employee not found")

    employee.is_active = False

    user_result = await db.execute(
        select(User).where(User.id == employee.user_id)
    )
    user = user_result.scalar_one_or_none()
    if user:
        user.is_active = False

    await db.commit()