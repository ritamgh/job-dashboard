from __future__ import annotations
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, HttpUrl


class HiringStatus(str, Enum):
    yes = 'Yes'
    maybe = 'Maybe'
    no = 'No'
    unknown = 'Unknown'


class StartupInput(BaseModel):
    company: str
    website: str | None = None
    linkedin: str | None = None
    founder_linkedin: str | None = None
    twitter: str | None = None
    founder_twitter: str | None = None
    funding: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class StartupRecord(StartupInput):
    id: int
    product_summary: str | None = None
    ai_native_score: int = 0
    interestingness_score: int = 0
    resume_fit_score: int = 0
    hiring_likelihood_score: int = 0
    learning_challenge_score: int = 0
    logistics_score: int = 0
    overall_score: float = 0
    hiring_status: HiringStatus = HiringStatus.unknown
    hiring_evidence: str | None = None
    remote_india_fit: str | None = None
    research_confidence: int = 0
    evidence_urls: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    company_size_estimate: str | None = None
    company_size_confidence: int = 0
    company_size_source_url: str | None = None
    company_size_source_snippet: str | None = None
    message_short: str | None = None
    message_founder: str | None = None
    message_email: str | None = None


class ResearchResult(BaseModel):
    product_summary: str
    ai_native_score: int
    interestingness_score: int
    resume_fit_score: int
    hiring_likelihood_score: int
    learning_challenge_score: int
    logistics_score: int
    hiring_status: HiringStatus
    hiring_evidence: str
    remote_india_fit: str
    research_confidence: int
    evidence_urls: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class MessageRequest(BaseModel):
    style: str = Field(pattern='^(short|founder|email)$')
    force: bool = False


class OutreachSessionCreate(BaseModel):
    website: str
    company: str | None = None


class OutreachContactCreate(BaseModel):
    name: str | None = None
    role: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    confidence: int = Field(default=0, ge=0, le=100)
    source_url: str | None = None
    source_snippet: str | None = None


class OutreachDraftCreate(BaseModel):
    contact_id: int | None = None
    channel: str = Field(pattern='^(email|linkedin|followup)$')
    subject: str | None = None
    body: str


class OutreachDraftUpdate(BaseModel):
    edited_subject: str | None = None
    edited_body: str | None = None
    contact_id: int | None = None


class OutreachSendRequest(BaseModel):
    to: str
    subject: str | None = None
    body: str | None = None
    confirm_send: bool = False
