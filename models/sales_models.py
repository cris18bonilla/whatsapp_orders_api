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

class RestaurantZone(Base):
    __tablename__ = "restaurant_zones"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    restaurant = relationship("Restaurant")
    tables = relationship("RestaurantTable", back_populates="zone")


class RestaurantTable(Base):
    __tablename__ = "restaurant_tables"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False, index=True)
    zone_id = Column(Integer, ForeignKey("restaurant_zones.id"), nullable=True, index=True)
    code = Column(String(40), nullable=False)
    display_name = Column(String(80), nullable=False)
    capacity = Column(Integer, nullable=False, default=4)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    restaurant = relationship("Restaurant")
    zone = relationship("RestaurantZone", back_populates="tables")

# =========================
# ORDEN PRINCIPAL
# =========================

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), index=True, nullable=False)

    # local / delivery / pickup / whatsapp
    channel = Column(String(30), nullable=False, index=True)

    status = Column(String(30), nullable=False, default="pending")

    customer_name = Column(String(120))
    customer_phone = Column(String(50))

    table_number = Column(String(20))

    service_mode = Column(String(20), nullable=False, default="quick", index=True)  # table | bar | quick | delivery | whatsapp
    table_id = Column(Integer, ForeignKey("restaurant_tables.id"), nullable=True, index=True)
    zone_id = Column(Integer, ForeignKey("restaurant_zones.id"), nullable=True, index=True)
    is_open = Column(Boolean, nullable=False, default=True, index=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    subtotal = Column(Numeric(10, 2), nullable=False, default=0)
    tax = Column(Numeric(10, 2), nullable=False, default=0)
    total = Column(Numeric(10, 2), nullable=False, default=0)

    payment_status = Column(String(30), nullable=False,  default="pending")

    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("OrderPayment", back_populates="order", cascade="all, delete-orphan")
    table = relationship("RestaurantTable")
    zone = relationship("RestaurantZone")

# =========================
# ITEMS DE LA ORDEN
# =========================

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)

    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False)

    product_id = Column(Integer, ForeignKey("products.id"), index=True, nullable=True)

    product_name_snapshot = Column(String(200), nullable=False)

    quantity = Column(Numeric(10, 2), nullable=False, default=1)

    unit_price = Column(Numeric(10, 2), nullable=False, default=0)

    total_price = Column(Numeric(10, 2), nullable=False, default=0)
    
    sent_to_kitchen = Column(Boolean, nullable=False, default=False, index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    kitchen_status = Column(String(20), nullable=False, default="draft", index=True)  # draft | sent | preparing | ready | delivered | voided
    voided = Column(Boolean, nullable=False, default=False, index=True)
    paid_quantity = Column(Numeric(12, 2), nullable=False, default=0)

    notes = Column(Text)

    order = relationship("Order", back_populates="items")


# =========================
# PAGOS
# =========================

class OrderPayment(Base):
    __tablename__ = "order_payments"

    id = Column(Integer, primary_key=True)

    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False)

    method = Column(String(50), nullable=False)  # cash / card / transfer / credit
    status = Column(String(30), nullable=False, default="approved")

    amount = Column(Numeric(10, 2), nullable=False)

    reference = Column(String(120))

    bank_name = Column(String(120))
    terminal_id = Column(String(120))
    authorization_code = Column(String(120))
    card_brand = Column(String(50))
    card_last4 = Column(String(10))

    cash_session_id = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    order = relationship("Order", back_populates="payments")
