"""Pydantic models for Memory MCP Server.

Domain models (Memory, ProjectInfo, Session) represent stored entities.
Request models (Store*Request, Search*Request) are inputs to service methods.
Response models wrap service outputs consistently.
"""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class MemoryCategory(str, Enum):
    DECISION = "decision"
    SESSION = "session"
    SPRINT = "sprint"
    PROJECT_PLAN = "project_plan"
    ARCHITECTURE = "architecture"
    DEVOPS = "devops"
    MANDATORY_RULES = "mandatory_rules"
    FORBIDDEN_RULES = "forbidden_rules"
    DEVELOPER_DOCS = "developer_docs"
    FEEDBACK = "feedback"
    REFERENCE = "reference"


RULE_CATEGORIES = {MemoryCategory.MANDATORY_RULES, MemoryCategory.FORBIDDEN_RULES}


# --- Domain Models ---


class Memory(BaseModel):
    id: str
    category: MemoryCategory
    title: str
    content: str
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict | None = None
    embedding: list[float] | None = None
    status: str = "active"
    priority: int = 0
    source: str | None = None
    related_ids: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    access_count: int = 0
    expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectInfo(BaseModel):
    slug: str
    display_name: str
    description: str | None = None
    created_at: datetime | None = None
    last_accessed: datetime | None = None
    db_path: str | None = None


class SessionRecord(BaseModel):
    id: str
    started_at: datetime
    ended_at: datetime | None = None
    summary: str | None = None
    memories_created: int = 0
    memories_accessed: int = 0


class ProvenanceEntry(BaseModel):
    id: int
    memory_id: str
    operation: str
    details: dict | None = None
    created_at: datetime | None = None


# --- Request Models ---


class StoreMemoryRequest(BaseModel):
    project: str
    category: MemoryCategory
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    metadata: dict | None = None
    priority: int = Field(default=0, ge=0, le=3)
    source: str = "assistant"
    related_ids: list[str] = Field(default_factory=list)


class UpdateMemoryRequest(BaseModel):
    project: str
    memory_id: str
    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = None
    tags: list[str] | None = None
    metadata: dict | None = None
    status: str | None = None
    priority: int | None = Field(default=None, ge=0, le=3)
    related_ids: list[str] | None = None


class SearchRequest(BaseModel):
    project: str
    query: str = Field(min_length=1)
    category: MemoryCategory | None = None
    tags: list[str] | None = None
    status: str = "active"
    limit: int = Field(default=10, ge=1, le=100)
    min_similarity: float = Field(default=0.3, ge=0.0, le=1.0)
    token_budget: int | None = Field(default=None, ge=1)


class MemoryFilter(BaseModel):
    status: str = "active"
    category: str | None = None
    tags: list[str] | None = None


class Pagination(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    sort_by: Literal["created_at", "updated_at", "title", "priority", "access_count", "category"] = "updated_at"
    sort_order: Literal["asc", "desc"] = "desc"


# --- Response Models ---


class SearchHit(BaseModel):
    memory: Memory
    similarity: float
    relevance_score: float


class SearchResponse(BaseModel):
    results: list[SearchHit]
    total: int
    query: str


class SearchResponseTokenBudgeted(BaseModel):
    index: list[dict]
    details: list[SearchHit]
    total: int
    tokens_used: int
    has_more: bool
    query: str


class ListResponse(BaseModel):
    memories: list[Memory]
    total: int
    limit: int
    offset: int


class RulesResponse(BaseModel):
    mandatory_rules: list[Memory]
    forbidden_rules: list[Memory]
    total: int


class SessionContext(BaseModel):
    session_id: str
    project: str
    mandatory_rules: list[Memory]
    forbidden_rules: list[Memory]
    last_session_summary: str | None = None
    active_sprint: list[Memory]
    recent_decisions: list[Memory]
    orphaned_sessions_closed: int = 0
