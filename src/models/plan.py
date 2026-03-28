"""
Plan and Epic models for the Architect Agent.

This module defines Pydantic models for Application Plans and Epics
that are used by the Architect agent for plan decomposition.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PlanStatus(str, Enum):
    """Status of a Plan in the decomposition pipeline."""

    DRAFT = "draft"
    """Plan is being drafted."""

    READY = "ready"
    """Plan is ready for decomposition."""

    IN_PROGRESS = "in-progress"
    """Plan is being decomposed into Epics."""

    COMPLETE = "complete"
    """Plan has been fully decomposed."""

    ERROR = "error"
    """Error occurred during decomposition."""


class EpicPriority(str, Enum):
    """Priority level for an Epic."""

    CRITICAL = "critical"
    """Must be completed first - blocks other work."""

    HIGH = "high"
    """Important - should be prioritized."""

    MEDIUM = "medium"
    """Normal priority."""

    LOW = "low"
    """Can be deferred if needed."""


class EpicDependency(BaseModel):
    """Represents a dependency between Epics."""

    epic_id: str = Field(
        ...,
        description="Identifier of the Epic this dependency refers to",
    )
    dependency_type: str = Field(
        default="blocks",
        description="Type of dependency: 'blocks', 'relates_to', 'requires'",
    )
    description: str | None = Field(
        default=None,
        description="Optional description of why this dependency exists",
    )


class AcceptanceCriterion(BaseModel):
    """A single acceptance criterion for an Epic or Plan."""

    id: str = Field(
        ...,
        description="Unique identifier for this criterion",
    )
    description: str = Field(
        ...,
        description="Description of what must be achieved",
    )
    verified: bool = Field(
        default=False,
        description="Whether this criterion has been verified",
    )


class WorkItem(BaseModel):
    """A work item extracted from a Plan or Epic."""

    id: str = Field(
        ...,
        description="Unique identifier for this work item",
    )
    title: str = Field(
        ...,
        description="Short title of the work item",
    )
    description: str | None = Field(
        default=None,
        description="Detailed description of the work item",
    )
    completed: bool = Field(
        default=False,
        description="Whether this work item is completed",
    )


class Epic(BaseModel):
    """
    Represents an Epic issue to be created from a Plan.

    An Epic is a large body of work that can be broken down into
    smaller stories or tasks. It represents a significant feature
    or component of the overall project.
    """

    id: str = Field(
        ...,
        description="Unique identifier for this Epic (e.g., 'epic-1', 'auth')",
    )
    title: str = Field(
        ...,
        description="Title of the Epic",
    )
    overview: str = Field(
        ...,
        description="Brief overview of what this Epic accomplishes",
    )
    component: str | None = Field(
        default=None,
        description="Technical component this Epic belongs to",
    )
    goals: list[str] = Field(
        default_factory=list,
        description="List of goals for this Epic",
    )
    work_items: list[WorkItem] = Field(
        default_factory=list,
        description="List of work items/tasks for this Epic",
    )
    acceptance_criteria: list[AcceptanceCriterion] = Field(
        default_factory=list,
        description="Acceptance criteria for this Epic",
    )
    dependencies: list[EpicDependency] = Field(
        default_factory=list,
        description="Dependencies on other Epics",
    )
    priority: EpicPriority = Field(
        default=EpicPriority.MEDIUM,
        description="Priority level of this Epic",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )

    @property
    def is_blocked(self) -> bool:
        """Check if this Epic has any blocking dependencies."""
        return any(dep.dependency_type == "blocks" for dep in self.dependencies)

    @property
    def dependency_ids(self) -> list[str]:
        """Get list of Epic IDs this Epic depends on."""
        return [dep.epic_id for dep in self.dependencies]


class Plan(BaseModel):
    """
    Represents an Application Plan to be decomposed into Epics.

    A Plan is a high-level document describing a feature, project,
    or significant change. The Architect agent analyzes Plans and
    generates Epic issues from them.
    """

    id: str = Field(
        ...,
        description="Unique identifier for this Plan (e.g., issue number)",
    )
    title: str = Field(
        ...,
        description="Title of the Plan",
    )
    source_url: str | None = Field(
        default=None,
        description="URL to the original Plan issue",
    )
    overview: str | None = Field(
        default=None,
        description="Overview/summary of the Plan",
    )
    goals: list[str] = Field(
        default_factory=list,
        description="List of goals for this Plan",
    )
    technology_stack: list[str] = Field(
        default_factory=list,
        description="Technologies mentioned in the Plan",
    )
    epics: list[Epic] = Field(
        default_factory=list,
        description="Generated Epics from this Plan",
    )
    acceptance_criteria: list[AcceptanceCriterion] = Field(
        default_factory=list,
        description="Acceptance criteria for this Plan",
    )
    raw_content: str | None = Field(
        default=None,
        description="Original markdown content of the Plan",
    )
    status: PlanStatus = Field(
        default=PlanStatus.DRAFT,
        description="Current status of the Plan",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )

    def add_epic(self, epic: Epic) -> None:
        """Add an Epic to this Plan."""
        self.epics.append(epic)

    def get_epic(self, epic_id: str) -> Epic | None:
        """Get an Epic by its ID."""
        for epic in self.epics:
            if epic.id == epic_id:
                return epic
        return None

    @property
    def epic_count(self) -> int:
        """Get the number of Epics in this Plan."""
        return len(self.epics)


class ParsedSection(BaseModel):
    """Represents a parsed section from a markdown document."""

    heading: str = Field(
        ...,
        description="The heading text (without # prefix)",
    )
    level: int = Field(
        ...,
        description="Heading level (1-6)",
    )
    content: str = Field(
        default="",
        description="Content under this heading",
    )
    subsections: list["ParsedSection"] = Field(
        default_factory=list,
        description="Nested subsections",
    )


# Update forward reference
ParsedSection.model_rebuild()
