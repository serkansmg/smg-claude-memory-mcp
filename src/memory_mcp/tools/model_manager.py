"""Embedding model management - switch between presets, persist config, re-embed."""

import json
from pathlib import Path

from memory_mcp.config import settings, EMBEDDING_MODELS
from memory_mcp.db.connection import connect
from memory_mcp.db.queries import MEMORY_COLUMNS, row_to_dict
from memory_mcp.db.provenance import record_provenance
from memory_mcp.utils.text import prepare_embedding_text

CONFIG_FILE = "model_config.json"


def _config_path() -> Path:
    return settings.data_dir / CONFIG_FILE


def load_persisted_model() -> None:
    path = _config_path()
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


def _persist_model(model_name: str) -> None:
    settings.ensure_dirs()
    _config_path().write_text(json.dumps({"embedding_model": model_name}, indent=2))


def get_model_info() -> dict:
    current = settings.embedding_model
    presets = {}
    for key, info in EMBEDDING_MODELS.items():
        presets[key] = {
            "name": info["name"],
            "languages": f"{len(info['languages'])} languages" if len(info["languages"]) > 1 else "English only",
            "disk": f"~{info['size_mb']}MB", "ram": f"~{info['ram_mb']}MB",
            "params": info["params"], "speed": info["speed"],
            "active": info["name"] == current,
        }
    return {"current_model": current, "current_preset": settings.model_preset, "presets": presets}


def set_model(preset: str, project: str | None = None, confirm: bool = False) -> dict:
    if preset not in EMBEDDING_MODELS:
        return {"error": f"Unknown preset '{preset}'. Available: {list(EMBEDDING_MODELS.keys())}"}

    new_model = EMBEDDING_MODELS[preset]
    old_model = settings.embedding_model
    if new_model["name"] == old_model:
        return {"status": "ok", "message": f"Already using '{preset}' ({old_model})."}

    memory_count = 0
    if project:
        with connect(project) as conn:
            memory_count = conn.execute("SELECT COUNT(*) FROM memories WHERE status = 'active'").fetchone()[0]

    impact = {
        "current_model": old_model, "new_model": new_model["name"],
        "disk_usage": f"~{new_model['size_mb']}MB", "ram_usage": f"~{new_model['ram_mb']}MB",
        "languages": f"{len(new_model['languages'])} languages" if len(new_model["languages"]) > 1 else "English only",
        "memories_to_reembed": memory_count,
    }

    if not confirm:
        return {"status": "confirmation_needed", "impact": impact,
                "message": f"Switching to '{new_model['name']}'. ~{new_model['ram_mb']}MB RAM, ~{new_model['size_mb']}MB disk. {memory_count} memories re-embedded. Call with confirm=True."}

    settings.embedding_model = new_model["name"]
    settings.embedding_dim = new_model["dim"]
    _persist_model(new_model["name"])

    import memory_mcp.embeddings as emb_module
    emb_module._model = None

    result = {"status": "ok", "old_model": old_model, "new_model": new_model["name"],
              "preset": preset, "persisted": True}

    if project and memory_count > 0:
        result["reembed"] = reembed_project(project)
    return result


def reembed_project(project: str) -> dict:
    from memory_mcp.embeddings import embed_texts

    with connect(project) as conn:
        rows = conn.execute(f"SELECT {MEMORY_COLUMNS} FROM memories WHERE status = 'active'").fetchall()
        if not rows:
            return {"reembedded": 0, "model": settings.embedding_model}

        memories = [row_to_dict(row) for row in rows]
        texts = [prepare_embedding_text(m["title"], m["content"]) for m in memories]
        embeddings = embed_texts(texts)

        reembedded = 0
        errors = []
        for mem, embedding in zip(memories, embeddings):
            try:
                conn.execute("UPDATE memories SET embedding = ?, updated_at = current_timestamp WHERE id = ?",
                             [embedding, mem["id"]])
                reembedded += 1
            except Exception as e:
                errors.append(f"{mem['id']}: {str(e)}")

    # Record provenance separately (opens its own connection)
    for mem in memories:
        record_provenance(project, mem["id"], "reembed", {"model": settings.embedding_model})

    return {"reembedded": reembedded, "errors": errors if errors else None, "model": settings.embedding_model}
