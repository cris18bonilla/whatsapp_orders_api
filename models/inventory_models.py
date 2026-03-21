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
# PRODUCTOS (MENÚ)
# =========================

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), index=True)

    name = Column(String(200), nullable=False)

    category = Column(String(100))

    price = Column(Numeric(10, 2))

    description = Column(Text)

    image_url = Column(Text)

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    recipes = relationship("Recipe", back_populates="product")


# =========================
# INSUMOS
# =========================

class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True)

    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), index=True)

    name = Column(String(200), nullable=False)

    unit = Column(String(50))

    current_stock = Column(Numeric(10, 2), default=0)

    minimum_stock = Column(Numeric(10, 2), default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    movements = relationship("InventoryMovement", back_populates="item")


# =========================
# RECETAS
# =========================

class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True)

    product_id = Column(Integer, ForeignKey("products.id"), index=True)

    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id"))

    quantity_required = Column(Numeric(10, 2))

    product = relationship("Product", back_populates="recipes")


# =========================
# KARDEX
# =========================

class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id = Column(Integer, primary_key=True)

    item_id = Column(Integer, ForeignKey("inventory_items.id"), index=True)

    movement_type = Column(String(30))  
    # entrada / salida / ajuste / consumo

    quantity = Column(Numeric(10, 2))

    reference_type = Column(String(50))
    # order / purchase / manual

    reference_id = Column(Integer)

    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    item = relationship("InventoryItem", back_populates="movements")
