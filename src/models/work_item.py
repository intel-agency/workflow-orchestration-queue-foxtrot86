"""
Work Item models for the Sentinel Orchestrator.

This module defines the core data models for work items that flow through
the orchestration system. All models use Pydantic v2 for validation.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """Type of task to be performed on a work item."""

    PLAN = "PLAN"
    """Plan mode - analyze and create implementation plan."""

    IMPLEMENT = "IMPLEMENT"
    """Implement mode - execute the implementation."""


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
