"""Simple in-memory rate limiter for webhook protection."""

import time
from collections import defaultdict

# phone -> list of timestamps
_request_log: dict[str, list[float]] = defaultdict(list)

WINDOW_SECONDS = 60
MAX_REQUESTS = 20  # max messages per minute per phone


def is_rate_limited(phone: str) -> bool:
    """Return True if this phone has exceeded the rate limit."""
    now = time.monotonic()
    cutoff = now - WINDOW_SECONDS
    timestamps = _request_log[phone]

    # Drop old entries
    _request_log[phone] = [t for t in timestamps if t > cutoff]
    _request_log[phone].append(now)

    return len(_request_log[phone]) > MAX_REQUESTS
