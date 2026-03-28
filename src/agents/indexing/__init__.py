"""
Indexing module for proactive workspace indexing.

This module provides models and utilities for managing vector index
operations in the Sentinel/Worker agent pattern.
"""

from .models import (
    IndexConfig,
    IndexFreshnessResult,
    IndexingResult,
    IndexStatus,
    IndexStatusLevel,
)
from .index_manager import IndexManager

__all__ = [
    "IndexConfig",
    "IndexFreshnessResult",
    "IndexManager",
    "IndexingResult",
    "IndexStatus",
    "IndexStatusLevel",
]
