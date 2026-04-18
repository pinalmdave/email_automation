"""
Token & cost tracker for Claude API calls.

Accumulates usage into two buckets:
  - session: resets on each new UI run (a call to reset_session())
  - total:   persisted across process restarts in usage_totals.json

Exposes record_usage(response) which accepts either a langchain_anthropic
AIMessage or a raw Anthropic SDK Message and extracts token counts.
"""

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict

from config import (
    CLAUDE_CACHE_READ_COST_PER_MTOK,
    CLAUDE_CACHE_WRITE_COST_PER_MTOK,
    CLAUDE_INPUT_COST_PER_MTOK,
    CLAUDE_OUTPUT_COST_PER_MTOK,
    USAGE_TOTALS_PATH,
)

logger = logging.getLogger(__name__)


@dataclass
class UsageBucket:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    api_calls: int = 0
    cost_usd: float = 0.0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add(self, other: "UsageBucket") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_creation_input_tokens += other.cache_creation_input_tokens
        self.cache_read_input_tokens += other.cache_read_input_tokens
        self.api_calls += other.api_calls
        self.cost_usd += other.cost_usd

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "total_tokens": (
                self.input_tokens
                + self.output_tokens
                + self.cache_creation_input_tokens
                + self.cache_read_input_tokens
            ),
            "api_calls": self.api_calls,
            "cost_usd": round(self.cost_usd, 6),
            "started_at": self.started_at,
        }


_lock = threading.Lock()
_session = UsageBucket()
_total = UsageBucket()


def _compute_cost(
    input_tokens: int,
    output_tokens: int,
    cache_write: int,
    cache_read: int,
) -> float:
    return (
        input_tokens * CLAUDE_INPUT_COST_PER_MTOK
        + output_tokens * CLAUDE_OUTPUT_COST_PER_MTOK
        + cache_write * CLAUDE_CACHE_WRITE_COST_PER_MTOK
        + cache_read * CLAUDE_CACHE_READ_COST_PER_MTOK
    ) / 1_000_000.0


def _load_totals() -> None:
    if not USAGE_TOTALS_PATH.exists():
        return
    try:
        data = json.loads(USAGE_TOTALS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    _total.input_tokens = int(data.get("input_tokens", 0))
    _total.output_tokens = int(data.get("output_tokens", 0))
    _total.cache_creation_input_tokens = int(data.get("cache_creation_input_tokens", 0))
    _total.cache_read_input_tokens = int(data.get("cache_read_input_tokens", 0))
    _total.api_calls = int(data.get("api_calls", 0))
    _total.cost_usd = float(data.get("cost_usd", 0.0))
    _total.started_at = str(data.get("started_at", _total.started_at))


def _save_totals() -> None:
    try:
        USAGE_TOTALS_PATH.write_text(
            json.dumps(_total.to_dict(), indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Could not persist usage totals: %s", exc)
        return
    try:
        from blob_storage import upload_state_file
        upload_state_file(USAGE_TOTALS_PATH)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Blob sync of usage totals skipped: %s", exc)


# Pull persisted totals from blob (if configured) before reading locally.
try:
    from blob_storage import download_state_file as _dl_state
    if not USAGE_TOTALS_PATH.exists():
        _dl_state(USAGE_TOTALS_PATH)
except Exception:  # noqa: BLE001
    pass

_load_totals()


def _extract_usage(response: Any) -> Dict[str, int]:
    """Pull token counts out of whatever shape the SDK/langchain returned."""
    usage: Dict[str, Any] = {}

    # langchain AIMessage — response_metadata has usage
    meta = getattr(response, "response_metadata", None)
    if isinstance(meta, dict):
        raw = meta.get("usage") or {}
        if isinstance(raw, dict):
            usage.update(raw)

    # langchain usage_metadata (normalized shape)
    um = getattr(response, "usage_metadata", None)
    if isinstance(um, dict):
        # keys: input_tokens, output_tokens, input_token_details
        if "input_tokens" in um and "input_tokens" not in usage:
            usage["input_tokens"] = um["input_tokens"]
        if "output_tokens" in um and "output_tokens" not in usage:
            usage["output_tokens"] = um["output_tokens"]
        details = um.get("input_token_details") or {}
        if isinstance(details, dict):
            if "cache_read" in details and "cache_read_input_tokens" not in usage:
                usage["cache_read_input_tokens"] = details["cache_read"]
            if "cache_creation" in details and "cache_creation_input_tokens" not in usage:
                usage["cache_creation_input_tokens"] = details["cache_creation"]

    # Raw Anthropic SDK Message.usage
    raw_usage = getattr(response, "usage", None)
    if raw_usage is not None and not usage:
        for key in ("input_tokens", "output_tokens",
                    "cache_creation_input_tokens", "cache_read_input_tokens"):
            val = getattr(raw_usage, key, None)
            if val is not None:
                usage[key] = val

    return {
        "input_tokens": int(usage.get("input_tokens", 0) or 0),
        "output_tokens": int(usage.get("output_tokens", 0) or 0),
        "cache_creation_input_tokens": int(usage.get("cache_creation_input_tokens", 0) or 0),
        "cache_read_input_tokens": int(usage.get("cache_read_input_tokens", 0) or 0),
    }


def record_usage(response: Any) -> Dict[str, Any]:
    """
    Parse usage off a Claude response and accumulate into session + total.
    Returns a snapshot of current usage (for progress events).
    """
    u = _extract_usage(response)
    cost = _compute_cost(
        u["input_tokens"],
        u["output_tokens"],
        u["cache_creation_input_tokens"],
        u["cache_read_input_tokens"],
    )

    with _lock:
        for bucket in (_session, _total):
            bucket.input_tokens += u["input_tokens"]
            bucket.output_tokens += u["output_tokens"]
            bucket.cache_creation_input_tokens += u["cache_creation_input_tokens"]
            bucket.cache_read_input_tokens += u["cache_read_input_tokens"]
            bucket.api_calls += 1
            bucket.cost_usd += cost
        _save_totals()
        snapshot = get_snapshot()

    logger.info(
        "Claude usage — in:%d out:%d cache_r:%d cache_w:%d  cost:$%.4f  (session $%.4f / total $%.4f)",
        u["input_tokens"], u["output_tokens"],
        u["cache_read_input_tokens"], u["cache_creation_input_tokens"],
        cost, snapshot["session"]["cost_usd"], snapshot["total"]["cost_usd"],
    )
    return snapshot


def reset_session() -> Dict[str, Any]:
    global _session
    with _lock:
        _session = UsageBucket()
        return get_snapshot()


def get_snapshot() -> Dict[str, Any]:
    with _lock:
        return {
            "session": _session.to_dict(),
            "total": _total.to_dict(),
        }
