"""
Data models for the Architect Sub-Agent.

This module defines Pydantic models for Plans, Epics, and Dependencies
used in the plan decomposition process.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PlanSection(str, Enum):
    """Sections that can be extracted from an Application Plan."""

    OVERVIEW = "overview"
    GOALS = "goals"
    SCOPE = "scope"
    TECHNICAL_REQUIREMENTS = "technical_requirements"
    USER_STORIES = "user_stories"
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    IMPLEMENTATION_PLAN = "implementation_plan"
    RISKS = "risks"
    TIMELINE = "timeline"
    UNKNOWN = "unknown"


class EpicStatus(str, Enum):
    """Status of an Epic in the decomposition pipeline."""

    DRAFT = "draft"
    """Epic is being generated."""

    READY = "ready"
    """Epic is ready to be created as a GitHub issue."""

    CREATED = "created"
    """Epic has been created as a GitHub issue."""

    BLOCKED = "blocked"
    """Epic is blocked by dependencies."""

    ERROR = "error"
    """Error occurred during Epic processing."""


class DependencyType(str, Enum):
    """Type of dependency between Epics."""

    BLOCKS = "blocks"
    """This epic blocks another epic."""

    BLOCKED_BY = "blocked_by"
    """This epic is blocked by another epic."""

    RELATED_TO = "related_to"
    """Epics are related but not blocking."""

    PART_OF = "part_of"
    """This epic is part of a larger epic."""


class Dependency(BaseModel):
    """
    Represents a dependency relationship between Epics.

    Attributes:
        source_epic_id: ID of the epic that has the dependency.
        target_epic_id: ID of the epic that is depended upon.
        dependency_type: Type of the dependency relationship.
        description: Human-readable description of the dependency.
    """

    source_epic_id: str = Field(
        ...,
        description="ID of the epic that has the dependency",
    )
    target_epic_id: str = Field(
        ...,
        description="ID of the epic that is depended upon",
    )
    dependency_type: DependencyType = Field(
        ...,
        description="Type of the dependency relationship",
    )
    description: str | None = Field(
        default=None,
        description="Human-readable description of the dependency",
    )

    model_config = {
        "frozen": False,
        "extra": "forbid",
    }


class Epic(BaseModel):
    """
    Represents a single Epic derived from an Application Plan.

    An Epic is a high-level work item that can be broken down into
    smaller stories/tasks.

    Attributes:
        id: Unique identifier for the epic (e.g., "epic-1", "epic-2").
        title: Human-readable title for the epic.
        description: Detailed description of the epic.
        acceptance_criteria: List of acceptance criteria for the epic.
        dependencies: List of epic IDs this epic depends on.
        priority: Priority level (1 = highest).
        labels: GitHub labels to apply to the epic issue.
        status: Current status of the epic.
        estimated_effort: Estimated effort (e.g., "1 week", "2-3 days").
        metadata: Additional metadata for the epic.
    """

    id: str = Field(
        ...,
        description="Unique identifier for the epic",
        pattern=r"^epic-\d+$",
    )
    title: str = Field(
        ...,
        description="Human-readable title for the epic",
        min_length=5,
        max_length=255,
    )
    description: str = Field(
        ...,
        description="Detailed description of the epic",
        min_length=10,
    )
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="List of acceptance criteria for the epic",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="List of epic IDs this epic depends on",
    )
    priority: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Priority level (1 = highest)",
    )
    labels: list[str] = Field(
        default_factory=lambda: ["epic", "implementation:ready"],
        description="GitHub labels to apply to the epic issue",
    )
    status: EpicStatus = Field(
        default=EpicStatus.DRAFT,
        description="Current status of the epic",
    )
    estimated_effort: str | None = Field(
        default=None,
        description="Estimated effort (e.g., '1 week', '2-3 days')",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for the epic",
    )

    model_config = {
        "frozen": False,
        "extra": "forbid",
        "str_strip_whitespace": True,
    }


class ParsedPlan(BaseModel):
    """
    Represents a parsed Application Plan.

    This model captures the structured content extracted from an
    Application Plan markdown document.

    Attributes:
        source_issue_number: GitHub issue number of the source plan.
        source_issue_url: URL to the source plan issue.
        title: Title of the application plan.
        overview: High-level overview of the plan.
        goals: List of goals/objectives.
        scope: Scope definition (in-scope and out-of-scope items).
        technical_requirements: Technical requirements and constraints.
        user_stories: User stories or use cases.
        acceptance_criteria: Overall acceptance criteria.
        implementation_sections: Implementation plan sections.
        risks: Identified risks and mitigations.
        timeline: Timeline or milestone information.
        raw_content: Original markdown content.
    """

    source_issue_number: int = Field(
        ...,
        description="GitHub issue number of the source plan",
    )
    source_issue_url: str = Field(
        ...,
        description="URL to the source plan issue",
    )
    title: str = Field(
        ...,
        description="Title of the application plan",
    )
    overview: str | None = Field(
        default=None,
        description="High-level overview of the plan",
    )
    goals: list[str] = Field(
        default_factory=list,
        description="List of goals/objectives",
    )
    scope: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Scope definition (in_scope, out_of_scope)",
    )
    technical_requirements: list[str] = Field(
        default_factory=list,
        description="Technical requirements and constraints",
    )
    user_stories: list[str] = Field(
        default_factory=list,
        description="User stories or use cases",
    )
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="Overall acceptance criteria",
    )
    implementation_sections: dict[str, str] = Field(
        default_factory=dict,
        description="Implementation plan sections",
    )
    risks: list[dict[str, str]] = Field(
        default_factory=list,
        description="Identified risks and mitigations",
    )
    timeline: str | None = Field(
        default=None,
        description="Timeline or milestone information",
    )
    raw_content: str = Field(
        default="",
        description="Original markdown content",
    )

    model_config = {
        "frozen": False,
        "extra": "forbid",
    }
