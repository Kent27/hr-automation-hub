from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Benefit(BaseModel):
    type: str = Field(..., min_length=1)
    limit: float = Field(..., ge=0)
    currency: str = Field(default="IDR", min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def _normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"IDR", "USD"}:
            raise ValueError("Benefit currency must be IDR or USD")
        return normalized


class Employee(BaseModel):
    id: str
    full_name: str = Field(..., min_length=1)
    email: str
    designation: Optional[str] = None
    salary: float = Field(..., ge=0)
    benefits: List[Benefit] = Field(default_factory=list)
    join_date: Optional[date] = None


class EmployeeCreate(BaseModel):
    full_name: str = Field(..., min_length=1)
    email: str
    designation: Optional[str] = None
    salary: float = Field(..., ge=0)
    benefits: List[Benefit] = Field(default_factory=list)
    join_date: Optional[date] = None


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1)
    email: Optional[str] = None
    designation: Optional[str] = None
    salary: Optional[float] = Field(None, ge=0)
    benefits: Optional[List[Benefit]] = None
    join_date: Optional[date] = None
