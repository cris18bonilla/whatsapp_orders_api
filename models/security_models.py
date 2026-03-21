from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db import Base


class RestaurantUser(Base):
    __tablename__ = "restaurant_users"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(
        Integer,
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(String(120), nullable=False)
    pin_code = Column(String(50), nullable=False)

    role_code = Column(String(50), nullable=False, default="staff", server_default="staff")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    session_timeout_seconds = Column(Integer, nullable=True)
    allow_infinite_session = Column(Boolean, nullable=False, default=False, server_default="0")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    restaurant = relationship("Restaurant", back_populates="users")
    permissions = relationship(
        "UserPermission",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sessions = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    logs = relationship("ActivityLog", back_populates="user")


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)

    code = Column(String(100), nullable=False, unique=True, index=True)
    name = Column(String(150), nullable=False)
    module_code = Column(String(50), nullable=False)

    role_permissions = relationship(
        "RolePermission",
        back_populates="permission",
        cascade="all, delete-orphan",
    )
    user_permissions = relationship(
        "UserPermission",
        back_populates="permission",
        cascade="all, delete-orphan",
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_code", "permission_id", name="uq_role_permission"),
    )

    id = Column(Integer, primary_key=True, index=True)

    role_code = Column(String(50), nullable=False, index=True)
    permission_id = Column(
        Integer,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    permission = relationship("Permission", back_populates="role_permissions")


class UserPermission(Base):
    __tablename__ = "user_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "permission_id", name="uq_user_permission"),
    )

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("restaurant_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_id = Column(
        Integer,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    is_allowed = Column(Boolean, nullable=False, default=True, server_default="1")

    user = relationship("RestaurantUser", back_populates="permissions")
    permission = relationship("Permission", back_populates="user_permissions")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(
        Integer,
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("restaurant_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    module_code = Column(String(50), nullable=False, index=True)

    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_activity_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    is_locked = Column(Boolean, nullable=False, default=False, server_default="0")
    locked_reason = Column(String(120), nullable=True)

    ip_address = Column(String(120), nullable=True)
    user_agent = Column(Text, nullable=True)

    restaurant = relationship("Restaurant", back_populates="sessions")
    user = relationship("RestaurantUser", back_populates="sessions")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)

    restaurant_id = Column(
        Integer,
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("restaurant_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    module_code = Column(String(50), nullable=False, index=True)
    action_code = Column(String(100), nullable=False, index=True)

    entity_type = Column(String(100), nullable=True)
    entity_id = Column(String(100), nullable=True)

    description = Column(Text, nullable=True)

    old_data_json = Column(Text, nullable=True)
    new_data_json = Column(Text, nullable=True)

    ip_address = Column(String(120), nullable=True)
    user_agent = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    restaurant = relationship("Restaurant", back_populates="logs")
    user = relationship("RestaurantUser", back_populates="logs")
