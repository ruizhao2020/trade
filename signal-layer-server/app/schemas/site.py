from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PublicIndicatorPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    indicator_type: str
    display_name: str
    public_visible: bool
    show_parameters: bool
    show_details: bool
    show_markers: bool
    sort_order: int


class PublicIndicatorPolicyUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=100)
    public_visible: Optional[bool] = None
    show_parameters: Optional[bool] = None
    show_details: Optional[bool] = None
    show_markers: Optional[bool] = None
    sort_order: Optional[int] = None


class PublicIndicatorFeaturePolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    indicator_type: str
    feature_code: str
    display_name: str
    public_visible: bool
    show_details: bool
    sort_order: int


class PublicIndicatorFeaturePolicyUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=100)
    public_visible: Optional[bool] = None
    show_details: Optional[bool] = None
    sort_order: Optional[int] = None


class PublicIndicatorFeaturePolicyCreate(BaseModel):
    indicator_type: str = Field(min_length=1, max_length=64)
    feature_code: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=100)
    public_visible: bool = False
    show_details: bool = False
    sort_order: int = 1000


class PublicSiteConfigResponse(BaseModel):
    surface: str = "public"
    authentication: bool = False
    modules: list[str] = ["indicators"]
    indicators: list[PublicIndicatorPolicyResponse]
    indicator_features: list[PublicIndicatorFeaturePolicyResponse]
