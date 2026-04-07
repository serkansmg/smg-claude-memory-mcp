"""Text preprocessing and validation utilities."""

import re


def slugify(text: str) -> str:
    """Convert text to a valid slug (lowercase, alphanumeric, hyphens)."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def validate_slug(slug: str) -> bool:
    """Check if a string is a valid project slug."""
    return bool(re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", slug)) or bool(
        re.match(r"^[a-z0-9]$", slug)
    )


def prepare_embedding_text(title: str, content: str) -> str:
    """Combine title and content for embedding generation."""
    return f"{title}\n{content}"
