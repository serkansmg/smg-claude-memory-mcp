"""Memory service - orchestrates store/update/delete with embeddings, summaries, entities."""

import json
import uuid

from memory_mcp.embeddings import embed_text
from memory_mcp.exceptions import MemoryNotFoundError, InvalidCategoryError
from memory_mcp.models import (
    Memory, MemoryCategory, RULE_CATEGORIES,
    StoreMemoryRequest, UpdateMemoryRequest,
)
from memory_mcp.repositories import MemoryRepository, ProjectRepository, ProvenanceRepository
from memory_mcp.services.rules_service import RulesService
from memory_mcp.utils.extraction import calculate_expiry, extract_entities, generate_summary
from memory_mcp.utils.text import prepare_embedding_text


class MemoryService:
    """Business logic for memory CRUD."""

    def __init__(
        self,
        memory_repo: MemoryRepository,
        provenance_repo: ProvenanceRepository,
        project_repo: ProjectRepository,
        rules_service: RulesService,
    ):
        self._memory_repo = memory_repo
        self._provenance_repo = provenance_repo
        self._project_repo = project_repo
        self._rules_service = rules_service

    # ---------- Store ----------

    def store(self, request: StoreMemoryRequest) -> Memory:
        # Force priority for rules
        priority = request.priority
        if request.category in RULE_CATEGORIES:
            priority = max(priority, 2)

        summary = generate_summary(request.title, request.content)
        entities = extract_entities(f"{request.title} {request.content}")
        expires_at = calculate_expiry(request.category.value, priority)
        embedding = embed_text(prepare_embedding_text(request.title, request.content))
        memory_id = str(uuid.uuid4())

        memory = self._memory_repo.insert(
            project=request.project,
            memory_id=memory_id,
            category=request.category.value,
            title=request.title,
            content=request.content,
            summary=summary,
            tags=request.tags,
            metadata=request.metadata,
            embedding=embedding,
            priority=priority,
            source=request.source,
            related_ids=request.related_ids,
            entities=entities,
            expires_at=expires_at,
        )

        self._project_repo.touch(request.project)
        self._provenance_repo.record(
            request.project, memory_id, "create",
            {
                "category": request.category.value, "title": request.title,
                "source": request.source, "entities_extracted": len(entities),
            },
        )

        if request.category in RULE_CATEGORIES:
            self._rules_service.invalidate(request.project)

        return memory

    # ---------- Recall ----------

    def recall(self, project: str, memory_id: str | None, title: str | None) -> Memory:
        if not memory_id and not title:
            raise ValueError("Provide either memory_id or title")

        memory = None
        if memory_id:
            memory = self._memory_repo.get_by_id(project, memory_id)
        else:
            memory = self._memory_repo.get_by_title(project, title)

        if memory is None:
            raise MemoryNotFoundError(f"Memory not found: id={memory_id}, title={title}")

        self._memory_repo.increment_access(project, memory.id)
        self._provenance_repo.record(project, memory.id, "access", {"method": "recall"})
        return memory

    # ---------- Update ----------

    def update(self, request: UpdateMemoryRequest) -> Memory:
        existing = self._memory_repo.get_by_id(request.project, request.memory_id)
        if existing is None:
            raise MemoryNotFoundError(f"Memory not found: {request.memory_id}")

        fields: dict = {}
        changed_fields: list[str] = []

        if request.title is not None:
            fields["title"] = request.title; changed_fields.append("title")
        if request.content is not None:
            fields["content"] = request.content; changed_fields.append("content")
        if request.tags is not None:
            fields["tags"] = request.tags; changed_fields.append("tags")
        if request.metadata is not None:
            fields["metadata"] = json.dumps(request.metadata); changed_fields.append("metadata")
        if request.status is not None:
            fields["status"] = request.status; changed_fields.append("status")
        if request.priority is not None:
            fields["priority"] = request.priority; changed_fields.append("priority")
        if request.related_ids is not None:
            fields["related_ids"] = request.related_ids; changed_fields.append("related_ids")

        if not fields:
            return existing

        # Re-embed / re-summarize / re-extract entities if title or content changed
        if request.title is not None or request.content is not None:
            new_title = request.title or existing.title
            new_content = request.content or existing.content
            fields["embedding"] = embed_text(prepare_embedding_text(new_title, new_content))
            fields["summary"] = generate_summary(new_title, new_content)
            fields["entities"] = extract_entities(f"{new_title} {new_content}")

        updated = self._memory_repo.update(request.project, request.memory_id, fields)
        self._provenance_repo.record(
            request.project, request.memory_id, "update",
            {"changed_fields": changed_fields},
        )

        if existing.category in RULE_CATEGORIES:
            self._rules_service.invalidate(request.project)

        return updated

    # ---------- Delete ----------

    def delete(self, project: str, memory_id: str, hard: bool = False, reason: str | None = None) -> dict:
        existing = self._memory_repo.get_by_id(project, memory_id)
        if existing is None:
            raise MemoryNotFoundError(f"Memory not found: {memory_id}")

        action = "hard_delete" if hard else "soft_delete"
        self._provenance_repo.record(project, memory_id, action, {"reason": reason})

        if hard:
            self._memory_repo.hard_delete(project, memory_id)
            result_action = "hard_deleted"
        else:
            self._memory_repo.soft_delete(project, memory_id)
            result_action = "archived"

        if existing.category in RULE_CATEGORIES:
            self._rules_service.invalidate(project)

        return {"status": "ok", "action": result_action, "memory_id": memory_id}
