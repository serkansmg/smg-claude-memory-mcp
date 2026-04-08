"""Database schema creation and migration for per-project DuckDB files."""

import duckdb

CURRENT_SCHEMA_VERSION = 2


def install_vss(conn: duckdb.DuckDBPyConnection) -> None:
    """Install and load the VSS extension."""
    conn.execute("INSTALL vss;")
    conn.execute("LOAD vss;")
    conn.execute("SET hnsw_enable_experimental_persistence = true;")


def create_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the full schema for a project database."""
    install_vss(conn)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id              VARCHAR PRIMARY KEY,
            category        VARCHAR NOT NULL,
            title           VARCHAR NOT NULL,
            content         VARCHAR NOT NULL,
            summary         VARCHAR,
            tags            VARCHAR[],
            metadata        JSON,
            embedding       FLOAT[384],
            status          VARCHAR DEFAULT 'active',
            priority        INTEGER DEFAULT 0,
            source          VARCHAR,
            related_ids     VARCHAR[],
            entities        VARCHAR[],
            access_count    INTEGER DEFAULT 0,
            expires_at      TIMESTAMP,
            created_at      TIMESTAMP DEFAULT current_timestamp,
            updated_at      TIMESTAMP DEFAULT current_timestamp
        )
    """)

    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_provenance_id START 1;
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS provenance (
            id              INTEGER PRIMARY KEY DEFAULT nextval('seq_provenance_id'),
            memory_id       VARCHAR NOT NULL,
            operation       VARCHAR NOT NULL,
            details         JSON,
            created_at      TIMESTAMP DEFAULT current_timestamp
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id                VARCHAR PRIMARY KEY,
            started_at        TIMESTAMP NOT NULL,
            ended_at          TIMESTAMP,
            summary           VARCHAR,
            memories_created  INTEGER DEFAULT 0,
            memories_accessed INTEGER DEFAULT 0,
            metadata          JSON
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version    INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT current_timestamp
        )
    """)

    # Indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_category ON memories (category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_status ON memories (status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_created ON memories (created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_expires ON memories (expires_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_provenance_memory ON provenance (memory_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_provenance_op ON provenance (operation)")

    # Record schema version
    conn.execute(
        "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
        [CURRENT_SCHEMA_VERSION],
    )


def migrate_v1_to_v2(conn: duckdb.DuckDBPyConnection) -> None:
    """Migrate from schema v1 to v2: add summary, entities, expires_at, provenance."""
    try:
        conn.execute("ALTER TABLE memories ADD COLUMN summary VARCHAR")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE memories ADD COLUMN entities VARCHAR[]")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE memories ADD COLUMN expires_at TIMESTAMP")
    except Exception:
        pass
    try:
        conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_provenance_id START 1;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS provenance (
                id              INTEGER PRIMARY KEY DEFAULT nextval('seq_provenance_id'),
                memory_id       VARCHAR NOT NULL,
                operation       VARCHAR NOT NULL,
                details         JSON,
                created_at      TIMESTAMP DEFAULT current_timestamp
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_provenance_memory ON provenance (memory_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_provenance_op ON provenance (operation)")
    except Exception:
        pass
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_expires ON memories (expires_at)")
    conn.execute(
        "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
        [CURRENT_SCHEMA_VERSION],
    )


def create_hnsw_index(conn: duckdb.DuckDBPyConnection) -> None:
    """Create or recreate HNSW vector index with cosine metric."""
    try:
        # Check if index exists
        indexes = conn.execute(
            "SELECT index_name FROM duckdb_indexes() WHERE table_name = 'memories' AND index_name = 'idx_memories_embedding'"
        ).fetchall()

        if indexes:
            # Drop and recreate to ensure correct metric
            conn.execute("DROP INDEX IF EXISTS idx_memories_embedding")

        # Check if there are any rows with embeddings
        count = conn.execute("SELECT COUNT(*) FROM memories WHERE embedding IS NOT NULL").fetchone()[0]
        if count > 0:
            conn.execute("""
                CREATE INDEX idx_memories_embedding
                ON memories USING HNSW (embedding)
                WITH (metric = 'cosine')
            """)
    except Exception:
        # HNSW index is optional - search works without it (brute force)
        pass


def create_registry_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the registry database schema."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            slug            VARCHAR PRIMARY KEY,
            display_name    VARCHAR NOT NULL,
            description     VARCHAR,
            created_at      TIMESTAMP DEFAULT current_timestamp,
            last_accessed   TIMESTAMP DEFAULT current_timestamp,
            db_path         VARCHAR NOT NULL
        )
    """)
