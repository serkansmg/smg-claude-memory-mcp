"""Auto-setup script for memory-mcp.

Handles:
1. Directory creation (~/.memory-mcp/)
2. DuckDB VSS extension installation
3. Embedding model download
4. Claude Code MCP configuration
"""

import json
import sys
from pathlib import Path

from memory_mcp.config import settings


def print_step(step: int, total: int, msg: str) -> None:
    print(f"  [{step}/{total}] {msg}")


def setup_directories() -> None:
    """Create required directories."""
    settings.ensure_dirs()
    print(f"    Data dir: {settings.data_dir}")
    print(f"    Projects: {settings.projects_dir}")
    print(f"    Backups:  {settings.backups_dir}")


def setup_vss() -> None:
    """Install DuckDB VSS extension."""
    import duckdb

    conn = duckdb.connect()
    conn.execute("INSTALL vss;")
    conn.execute("LOAD vss;")
    conn.close()


def setup_embedding_model() -> None:
    """Download and cache the embedding model."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(settings.embedding_model)
    # Verify it works
    test = model.encode("test", normalize_embeddings=True)
    assert len(test) == settings.embedding_dim, f"Expected {settings.embedding_dim} dims, got {len(test)}"


def get_claude_config_path() -> Path:
    """Find the Claude Code settings file."""
    # Claude Code stores MCP config in ~/.claude.json or project-level .mcp.json
    return Path.home() / ".claude.json"


def setup_claude_config(server_dir: str | None = None) -> None:
    """Add memory-mcp to Claude Code MCP configuration."""
    config_path = get_claude_config_path()

    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    # Determine the server directory
    if not server_dir:
        server_dir = str(Path(__file__).resolve().parent.parent.parent)

    config["mcpServers"]["memory"] = {
        "command": "uv",
        "args": ["run", "--directory", server_dir, "memory-mcp"],
        "env": {
            "MEMORY_MCP_DATA_DIR": str(settings.data_dir),
        },
    }

    config_path.write_text(json.dumps(config, indent=2))
    print(f"    Config: {config_path}")


def main() -> None:
    """Run full auto-setup."""
    print()
    print("=" * 60)
    print("  Memory MCP Server - Auto Setup")
    print("=" * 60)
    print()

    total = 4

    print_step(1, total, "Creating directories...")
    setup_directories()
    print("    Done.")
    print()

    print_step(2, total, "Installing DuckDB VSS extension...")
    try:
        setup_vss()
        print("    Done.")
    except Exception as e:
        print(f"    Warning: {e}")
        print("    VSS will be installed on first use.")
    print()

    print_step(3, total, "Downloading embedding model (all-MiniLM-L6-v2, ~80MB)...")
    print("    This may take a minute on first run...")
    try:
        setup_embedding_model()
        print(f"    Model: {settings.embedding_model} ({settings.embedding_dim} dimensions)")
        print("    Done.")
    except Exception as e:
        print(f"    Warning: {e}")
        print("    Model will be downloaded on first use.")
    print()

    print_step(4, total, "Configuring Claude Code MCP...")
    try:
        setup_claude_config()
        print("    Done.")
    except Exception as e:
        print(f"    Warning: {e}")
        print("    You can manually add the MCP config later.")
    print()

    print("=" * 60)
    print("  Setup complete!")
    print()
    print("  Usage:")
    print("    1. Restart Claude Code")
    print("    2. Use memory_init_project to create your first project")
    print("    3. Use memory_session_start at the beginning of each session")
    print()
    print("  Manual MCP config (if auto-config failed):")
    print('    Add to ~/.claude.json or .mcp.json:')
    print()
    print('    "memory": {')
    print('      "command": "uv",')
    print(f'      "args": ["run", "--directory", "<path-to-memory-mcp>", "memory-mcp"]')
    print("    }")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
