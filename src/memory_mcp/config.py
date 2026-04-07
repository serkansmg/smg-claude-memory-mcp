"""Configuration via environment variables and pydantic-settings."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "MEMORY_MCP_"}

    data_dir: Path = Path.home() / ".memory-mcp"
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384
    max_connections: int = 5
    rules_cache_ttl: int = 60
    search_oversample: int = 3
    relevance_weights: tuple[float, float, float] = (0.7, 0.15, 0.15)

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def registry_path(self) -> Path:
        return self.data_dir / "registry.duckdb"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
