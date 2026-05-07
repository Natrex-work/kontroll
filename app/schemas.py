from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TextPolishRequest(BaseModel):
    mode: str = Field(default='generic', max_length=40)
    text: str = Field(default='', max_length=20000)
    case_basis: str = Field(default='patruljeobservasjon', max_length=40)
    source_name: str = Field(default='', max_length=200)
    subject: str = Field(default='', max_length=200)
    location: str = Field(default='', max_length=200)


class SummarySuggestRequest(BaseModel):
    findings: list[dict[str, Any]] = Field(default_factory=list)
    persons: list[dict[str, Any]] = Field(default_factory=list)
    seizure_reports: list[dict[str, Any]] = Field(default_factory=list)
    case_basis: str = Field(default='patruljeobservasjon', max_length=40)
    control_type: str = Field(default='', max_length=100)
    species: str = Field(default='', max_length=100)
    fishery_type: str = Field(default='', max_length=100)
    gear_type: str = Field(default='', max_length=100)
    location_name: str = Field(default='', max_length=200)
    area_name: str = Field(default='', max_length=200)
    area_status: str = Field(default='', max_length=200)
    suspect_name: str = Field(default='', max_length=200)
    vessel_name: str = Field(default='', max_length=200)
    investigator_name: str = Field(default='', max_length=200)
    basis_source_name: str = Field(default='', max_length=200)
    basis_details: str = Field(default='', max_length=8000)
    start_time: str = Field(default='', max_length=50)
    latitude: float | None = None
    longitude: float | None = None
