# Memory MCP Server

Production-grade vector memory MCP server with DuckDB + semantic search.

## Auto-Memory Behavior

When this MCP is active and a project session is running, Claude should AUTOMATICALLY use memory tools during natural conversation — no explicit commands needed:

### Auto-Store (triggered by conversation context)
- **Decision made** → `memory_store(category="decision", ...)`
- **Architecture choice** → `memory_store(category="architecture", ...)`
- **User sets a rule** ("always do X", "never do Y") → `memory_store(category="mandatory_rules"/"forbidden_rules", ...)`
- **User gives feedback** ("don't do that", "keep doing this") → `memory_store(category="feedback", ...)`
- **Sprint/milestone discussed** → `memory_store(category="sprint", ...)`
- **DevOps config decided** → `memory_store(category="devops", ...)`
- **External resource mentioned** → `memory_store(category="reference", ...)`

### Auto-Search (before answering)
- When user asks about a past decision → `memory_search("...")`
- When context from previous sessions is needed → `memory_search("...")`
- When starting work that may have prior context → `memory_search("...")`

### Auto-Rules Check
- Before any significant operation → `memory_get_rules()` to ensure mandatory rules are followed and forbidden patterns are avoided

### Session Lifecycle
- At conversation start → `memory_session_start()`
- At conversation end → `memory_session_end(session_id, summary)`

## Development

```bash
uv sync --all-extras
uv run pytest -v
```

## Tech Stack
- Python + FastMCP
- DuckDB + VSS (HNSW vector search, cosine similarity)
- sentence-transformers/all-MiniLM-L6-v2 (local embeddings, 384 dimensions)
- Pydantic v2
