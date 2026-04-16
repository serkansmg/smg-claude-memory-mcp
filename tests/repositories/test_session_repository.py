"""Unit tests for SessionRepository."""

import uuid

import pytest

from memory_mcp.repositories import SessionRepository, ProjectRepository
from memory_mcp.db.connection import get_connection


@pytest.fixture
def repo():
    return SessionRepository()


@pytest.fixture
def project(project_slug) -> str:
    pr = ProjectRepository()
    pr.register(project_slug, "Test")
    conn = get_connection(project_slug)
    conn.close()
    return project_slug


class TestLifecycle:
    def test_insert_and_end(self, repo, project):
        sid = str(uuid.uuid4())
        repo.insert(project, sid)
        # No exception = success
        repo.end(project, sid, "summary text", memories_created=3, memories_accessed=5)
        last = repo.last_with_summary(project)
        assert last is not None
        assert last.summary == "summary text"
        assert last.memories_created == 3

    def test_orphaned_detects_unended(self, repo, project):
        sid1 = str(uuid.uuid4())
        sid2 = str(uuid.uuid4())
        repo.insert(project, sid1)
        repo.insert(project, sid2)
        repo.end(project, sid1, "done")

        orphans = repo.orphaned(project)
        assert sid2 in orphans
        assert sid1 not in orphans

    def test_last_with_summary_filters(self, repo, project):
        s1 = str(uuid.uuid4())
        s2 = str(uuid.uuid4())
        repo.insert(project, s1)
        repo.end(project, s1, "[auto-closed]")
        repo.insert(project, s2)
        repo.end(project, s2, "real work")

        last_excluding = repo.last_with_summary(project, exclude_summary="[auto-closed]")
        assert last_excluding.summary == "real work"
