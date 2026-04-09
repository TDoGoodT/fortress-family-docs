"""Base class for document processors."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProcessorResult:
    """Unified result from any document processor."""

    raw_text: str = ""
    structured_data: dict[str, Any] = field(default_factory=dict)
    tables: list[list[list[str]]] = field(default_factory=list)
    confidence: float = 0.0
    processor_name: str = ""
    extraction_method: str = ""
    page_count: int = 0
    language_detected: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_text(self) -> bool:
        return bool(self.raw_text and self.raw_text.strip())

    @property
    def has_tables(self) -> bool:
        return bool(self.tables)

    @property
    def has_structured_data(self) -> bool:
        return bool(self.structured_data)


class BaseProcessor(ABC):
    """Abstract base for document processors."""

    name: str = "base"

    @abstractmethod
    async def process(self, file_path: str, mime_type: str = "") -> ProcessorResult:
        """Process a document and return structured result."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this processor is configured and available."""
        ...
