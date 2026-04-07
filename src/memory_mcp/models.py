"""Pydantic models for Memory MCP Server."""

from datetime import datetime
from enum import Enum

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


class Memory(BaseModel):
    id: str
    category: MemoryCategory
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict | None = None
    embedding: list[float] | None = None
    status: str = "active"
    priority: int = 0
    source: str | None = None
    related_ids: list[str] = Field(default_factory=list)
    access_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SearchResult(BaseModel):
    memory: Memory
    similarity: float
    relevance_score: float


class SessionContext(BaseModel):
    session_id: str
    project: str
    mandatory_rules: list[Memory]
    forbidden_rules: list[Memory]
    last_session_summary: str | None = None
    active_sprint: list[Memory]
    recent_decisions: list[Memory]


class ProjectInfo(BaseModel):
    slug: str
    display_name: str
    description: str | None = None
    created_at: datetime | None = None
    last_accessed: datetime | None = None
    db_path: str | None = None
