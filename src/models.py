"""Canonical JSON schemas for the intelligence graph pipeline.

Every record carries schemaVersion, recordType, source provenance and a
collection timestamp, matching the demo-task specification.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PricingModel(str, Enum):
    FREE = "FREE"
    FREEMIUM = "FREEMIUM"
    PAID = "PAID"
    ENTERPRISE = "ENTERPRISE"


class Source(BaseModel):
    name: str
    url: str


class StartupContent(BaseModel):
    entityName: str
    website: Optional[str] = None
    description: Optional[str] = None
    batch: Optional[str] = None
    location: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    data: dict = Field(default_factory=dict)  # employeeCount etc.


class StartupRecord(BaseModel):
    schemaVersion: str = SCHEMA_VERSION
    recordType: str = "STARTUP"
    source: Source
    content: StartupContent
    collectedAt: str = Field(default_factory=utcnow_iso)


class ProductContent(BaseModel):
    productName: str
    startupName: Optional[str] = None
    description: Optional[str] = None
    pricingModel: PricingModel = PricingModel.FREE
    categories: list[str] = Field(default_factory=list)


class ProductRecord(BaseModel):
    schemaVersion: str = SCHEMA_VERSION
    recordType: str = "PRODUCT"
    source: Source
    content: ProductContent
    collectedAt: str = Field(default_factory=utcnow_iso)


class PaperContent(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    paper_url: str
    abstract: Optional[str] = None
    github_url: Optional[str] = None
    github_stars: Optional[int] = None
    stars_source: Optional[str] = None
    published_date: Optional[str] = None


class PaperRecord(BaseModel):
    schemaVersion: str = SCHEMA_VERSION
    recordType: str = "RESEARCH_PAPER"
    source: Source
    content: PaperContent
    collectedAt: str = Field(default_factory=utcnow_iso)


class JobContent(BaseModel):
    title: str
    company: str
    date: str
    url: str
    location: Optional[str] = None
    is_remote: bool = False
    role_family: str = "Engineering"
    description: Optional[str] = None


class JobRecord(BaseModel):
    schemaVersion: str = SCHEMA_VERSION
    recordType: str = "JOB"
    source: Source
    content: JobContent
    collectedAt: str = Field(default_factory=utcnow_iso)


class NewsContent(BaseModel):
    headline: str
    url: str
    published_date: str
    full_text: Optional[str] = None
    summary: Optional[str] = None
    date_confidence: str = "high"  # high | medium | heuristic


class NewsRecord(BaseModel):
    schemaVersion: str = SCHEMA_VERSION
    recordType: str = "NEWS"
    source: Source
    content: NewsContent
    collectedAt: str = Field(default_factory=utcnow_iso)


class EntityMapping(BaseModel):
    raw_name: str
    canonical_name: str
    record_type: str
    match_strategy: str  # exact | normalized | fuzzy | alias | unmatched
    confidence: float
    decided_at: str = Field(default_factory=utcnow_iso)
