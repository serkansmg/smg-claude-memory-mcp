"""Custom exception hierarchy for Memory MCP.

All domain errors inherit from MemoryMCPError so the tool layer can catch
a single base class and return consistent error responses.
"""


class MemoryMCPError(Exception):
    """Base exception for all Memory MCP domain errors."""


class ProjectNotFoundError(MemoryMCPError):
    """Raised when a requested project does not exist in the registry."""


class ProjectAlreadyExistsError(MemoryMCPError):
    """Raised when trying to create a project with a slug that already exists."""


class NoActiveProjectError(MemoryMCPError):
    """Raised when a tool needs a project and none is set or detected."""


class MemoryNotFoundError(MemoryMCPError):
    """Raised when a memory with the given ID or title does not exist."""


class InvalidCategoryError(MemoryMCPError):
    """Raised when an unknown memory category is provided."""


class ValidationError(MemoryMCPError):
    """Raised when request validation fails (beyond Pydantic's own errors)."""


class DatabaseError(MemoryMCPError):
    """Raised when a database operation fails unexpectedly."""


class ModelNotFoundError(MemoryMCPError):
    """Raised when an embedding model preset is not recognized."""


class ExportImportError(MemoryMCPError):
    """Raised on export/import failures (file system, parsing, etc.)."""
