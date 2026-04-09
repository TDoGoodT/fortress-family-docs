"""Document processors — pluggable extraction backends (Google + AWS only)."""
from src.services.document_processors.base_processor import BaseProcessor, ProcessorResult
from src.services.document_processors.processor_router import route_processor, process_with_best

__all__ = ["BaseProcessor", "ProcessorResult", "route_processor", "process_with_best"]
