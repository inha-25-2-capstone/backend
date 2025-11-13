"""
Common Pydantic schemas for API.
"""
from typing import Optional, Generic, TypeVar, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class StanceType(str, Enum):
    """Stance classification types."""
    support = "support"
    neutral = "neutral"
    oppose = "oppose"


class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints."""
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    limit: int = Field(default=20, ge=1, le=100, description="Items per page")


class PaginationMeta(BaseModel):
    """Pagination metadata."""
    page: int = Field(description="Current page number")
    limit: int = Field(description="Items per page")
    total: int = Field(description="Total number of items")
    total_pages: int = Field(description="Total number of pages")


T = TypeVar('T')


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""
    data: List[T]
    pagination: PaginationMeta


class StanceData(BaseModel):
    """Stance analysis data (optional - model not ready yet)."""
    label: StanceType = Field(description="Stance classification")
    score: float = Field(ge=-1, le=1, description="Stance score [-1, 1]")
    probabilities: "StanceProbabilities" = Field(description="Classification probabilities")


class StanceProbabilities(BaseModel):
    """Stance classification probabilities."""
    support: float = Field(ge=0, le=1, description="Support probability")
    neutral: float = Field(ge=0, le=1, description="Neutral probability")
    oppose: float = Field(ge=0, le=1, description="Opposition probability")


class StanceDistribution(BaseModel):
    """Stance distribution for a topic."""
    support: int = Field(ge=0, description="Number of support articles")
    neutral: int = Field(ge=0, description="Number of neutral articles")
    oppose: int = Field(ge=0, description="Number of opposition articles")
