from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from db import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, index=True, nullable=False, default=1, server_default="1")
    ticket = Column(String(32), unique=True, nullable=False)
    wa_id = Column(String(32), index=True, nullable=False)

    customer_name = Column(String(120), nullable=True)
    delivery_mode = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)
    district_group = Column(String(80), nullable=True)
    payment_method = Column(String(30), nullable=True)

    # pendiente / preparando / en_camino / listo_retirar / entregado / cancelado
    status = Column(String(30), nullable=False, default="pendiente", server_default="pendiente")

    # ocultar del Kitchen Display sin borrar de la DB
    hidden_from_kds = Column(Boolean, nullable=False, default=False, server_default="false")

    subtotal = Column(Integer, nullable=False, default=0)
    delivery_fee = Column(Integer, nullable=False, default=0)
    total = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    items = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)

    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(String(200), nullable=False)
    config = Column(String(200), nullable=True, default="")
    price = Column(Integer, nullable=False)
    qty = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="items")
