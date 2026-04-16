"""Project service - initialize and describe projects."""

from memory_mcp.config import settings
from memory_mcp.db.connection import get_connection
from memory_mcp.exceptions import ProjectNotFoundError
from memory_mcp.models import ProjectInfo
from memory_mcp.repositories import ProjectRepository
from memory_mcp.utils.text import slugify, validate_slug


class ProjectService:
    """Project lifecycle operations."""

    def __init__(self, project_repo: ProjectRepository):
        self._repo = project_repo

    def init_project(
        self,
        slug: str,
        display_name: str,
        description: str | None = None,
    ) -> ProjectInfo:
        if not validate_slug(slug):
            slug = slugify(slug)

        settings.ensure_dirs()
        project = self._repo.register(slug, display_name, description)

        # Ensure DB schema exists by opening + closing a connection
        conn = get_connection(slug)
        conn.close()

        return project

    def list_all(self) -> list[ProjectInfo]:
        return self._repo.list_all()

    def get(self, slug: str) -> ProjectInfo:
        project = self._repo.get(slug)
        if project is None:
            raise ProjectNotFoundError(f"Project '{slug}' not found")
        return project
