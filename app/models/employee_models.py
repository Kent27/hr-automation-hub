from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class Benefit(BaseModel):
    type: str = Field(..., min_length=1)
    limit: float = Field(..., ge=0)


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
