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
# SESIÓN DE CAJA
# =========================

class CashSession(Base):
    __tablename__ = "cash_sessions"

    id = Column(Integer, primary_key=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), index=True)

    opened_by_user_id = Column(Integer)

    opening_amount = Column(Numeric(10, 2))

    closing_amount = Column(Numeric(10, 2))

    expected_amount = Column(Numeric(10, 2))

    difference = Column(Numeric(10, 2))

    is_open = Column(Boolean, default=True)

    opened_at = Column(DateTime(timezone=True), server_default=func.now())

    closed_at = Column(DateTime(timezone=True))

    movements = relationship("CashMovement", back_populates="session")


# =========================
# MOVIMIENTOS DE CAJA
# =========================

class CashMovement(Base):
    __tablename__ = "cash_movements"

    id = Column(Integer, primary_key=True)

    session_id = Column(Integer, ForeignKey("cash_sessions.id"), index=True)

    movement_type = Column(String(30))  
    # sale / ingreso / retiro / ajuste

    amount = Column(Numeric(10, 2))

    description = Column(Text)

    created_by_user_id = Column(Integer)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("CashSession", back_populates="movements")
