from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from db import Base

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    wa_id = Column(String(32), index=True, nullable=False)

    customer_name = Column(String(120), nullable=True)
    delivery_mode = Column(String(20), nullable=True)   # Delivery / Retiro
    address = Column(Text, nullable=True)
    district_group = Column(String(80), nullable=True)
    payment_method = Column(String(30), nullable=True)

    subtotal = Column(Integer, nullable=False, default=0)
    delivery_fee = Column(Integer, nullable=False, default=0)
    total = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)

    name = Column(String(200), nullable=False)
    config = Column(String(200), nullable=True)
    price = Column(Integer, nullable=False)
    qty = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="items")
