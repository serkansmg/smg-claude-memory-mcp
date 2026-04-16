"""Dependency injection container.

Wires together repositories and services in a single place so the
server layer can pull the composed graph without knowing construction details.
"""

from memory_mcp.repositories import (
    MemoryRepository, ProjectRepository, SessionRepository, ProvenanceRepository,
)
from memory_mcp.services import (
    MemoryService, SearchService, RulesService, RulesCache,
    SessionService, ProjectService, PortableService,
    ExportImportService, ModelService, UpdateService,
)


class Container:
    """Holds the instantiated dependency graph."""

    def __init__(self):
        # Repositories (stateless)
        self.memory_repo = MemoryRepository()
        self.project_repo = ProjectRepository()
        self.session_repo = SessionRepository()
        self.provenance_repo = ProvenanceRepository()

        # Caches
        self.rules_cache = RulesCache()

        # Services
        self.rules_service = RulesService(self.memory_repo, self.rules_cache)
        self.memory_service = MemoryService(
            self.memory_repo, self.provenance_repo,
            self.project_repo, self.rules_service,
        )
        self.search_service = SearchService(self.memory_repo)
        self.session_service = SessionService(
            self.session_repo, self.memory_repo,
            self.project_repo, self.rules_service,
        )
        self.project_service = ProjectService(self.project_repo)
        self.portable_service = PortableService(self.project_repo)
        self.export_import_service = ExportImportService(
            self.memory_repo, self.provenance_repo,
        )
        self.model_service = ModelService(self.memory_repo)
        self.update_service = UpdateService()


# Module-level singleton
container = Container()
