# SMG Claude Memory MCP

Production-grade vector memory server for Claude Code. Per-project semantic search, rules enforcement, session management, and team collaboration — powered by DuckDB + sentence-transformers.

## Why?

Claude Code's built-in memory (MEMORY.md + flat files) has limitations:
- **No semantic search** — can't find "which database did we choose?" unless you used the exact keyword
- **Context window pressure** — large memory files eat into your context
- **No project isolation** — memories from different projects can mix
- **No rules enforcement** — mandatory/forbidden rules aren't guaranteed to be loaded
- **No team sharing** — memories are local to one machine

This MCP server solves all of these with a vector database approach.

## Features

| Feature | Description |
|---------|-------------|
| **Semantic Search** | HNSW-accelerated cosine similarity — find memories by meaning, not keywords |
| **Per-Project Isolation** | Each project gets its own DuckDB database |
| **11 Memory Categories** | decisions, sessions, sprints, architecture, rules, devops, and more |
| **Rules Enforcement** | Mandatory/forbidden rules with cached direct SQL retrieval |
| **Session Management** | Auto-loads context (rules, sprint goals, recent decisions) at session start |
| **Auto-Summary** | 15-20 word summary generated for every memory |
| **Entity Extraction** | Automatic detection of tech names, @mentions, #tags, acronyms |
| **TTL/Expiration** | Category-based automatic expiration (rules never expire) |
| **Provenance Tracking** | Full audit trail for every memory operation |
| **Token Budgeting** | Dual-phase search responses to control context usage |
| **Portable DB** | Move DB into project directory, share via git |
| **Export/Import** | Human-readable .md export for non-MCP users |
| **Active Project** | Set once, use everywhere — no need to repeat project slug |
| **CWD Detection** | Auto-detects project from current working directory |
| **Local Embeddings** | all-MiniLM-L6-v2 (384-dim, ~80MB, runs on CPU) |
| **Zero Cloud Deps** | No API keys, no cloud services, fully local |

## Quick Install

```bash
git clone https://github.com/serkansmg/smg-claude-memory-mcp.git
cd smg-claude-memory-mcp
chmod +x install.sh
./install.sh
```

This will:
1. Install `uv` if not present
2. Install all Python dependencies in an isolated venv (no system pollution)
3. Download the embedding model (~80MB, one-time)
4. Configure Claude Code MCP automatically

Then restart Claude Code.

## Manual Install

```bash
# Install dependencies
uv sync

# Run setup
uv run memory-mcp-setup
```

Or add to Claude Code manually (`.mcp.json` or `~/.claude.json`):

```json
{
  "mcpServers": {
    "memory": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/smg-claude-memory-mcp", "memory-mcp"]
    }
  }
}
```

## Quick Start

```
# 1. Create a project (one-time)
/smg-memory init my-app "My Application"

# 2. Start a session (beginning of each conversation)
/smg-memory start

# 3. Store memories (or let Claude auto-detect from conversation)
/smg-memory store decision "Use PostgreSQL" "Chose PostgreSQL for JSON support"
/smg-memory store mandatory_rules "Always Test" "Run pytest before every commit"

# 4. Search
/smg-memory search "database choice"

# 5. End session
/smg-memory end "Implemented auth module, chose JWT tokens"
```

## Usage

### Project Management

```bash
# Create new project (auto-activates)
/smg-memory init my-app "My Application"

# Attach existing project directory
/smg-memory attach /path/to/my-app

# Set active project (no need to pass project= to every command)
/smg-memory use my-app

# List all projects
/smg-memory projects
```

### Session Lifecycle

```bash
# Start session — loads rules, last session summary, sprint goals, recent decisions
/smg-memory start

# End session with summary
/smg-memory end "Completed user auth, decided on JWT, next: API rate limiting"
```

### Memory Operations

```bash
# Store (project is optional — uses active project)
/smg-memory store decision "Redis for Cache" "Using Redis for session and API response caching"
/smg-memory store architecture "Event-Driven" "Adopted event-driven architecture with RabbitMQ"
/smg-memory store mandatory_rules "PR Reviews" "All PRs require at least one review"

# Semantic search
/smg-memory search "caching strategy"
/smg-memory search "deployment pipeline"

# List by category
/smg-memory list decisions
/smg-memory list mandatory_rules

# Get rules
/smg-memory rules

# View change history
/smg-memory history <memory-id>
```

### Team Collaboration

#### Option A: Share via Git (portable DB)

```bash
# Developer 1: Move DB to project directory
/smg-memory portable /path/to/project
# Add to .gitignore: *.duckdb.wal
git add .memory-mcp.duckdb
git commit -m "add project memory"
git push

# Developer 2: After git pull
/smg-memory sync /path/to/project
# Ready! All memories from Developer 1 are available
```

#### Option B: Export for non-MCP users

```bash
# Export to human-readable .md files
/smg-memory export /path/to/project

# Creates:
# .memory/
#   MEMORY_INDEX.md          <- Master index
#   README.md                <- Format docs
#   decision/
#     use-postgresql.md      <- Individual memories
#   mandatory_rules/
#     always-test.md
#   architecture/
#     event-driven.md

# Non-MCP users can read and edit these files directly

# Import changes back
/smg-memory import /path/to/project
```

### Automatic Memory (No Commands Needed)

When a session is active, Claude automatically:
- **Stores decisions** when you make architectural or technical choices
- **Stores rules** when you say "always do X" or "never do Y"
- **Searches memory** when you ask about past decisions
- **Checks rules** before significant operations

## Memory Categories

| Category | Description | TTL |
|----------|-------------|-----|
| `decision` | Important decisions and rationale | 365 days |
| `session` | Session summaries | 30 days |
| `sprint` | Sprint goals, progress, retrospectives | 90 days |
| `project_plan` | Project plans and milestones | 365 days |
| `architecture` | Architecture decisions and patterns | 365 days |
| `devops` | DevOps configs, deployment notes | 180 days |
| `mandatory_rules` | Rules that MUST be followed | **Never expires** |
| `forbidden_rules` | Operations that are FORBIDDEN | **Never expires** |
| `developer_docs` | Developer documentation | 180 days |
| `feedback` | User feedback on assistant behavior | 90 days |
| `reference` | Pointers to external resources | 365 days |

## MCP Tools Reference

| Tool | Description |
|------|-------------|
| `memory_use` | Set active project (no more repeating slug) |
| `memory_init_project` | Create new project namespace |
| `memory_attach_project` | Attach existing project directory |
| `memory_store` | Store memory with auto-embedding, summary, entities, TTL |
| `memory_search` | Semantic search with relevance scoring + token budgeting |
| `memory_recall` | Get memory by ID or exact title |
| `memory_update` | Partial update (re-embeds if content changes) |
| `memory_delete` | Soft or hard delete with provenance |
| `memory_list` | Filtered listing with pagination |
| `memory_provenance` | Full audit trail for a memory |
| `memory_get_rules` | Get all rules (cached, direct SQL) |
| `memory_session_start` | Start session, load full context |
| `memory_session_end` | End session, store summary |
| `memory_make_portable` | Move DB to project dir for git sharing |
| `memory_sync` | Register portable DB after git pull |
| `memory_export` | Export to .md files for non-MCP users |
| `memory_import` | Import from .md files |
| `memory_list_projects` | List all projects |
| `memory_project_info` | Get project details |

## Architecture

```
~/.memory-mcp/
  registry.duckdb              # Project registry
  projects/
    my-app.duckdb              # Per-project vector DB
    api-backend.duckdb
  backups/

# Or portable (in project dir):
my-app/
  .memory-mcp.duckdb           # Shared via git
  .memory/                     # Exported .md files (optional)
```

**Stack**: FastMCP + DuckDB (VSS/HNSW) + sentence-transformers (all-MiniLM-L6-v2)

## Requirements

- Python 3.11+
- macOS or Linux (Apple Silicon fully supported)
- ~80MB disk for the embedding model
- ~90MB RAM for the model (loaded on first use)

## Development

```bash
uv sync --all-extras
uv run pytest -v
```

## License

MIT
