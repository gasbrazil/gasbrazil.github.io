"""Pydantic response models for the GasBrazil API (Track C)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ok: bool = Field(description="True when all critical datasets are available")
    datasets: dict[str, bool] = Field(description="Availability status of all lake datasets")
    critical: list[str] = Field(description="List of critical dataset keys required for ok=True")
    transforms: dict[str, Any] = Field(description="Summary of registered transformation versions")


class BasePaginatedResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    count: int = Field(description="Total matching rows before pagination limit")
    limit: int = Field(description="Maximum rows requested in this page")
    offset: int = Field(default=0, description="Starting row offset for pagination")
    rows: list[dict[str, Any]] = Field(description="List of records")


class FlowsPointsResponse(BasePaginatedResponse):
    pass


class PldDailyResponse(BasePaginatedResponse):
    pass


class PldHourlyResponse(BasePaginatedResponse):
    tou: str = Field(description="TOU version identifier")


class SupplyMonthlyResponse(BasePaginatedResponse):
    pass


class PrecosPricesResponse(BasePaginatedResponse):
    pass


class OnsBalancesResponse(BasePaginatedResponse):
    pass


class PowerPldCmoResponse(BasePaginatedResponse):
    transform: str = Field(description="Transform mapping key used for the join")
