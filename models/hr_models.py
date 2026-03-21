from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime,
    Numeric,
    Boolean,
    Text
)

from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db import Base


# =========================
# EMPLEADOS
# =========================

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), index=True)

    name = Column(String(200), nullable=False)

    role = Column(String(100))
    # mesero / cajero / cocinero / rider / gerente

    phone = Column(String(50))

    salary = Column(Numeric(10,2))

    hire_date = Column(DateTime)

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    attendances = relationship("EmployeeAttendance", back_populates="employee")
    advances = relationship("SalaryAdvance", back_populates="employee")


# =========================
# ASISTENCIA
# =========================

class EmployeeAttendance(Base):
    __tablename__ = "employee_attendance"

    id = Column(Integer, primary_key=True)

    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)

    check_in = Column(DateTime)

    check_out = Column(DateTime)

    notes = Column(Text)

    employee = relationship("Employee", back_populates="attendances")


# =========================
# VACACIONES
# =========================

class EmployeeVacation(Base):
    __tablename__ = "employee_vacations"

    id = Column(Integer, primary_key=True)

    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)

    start_date = Column(DateTime)

    end_date = Column(DateTime)

    days_taken = Column(Integer)

    notes = Column(Text)


# =========================
# ADELANTOS SALARIALES
# =========================

class SalaryAdvance(Base):
    __tablename__ = "salary_advances"

    id = Column(Integer, primary_key=True)

    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)

    amount = Column(Numeric(10,2))

    reason = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employee = relationship("Employee", back_populates="advances")


# =========================
# LIQUIDACIONES
# =========================

class EmployeeSettlement(Base):
    __tablename__ = "employee_settlements"

    id = Column(Integer, primary_key=True)

    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)

    termination_date = Column(DateTime)

    reason = Column(String(200))

    amount_paid = Column(Numeric(10,2))

    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
