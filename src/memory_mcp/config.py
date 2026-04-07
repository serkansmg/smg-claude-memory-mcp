"""Configuration via environment variables and pydantic-settings."""

from pathlib import Path

from pydantic_settings import BaseSettings


# Available embedding model presets
EMBEDDING_MODELS = {
    "english": {
        "name": "all-MiniLM-L6-v2",
        "dim": 384,
        "languages": ["English"],
        "size_mb": 80,
        "ram_mb": 90,
        "params": "22M",
        "speed": "Very fast (~14k sentences/sec)",
        "description": "Lightweight English-only model. Best for English-only projects.",
    },
    "multilingual": {
        "name": "paraphrase-multilingual-MiniLM-L12-v2",
        "dim": 384,
        "languages": [
            "ar", "bg", "ca", "cs", "da", "de", "el", "en", "es", "et",
            "fa", "fi", "fr", "gl", "gu", "he", "hi", "hr", "hu", "hy",
            "id", "it", "ja", "ka", "ko", "ku", "lt", "lv", "mk", "mn",
            "mr", "ms", "my", "nb", "nl", "pl", "pt", "ro", "ru", "sk",
            "sl", "sq", "sr", "sv", "th", "tr", "uk", "ur", "vi",
        ],
        "size_mb": 470,
        "ram_mb": 500,
        "params": "118M",
        "speed": "Fast (~5k sentences/sec)",
        "description": "50+ languages including Turkish, Japanese, Korean, Arabic. Same 384 dimensions.",
    },
}


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

    @property
    def model_preset(self) -> str:
        """Return preset key for current model."""
        for key, info in EMBEDDING_MODELS.items():
            if info["name"] == self.embedding_model:
                return key
        return "custom"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
