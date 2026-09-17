from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Table, Column, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(120), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    roles: Mapped[list["Role"]] = relationship(secondary=user_roles, lazy="selectin")


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    built_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    registration_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    permissions: Mapped[list["Permission"]] = relationship(secondary=role_permissions, lazy="selectin")


class Module(Base, TimestampMixin):
    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    icon: Mapped[str] = mapped_column(String(40), nullable=False, default="module")
    component_key: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    route_path: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    api_prefixes: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    api_permission: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    public_access: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    permissions: Mapped[list["Permission"]] = relationship(back_populates="module", lazy="selectin")


class Permission(Base, TimestampMixin):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    module_id: Mapped[Optional[int]] = mapped_column(ForeignKey("modules.id", ondelete="SET NULL"), nullable=True)
    module: Mapped[Optional[Module]] = relationship(back_populates="permissions")

    __table_args__ = (Index("idx_permission_module", "module_id"),)


class PublicIndicatorPolicy(Base, TimestampMixin):
    """Administrator-controlled public exposure for each indicator."""
    __tablename__ = "public_indicator_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    indicator_type: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    public_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    show_parameters: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    show_details: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    show_markers: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PublicIndicatorFeaturePolicy(Base, TimestampMixin):
    """Generic public visibility of any indicator's plots, markers or structures."""
    __tablename__ = "public_indicator_feature_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    indicator_type: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_code: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    public_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    show_details: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("indicator_type", "feature_code", name="uk_public_indicator_feature"),
        Index("idx_public_indicator_feature", "indicator_type", "sort_order"),
    )
