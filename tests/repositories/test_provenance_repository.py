"""Unit tests for ProvenanceRepository."""

import uuid

import pytest

from memory_mcp.repositories import ProvenanceRepository, ProjectRepository
from memory_mcp.db.connection import get_connection


@pytest.fixture
def repo():
    return ProvenanceRepository()


@pytest.fixture
def project(project_slug) -> str:
    pr = ProjectRepository()
    pr.register(project_slug, "Test")
    conn = get_connection(project_slug)
    conn.close()
    return project_slug


class TestProvenance:
    def test_record_and_retrieve(self, repo, project):
        mid = str(uuid.uuid4())
        repo.record(project, mid, "create", {"source": "test"})
        repo.record(project, mid, "update", {"field": "title"})
        repo.record(project, mid, "access", None)

        entries = repo.for_memory(project, mid)
        assert len(entries) == 3
        ops = [e.operation for e in entries]
        assert ops == ["create", "update", "access"]

        # Details round-trip
        assert entries[0].details == {"source": "test"}
        assert entries[2].details is None

    def test_empty_for_unknown_memory(self, repo, project):
        entries = repo.for_memory(project, "unknown")
        assert entries == []
