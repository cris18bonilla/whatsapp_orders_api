from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime,
    Numeric
)

from sqlalchemy.sql import func

from db import Base


# =========================
# MÉTRICAS DIARIAS
# =========================

class DailyMetric(Base):
    __tablename__ = "daily_metrics"

    id = Column(Integer, primary_key=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), index=True)

    date = Column(DateTime)

    total_sales = Column(Numeric(10,2))

    total_orders = Column(Integer)

    average_ticket = Column(Numeric(10,2))

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# =========================
# MÉTRICAS DE PRODUCTOS
# =========================

class ProductSalesMetric(Base):
    __tablename__ = "product_sales_metrics"

    id = Column(Integer, primary_key=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), index=True)

    product_id = Column(Integer)

    product_name = Column(String(200))

    quantity_sold = Column(Numeric(10,2))

    total_revenue = Column(Numeric(10,2))

    metric_date = Column(DateTime)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# =========================
# MÉTRICAS DE EMPLEADOS
# =========================

class UserSalesMetric(Base):
    __tablename__ = "user_sales_metrics"

    id = Column(Integer, primary_key=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), index=True)

    user_id = Column(Integer)

    user_name = Column(String(200))

    orders_handled = Column(Integer)

    total_sales = Column(Numeric(10,2))

    metric_date = Column(DateTime)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# =========================
# MÉTRICAS DE RIDERS
# =========================

class DriverMetric(Base):
    __tablename__ = "driver_metrics"

    id = Column(Integer, primary_key=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), index=True)

    driver_id = Column(Integer)

    driver_name = Column(String(200))

    deliveries_completed = Column(Integer)

    total_delivery_revenue = Column(Numeric(10,2))

    metric_date = Column(DateTime)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
