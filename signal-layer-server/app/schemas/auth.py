from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    email: Optional[str] = Field(default=None, max_length=120)
    display_name: str = Field(default="", max_length=80)


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ModuleResponse(BaseModel):
    id: int
    code: str
    name: str
    icon: str
    component_key: str
    route_path: str
    api_prefixes: str
    api_permission: str
    sort_order: int
    enabled: bool
    visible: bool


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    display_name: str
    enabled: bool
    role_codes: list[str]
    permission_codes: list[str]
    modules: list[ModuleResponse] = Field(default_factory=list)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: int
    user: UserResponse


class PermissionResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str
    module_code: Optional[str]


class RoleResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str
    built_in: bool
    enabled: bool
    permission_codes: list[str]


class RoleCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=255)
    enabled: bool = True
    permission_codes: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=255)
    enabled: Optional[bool] = None
    permission_codes: Optional[list[str]] = None


class UserRoleUpdate(BaseModel):
    role_codes: list[str]
    enabled: Optional[bool] = None


class ModuleCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=80)
    icon: str = Field(default="module", max_length=40)
    component_key: str = Field(default="", max_length=80)
    route_path: str = Field(default="", max_length=120)
    api_prefixes: str = Field(default="", max_length=500)
    api_permission: str = Field(default="", max_length=100)
    sort_order: int = 0
    enabled: bool = True
    visible: bool = True


class ModuleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    icon: Optional[str] = Field(default=None, max_length=40)
    component_key: Optional[str] = Field(default=None, max_length=80)
    route_path: Optional[str] = Field(default=None, max_length=120)
    api_prefixes: Optional[str] = Field(default=None, max_length=500)
    api_permission: Optional[str] = Field(default=None, max_length=100)
    sort_order: Optional[int] = None
    enabled: Optional[bool] = None
    visible: Optional[bool] = None


class PermissionCreate(BaseModel):
    code: str = Field(min_length=3, max_length=100, pattern=r"^[a-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=255)
    module_code: Optional[str] = None
