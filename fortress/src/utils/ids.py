"""Fortress 2.0 utility — ID generation."""

import uuid


def generate_id() -> str:
    """Return a new random UUID as a string."""
    return str(uuid.uuid4())
