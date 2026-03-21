from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db import Base


class Restaurant(Base):
    __tablename__ = "restaurants"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(120), nullable=False)
    slug = Column(String(120), unique=True, index=True, nullable=False)

    brand_name = Column(String(120), nullable=True)
    tagline = Column(String(180), nullable=True)

    logo_url = Column(Text, nullable=True)

    ruc = Column(String(80), nullable=True)
    address = Column(Text, nullable=True)
    schedule = Column(Text, nullable=True)

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    whatsapp_phone_number_id = Column(String(80), unique=True, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    modules = relationship(
        "RestaurantModule",
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )
    settings = relationship(
        "RestaurantSetting",
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )
    users = relationship(
        "RestaurantUser",
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )
    sessions = relationship(
        "UserSession",
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )
    logs = relationship(
        "ActivityLog",
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )


class RestaurantModule(Base):
    __tablename__ = "restaurant_modules"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "module_code", name="uq_restaurant_module"),
    )

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(
        Integer,
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    module_code = Column(String(50), nullable=False, index=True)
    is_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    activated_at = Column(DateTime(timezone=True), nullable=True)

    restaurant = relationship("Restaurant", back_populates="modules")


class RestaurantSetting(Base):
    __tablename__ = "restaurant_settings"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "setting_key", name="uq_restaurant_setting"),
    )

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(
        Integer,
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    setting_key = Column(String(100), nullable=False, index=True)
    setting_value = Column(Text, nullable=True)

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    restaurant = relationship("Restaurant", back_populates="settings")
