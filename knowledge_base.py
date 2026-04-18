"""
Knowledge base loader.

Concatenates all markdown files under config.KNOWLEDGE_DIR (sorted by name)
into a single string, cached in memory for the process lifetime. The result
is injected into LLM system prompts and marked with Anthropic's ephemeral
cache_control so the cached block costs ~10% of normal input rate after
the first call per 5-minute window.
"""

import logging
from functools import lru_cache
from typing import List

from config import KNOWLEDGE_DIR

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_knowledge() -> str:
    """Return the concatenated knowledge base, or '' if the dir is missing/empty."""
    if not KNOWLEDGE_DIR.exists() or not KNOWLEDGE_DIR.is_dir():
        logger.info("No knowledge/ directory — skipping knowledge injection")
        return ""

    chunks: List[str] = []
    for md in sorted(KNOWLEDGE_DIR.glob("*.md")):
        try:
            body = md.read_text(encoding="utf-8").strip()
        except OSError as exc:
            logger.warning("Could not read %s: %s", md, exc)
            continue
        if not body:
            continue
        chunks.append(f"<!-- SOURCE: {md.name} -->\n{body}")

    if not chunks:
        return ""

    joined = "\n\n---\n\n".join(chunks)
    logger.info("Loaded knowledge base: %d file(s), %d chars", len(chunks), len(joined))
    return joined


def system_prompt_with_knowledge(base_prompt: str) -> str:
    """Prepend the knowledge base (if any) to a base system prompt, wrapped in tags."""
    kb = load_knowledge()
    if not kb:
        return base_prompt
    return (
        "<knowledge>\n"
        f"{kb}\n"
        "</knowledge>\n\n"
        f"{base_prompt}"
    )
