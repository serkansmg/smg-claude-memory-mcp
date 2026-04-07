"""Embedding model management - switch between presets, re-embed existing memories."""

from memory_mcp.config import settings, EMBEDDING_MODELS
from memory_mcp.db.connection import get_connection
from memory_mcp.db.queries import MEMORY_COLUMNS, row_to_dict
from memory_mcp.db.provenance import record_provenance
from memory_mcp.utils.text import prepare_embedding_text


def get_model_info() -> dict:
    """Get current model info and available presets."""
    current = settings.embedding_model
    current_preset = settings.model_preset

    presets = {}
    for key, info in EMBEDDING_MODELS.items():
        presets[key] = {
            "name": info["name"],
            "languages": f"{len(info['languages'])} languages" if len(info["languages"]) > 1 else "English only",
            "disk": f"~{info['size_mb']}MB",
            "ram": f"~{info['ram_mb']}MB",
            "params": info["params"],
            "speed": info["speed"],
            "active": info["name"] == current,
        }

    return {
        "current_model": current,
        "current_preset": current_preset,
        "presets": presets,
    }


def set_model(
    preset: str,
    project: str | None = None,
    confirm: bool = False,
) -> dict:
    """Switch embedding model preset.

    Args:
        preset: 'english' or 'multilingual'
        project: If provided, re-embed this project's memories
        confirm: Must be True to proceed (after user sees the impact)
    """
    if preset not in EMBEDDING_MODELS:
        return {
            "error": f"Unknown preset '{preset}'. Available: {list(EMBEDDING_MODELS.keys())}",
        }

    new_model = EMBEDDING_MODELS[preset]
    old_model = settings.embedding_model

    if new_model["name"] == old_model:
        return {
            "status": "ok",
            "message": f"Already using '{preset}' ({old_model}). No change needed.",
        }

    # Calculate impact
    memory_count = 0
    if project:
        conn = get_connection(project)
        memory_count = conn.execute("SELECT COUNT(*) FROM memories WHERE status = 'active'").fetchone()[0]

    impact = {
        "current_model": old_model,
        "new_model": new_model["name"],
        "new_preset": preset,
        "disk_usage": f"~{new_model['size_mb']}MB (model download)",
        "ram_usage": f"~{new_model['ram_mb']}MB",
        "languages": f"{len(new_model['languages'])} languages" if len(new_model["languages"]) > 1 else "English only",
        "memories_to_reembed": memory_count,
        "reembed_note": f"{memory_count} memories will be re-embedded with the new model" if memory_count > 0 else "No memories to re-embed",
    }

    if not confirm:
        return {
            "status": "confirmation_needed",
            "impact": impact,
            "message": f"Switching from '{old_model}' to '{new_model['name']}'. "
                       f"This will use ~{new_model['ram_mb']}MB RAM and ~{new_model['size_mb']}MB disk. "
                       f"{memory_count} existing memories will be re-embedded. "
                       f"Call again with confirm=True to proceed.",
        }

    # Apply the change
    settings.embedding_model = new_model["name"]
    settings.embedding_dim = new_model["dim"]

    # Force reload of embedding model
    import memory_mcp.embeddings as emb_module
    emb_module._model = None

    result = {
        "status": "ok",
        "old_model": old_model,
        "new_model": new_model["name"],
        "preset": preset,
        "message": f"Switched to '{preset}' ({new_model['name']}). Model will be downloaded on next use.",
    }

    # Re-embed if project specified
    if project and memory_count > 0:
        reembed_result = reembed_project(project)
        result["reembed"] = reembed_result

    return result


def reembed_project(project: str) -> dict:
    """Re-embed all active memories in a project with the current model."""
    from memory_mcp.embeddings import embed_text

    conn = get_connection(project)
    rows = conn.execute(
        f"SELECT {MEMORY_COLUMNS} FROM memories WHERE status = 'active'"
    ).fetchall()

    reembedded = 0
    errors = []

    for row in rows:
        memory = row_to_dict(row)
        memory_id = memory["id"]
        title = memory["title"]
        content = memory["content"]

        try:
            embedding_text = prepare_embedding_text(title, content)
            new_embedding = embed_text(embedding_text)

            conn.execute(
                "UPDATE memories SET embedding = ?, updated_at = current_timestamp WHERE id = ?",
                [new_embedding, memory_id],
            )

            record_provenance(project, memory_id, "reembed", {
                "model": settings.embedding_model,
                "reason": "model_switch",
            })

            reembedded += 1
        except Exception as e:
            errors.append(f"{memory_id}: {str(e)}")

    return {
        "reembedded": reembedded,
        "errors": errors if errors else None,
        "model": settings.embedding_model,
    }
