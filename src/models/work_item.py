"""
Work Item models for the Sentinel Orchestrator.

This module defines the core data models for work items that flow through
the orchestration system. All models use Pydantic v2 for validation.
"""

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# Story 6: Credential Scrubbing Integration
# Secret patterns that must be scrubbed from all output
# IMPORTANT: Order matters! More specific patterns must come BEFORE generic patterns
SECRET_PATTERNS = [
    # Private keys (PEM format) - must be first to match multiline
    (
        r"-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----",
        "[PRIVATE_KEY_REDACTED]",
    ),
    # GitHub tokens (real PATs are 36 alphanumeric chars after prefix)
    (r"ghp_[A-Za-z0-9_]{36,}", "ghp_[REDACTED]"),
    (r"ghs_[A-Za-z0-9_]{36,}", "ghs_[REDACTED]"),
    (r"gho_[A-Za-z0-9_]{36,}", "gho_[REDACTED]"),
    (r"github_pat_[A-Za-z0-9_]{22,}", "github_pat_[REDACTED]"),
    # OpenAI keys
    (r"sk-proj-[A-Za-z0-9]{20,}", "sk-proj-[REDACTED]"),
    (r"sk-[A-Za-z0-9]{20,}", "sk-[REDACTED]"),
    # ZhipuAI keys (JWT-like format)
    (r"[A-Za-z0-9]{32,}\.[A-Za-z0-9]{32,}\.[A-Za-z0-9]{32,}", "[ZHIPU_KEY_REDACTED]"),
    # Google/Gemini keys
    (r"AIza[A-Za-z0-9_-]{35}", "AIza[REDACTED]"),
    # AWS keys
    (r"AKIA[A-Z0-9]{16}", "AKIA[REDACTED]"),
    (
        r"aws_secret_access_key\s*=\s*[A-Za-z0-9/+=]{40}",
        "aws_secret_access_key=[REDACTED]",
    ),
    # Generic Bearer tokens
    (r"Bearer\s+[A-Za-z0-9._-]{20,}", "Bearer [REDACTED]"),
    # Generic token patterns - these are catch-alls, must be last
    (r"token['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9._-]{20,}['\"]?", "token=[REDACTED]"),
    (r"api_key['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9._-]{20,}['\"]?", "api_key=[REDACTED]"),
]


def scrub_secrets(text: str | None) -> str | None:
    """
    Remove sensitive credentials and secrets from text.

    This function must be applied to ALL content before posting to GitHub
    (comments, logs, error messages, etc.) to prevent credential leaks.

    Args:
        text: The text to scrub.

    Returns:
        The text with all detected secrets replaced with redacted placeholders.

    Example:
        >>> scrub_secrets("Using token ghp_abc123xyz...")
        'Using token ghp_[REDACTED]...'
    """
    if not text:
        return text

    scrubbed = text
    for pattern, replacement in SECRET_PATTERNS:
        scrubbed = re.sub(pattern, replacement, scrubbed, flags=re.IGNORECASE)

    return scrubbed


class TaskType(str, Enum):
    """Type of task to be performed on a work item."""

    PLAN = "PLAN"
    """Plan mode - analyze and create implementation plan."""

    IMPLEMENT = "IMPLEMENT"
    """Implement mode - execute the implementation."""

    BUG = "BUG"
    """Bug report - issue describing a defect or problem."""

    FEATURE = "FEATURE"
    """Feature request - new functionality or enhancement."""

    ENHANCEMENT = "ENHANCEMENT"
    """Enhancement - improvement to existing functionality."""

    GENERIC = "GENERIC"
    """Generic issue - no specific template detected."""


class WorkItemStatus(str, Enum):
    """
    Status of a work item in the orchestration pipeline.

    These statuses map to GitHub labels used for workflow tracking.
    """

    QUEUED = "queued"
    """Item is queued and waiting to be processed."""

    IN_PROGRESS = "in-progress"
    """Item is currently being processed by an agent."""

    SUCCESS = "success"
    """Item was processed successfully."""

    ERROR = "error"
    """Item processing failed with an error."""

    STALLED_BUDGET = "stalled-budget"
    """Agent stalled due to budget/token limits."""

    INFRA_FAILURE = "infra-failure"
    """Agent infrastructure failure (timeout, OOM, etc.)."""


class WorkItem(BaseModel):
    """
    A unified work item representation for the Sentinel Orchestrator.

    This model decouples the orchestrator logic from specific providers
    (GitHub, Linear, etc.) by providing a standardized interface for
    work items regardless of their source.

    Attributes:
        id: Unique identifier for the work item (string or int from source).
        source_url: URL to the original work item in the source system.
        context_body: The main content/context of the work item.
        target_repo_slug: Target repository in "owner/repo" format.
        task_type: Type of task (PLAN or IMPLEMENT).
        status: Current status of the work item.
        metadata: Provider-specific information (e.g., issue_node_id for GitHub).
    """

    id: str | int = Field(
        ...,
        description="Unique identifier for the work item",
    )
    source_url: str = Field(
        ...,
        description="URL to the original work item in the source system",
    )
    context_body: str = Field(
        ...,
        description="The main content/context of the work item",
    )
    target_repo_slug: str = Field(
        ...,
        description="Target repository in 'owner/repo' format",
        pattern=r"^[^/]+/[^/]+$",
    )
    task_type: TaskType = Field(
        ...,
        description="Type of task (PLAN or IMPLEMENT)",
    )
    status: WorkItemStatus = Field(
        default=WorkItemStatus.QUEUED,
        description="Current status of the work item",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific information (e.g., issue_node_id for GitHub)",
    )

    model_config = {
        "frozen": False,
        "extra": "forbid",
        "str_strip_whitespace": True,
        "validate_assignment": True,
    }
