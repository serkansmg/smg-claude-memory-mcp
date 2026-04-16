"""Model service - manage embedding model presets, persist config, re-embed."""

import json
from pathlib import Path

from memory_mcp.config import EMBEDDING_MODELS, settings
from memory_mcp.embeddings import embed_texts
from memory_mcp.exceptions import ModelNotFoundError
from memory_mcp.repositories import MemoryRepository
from memory_mcp.utils.text import prepare_embedding_text

CONFIG_FILE = "model_config.json"


class ModelService:
    """Manage embedding model selection with persistence and re-embedding."""

    def __init__(self, memory_repo: MemoryRepository):
        self._memory_repo = memory_repo

    def _config_path(self) -> Path:
        return settings.data_dir / CONFIG_FILE

    def load_persisted(self) -> None:
        """Load persisted model config on startup."""
        path = self._config_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            model_name = data.get("embedding_model")
            if model_name:
                settings.embedding_model = model_name
                for info in EMBEDDING_MODELS.values():
                    if info["name"] == model_name:
                        settings.embedding_dim = info["dim"]
                        break
        except Exception:
            pass

    def _persist(self, model_name: str) -> None:
        settings.ensure_dirs()
        self._config_path().write_text(
            json.dumps({"embedding_model": model_name}, indent=2)
        )

    def info(self) -> dict:
        current = settings.embedding_model
        presets = {}
        for key, info in EMBEDDING_MODELS.items():
            presets[key] = {
                "name": info["name"],
                "languages": (
                    f"{len(info['languages'])} languages"
                    if len(info["languages"]) > 1
                    else "English only"
                ),
                "disk": f"~{info['size_mb']}MB",
                "ram": f"~{info['ram_mb']}MB",
                "params": info["params"],
                "speed": info["speed"],
                "active": info["name"] == current,
            }
        return {
            "current_model": current,
            "current_preset": settings.model_preset,
            "presets": presets,
        }

    def set_model(
        self,
        preset: str,
        project: str | None = None,
        confirm: bool = False,
    ) -> dict:
        if preset not in EMBEDDING_MODELS:
            raise ModelNotFoundError(
                f"Unknown preset '{preset}'. Available: {list(EMBEDDING_MODELS.keys())}"
            )

        new_model = EMBEDDING_MODELS[preset]
        old_model = settings.embedding_model
        if new_model["name"] == old_model:
            return {"status": "ok", "message": f"Already using '{preset}'."}

        memory_count = 0
        if project:
            memory_count = self._memory_repo.count_active(project)

        impact = {
            "current_model": old_model,
            "new_model": new_model["name"],
            "disk_usage": f"~{new_model['size_mb']}MB",
            "ram_usage": f"~{new_model['ram_mb']}MB",
            "languages": (
                f"{len(new_model['languages'])} languages"
                if len(new_model["languages"]) > 1
                else "English only"
            ),
            "memories_to_reembed": memory_count,
        }

        if not confirm:
            return {
                "status": "confirmation_needed",
                "impact": impact,
                "message": (
                    f"Switching to '{new_model['name']}'. "
                    f"~{new_model['ram_mb']}MB RAM, ~{new_model['size_mb']}MB disk. "
                    f"{memory_count} memories re-embedded. Call with confirm=True."
                ),
            }

        settings.embedding_model = new_model["name"]
        settings.embedding_dim = new_model["dim"]
        self._persist(new_model["name"])

        # Force reload of the cached model
        import memory_mcp.embeddings as emb_module
        emb_module._model = None

        result = {
            "status": "ok",
            "old_model": old_model,
            "new_model": new_model["name"],
            "preset": preset,
            "persisted": True,
        }

        if project and memory_count > 0:
            result["reembed"] = self.reembed(project)
        return result

    def reembed(self, project: str) -> dict:
        memories = list(self._memory_repo.iter_active(project))
        if not memories:
            return {"reembedded": 0, "model": settings.embedding_model}

        texts = [prepare_embedding_text(m.title, m.content) for m in memories]
        embeddings = embed_texts(texts)

        reembedded = 0
        errors: list[str] = []
        for memory, embedding in zip(memories, embeddings):
            try:
                self._memory_repo.update_embedding(project, memory.id, embedding)
                reembedded += 1
            except Exception as e:
                errors.append(f"{memory.id}: {e}")

        return {
            "reembedded": reembedded,
            "errors": errors if errors else None,
            "model": settings.embedding_model,
        }
