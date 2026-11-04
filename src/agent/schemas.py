"""Strict schemas for model-requested, read-only tool arguments."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: str | None = Field(default=None, max_length=120)
    category: str | None = Field(default=None, max_length=80)
    min_price_cents: int | None = Field(default=None, ge=0)
    max_price_cents: int | None = Field(default=None, ge=0)
    active_promotion: bool | None = None
    available_only: bool = True
    limit: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def validate_price_range(self) -> ProductSearchArgs:
        if (
            self.min_price_cents is not None
            and self.max_price_cents is not None
            and self.min_price_cents > self.max_price_cents
        ):
            raise ValueError("minimum price exceeds maximum price")
        return self


class OrderLookupArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    order_id: str = Field(min_length=1, max_length=80)


class PolicyLookupArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: str = Field(min_length=1, max_length=1000)
