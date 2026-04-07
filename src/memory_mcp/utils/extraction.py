"""Auto-summary generation, entity extraction, and TTL calculation."""

import re
from datetime import datetime, timedelta, timezone


def generate_summary(title: str, content: str, max_words: int = 20) -> str:
    """Generate a short summary (15-20 words) from title and content."""
    # Use first sentence of content, prepend title context
    first_sentence = content.split(".")[0].strip()
    if len(first_sentence.split()) <= max_words:
        summary = first_sentence
    else:
        words = first_sentence.split()[:max_words]
        summary = " ".join(words) + "..."

    # If summary is too short, add title
    if len(summary.split()) < 5:
        summary = f"{title}: {summary}"

    return summary[:200]  # Hard cap


def extract_entities(text: str) -> list[str]:
    """Extract named entities from text using pattern matching.

    Detects: CamelCase, ACRONYMS, @mentions, #tags, quoted terms, capitalized phrases.
    """
    entities = set()

    # CamelCase words (e.g., PostgreSQL, FastMCP, DuckDB)
    for match in re.finditer(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", text):
        entities.add(match.group())

    # ACRONYMS (2+ uppercase letters, e.g., API, JWT, REST)
    for match in re.finditer(r"\b[A-Z]{2,}\b", text):
        word = match.group()
        if word not in {"THE", "AND", "FOR", "NOT", "BUT", "ARE", "WAS", "HAS", "ALL", "ANY", "CAN"}:
            entities.add(word)

    # @mentions
    for match in re.finditer(r"@(\w+)", text):
        entities.add(f"@{match.group(1)}")

    # #tags
    for match in re.finditer(r"#(\w+)", text):
        entities.add(f"#{match.group(1)}")

    # Quoted terms
    for match in re.finditer(r'"([^"]{2,30})"', text):
        entities.add(match.group(1))
    for match in re.finditer(r"'([^']{2,30})'", text):
        entities.add(match.group(1))

    # Technology/tool names (common patterns)
    tech_patterns = [
        r"\b(?:React|Vue|Angular|Next\.js|Nuxt|Svelte)\b",
        r"\b(?:PostgreSQL|MySQL|MongoDB|Redis|DuckDB|SQLite)\b",
        r"\b(?:Docker|Kubernetes|AWS|GCP|Azure|Cloudflare)\b",
        r"\b(?:Python|TypeScript|JavaScript|Rust|Go|Java)\b",
        r"\b(?:FastAPI|Django|Flask|Express|FastMCP)\b",
        r"\b(?:GitHub|GitLab|Jira|Linear|Slack|Notion)\b",
    ]
    for pattern in tech_patterns:
        for match in re.finditer(pattern, text):
            entities.add(match.group())

    return sorted(entities)


# TTL defaults per category (in days)
DEFAULT_TTL_DAYS = {
    "session": 30,
    "sprint": 90,
    "decision": 365,
    "project_plan": 365,
    "architecture": 365,
    "devops": 180,
    "mandatory_rules": None,  # Never expires
    "forbidden_rules": None,  # Never expires
    "developer_docs": 180,
    "feedback": 90,
    "reference": 365,
}

# Priority multiplier for TTL
PRIORITY_TTL_MULTIPLIER = {
    0: 1.0,
    1: 1.5,
    2: None,  # Priority 2 (rules) never expire
}


def calculate_expiry(category: str, priority: int = 0) -> datetime | None:
    """Calculate expiration timestamp based on category and priority."""
    # Rules never expire
    if priority >= 2:
        return None

    base_days = DEFAULT_TTL_DAYS.get(category)
    if base_days is None:
        return None

    multiplier = PRIORITY_TTL_MULTIPLIER.get(priority, 1.0)
    if multiplier is None:
        return None

    total_days = int(base_days * multiplier)
    return datetime.now(timezone.utc) + timedelta(days=total_days)


def estimate_tokens(text: str) -> int:
    """Rough token estimation (~4 chars per token)."""
    return max(1, len(text) // 4)
