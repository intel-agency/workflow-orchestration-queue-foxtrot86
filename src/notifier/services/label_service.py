"""
Template-to-Label Mapping Service for Intelligent Template Triaging.

This module provides functionality to map detected template types to
GitHub labels for automatic issue triaging.

Story 2.2.2: Template-to-Label Mapping Service
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings

from src.models import TaskType

logger = logging.getLogger(__name__)


# Default label mappings from TaskType to GitHub labels
DEFAULT_LABEL_MAPPINGS: dict[TaskType, list[str]] = {
    TaskType.PLAN: ["agent:queued", "orchestration:dispatch"],
    TaskType.BUG: ["agent:queued", "bug"],
    TaskType.FEATURE: ["agent:queued", "enhancement"],
    TaskType.ENHANCEMENT: ["agent:queued", "enhancement"],
    TaskType.IMPLEMENT: ["agent:queued"],
    TaskType.GENERIC: ["agent:queued"],
}


class LabelMappingSettings(BaseSettings):
    """
    Settings for label mapping configuration.

    Supports environment-based customization of label mappings.

    Environment Variables:
        LABEL_MAPPINGS: JSON string with custom label mappings
                       Format: {"PLAN": ["label1", "label2"], ...}
        ENABLE_AUTO_TRIAGE: Enable/disable automatic triaging (default: true)
    """

    # JSON string for custom label mappings
    label_mappings: str = ""

    # Feature flag for auto-triage
    enable_auto_triage: bool = True

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


@dataclass
class TriageResult:
    """
    Result of triaging an issue.

    Attributes:
        detected_type: The detected TaskType from parsing.
        labels_to_apply: List of GitHub labels to apply.
        already_present: Labels that were already on the issue.
        skipped: Whether triaging was skipped (already has agent labels).
        reason: Reason for the triage decision.
    """

    detected_type: TaskType
    labels_to_apply: list[str] = field(default_factory=list)
    already_present: list[str] = field(default_factory=list)
    skipped: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "detected_type": self.detected_type.value,
            "labels_to_apply": self.labels_to_apply,
            "already_present": self.already_present,
            "skipped": self.skipped,
            "reason": self.reason,
        }


class TemplateLabelMapper:
    """
    Maps detected template types to GitHub labels.

    This class provides configurable mappings from TaskType enum values
    to lists of GitHub label names. It supports:
    - Default mappings for all template types
    - Custom mappings via environment variables
    - Runtime configuration updates
    - Checking if triaging should be skipped

    Example:
        ```python
        mapper = TemplateLabelMapper()
        result = mapper.triage_issue(
            detected_type=TaskType.BUG,
            existing_labels=["priority:high"]
        )
        print(result.labels_to_apply)  # ["agent:queued", "bug"]
        ```
    """

    # Prefixes that indicate an agent label is already present
    AGENT_LABEL_PREFIXES = ["agent:", "orchestration:", "implementation:"]

    def __init__(
        self,
        custom_mappings: dict[TaskType, list[str]] | None = None,
        settings: LabelMappingSettings | None = None,
    ):
        """
        Initialize the Template Label Mapper.

        Args:
            custom_mappings: Optional custom label mappings to override defaults.
            settings: Optional settings instance. If not provided, creates default.
        """
        self._settings = settings or LabelMappingSettings()
        self._mappings = self._build_mappings(custom_mappings)

        logger.info(
            f"TemplateLabelMapper initialized with {len(self._mappings)} mappings, "
            f"auto_triage={'enabled' if self._settings.enable_auto_triage else 'disabled'}"
        )

    def _build_mappings(
        self,
        custom_mappings: dict[TaskType, list[str]] | None = None,
    ) -> dict[TaskType, list[str]]:
        """
        Build the label mappings from defaults, env vars, and custom mappings.

        Priority (highest to lowest):
        1. Custom mappings passed to constructor
        2. Environment variable LABEL_MAPPINGS
        3. Default mappings

        Args:
            custom_mappings: Custom mappings from constructor.

        Returns:
            Complete mapping dictionary.
        """
        # Start with defaults
        mappings = dict(DEFAULT_LABEL_MAPPINGS)

        # Apply environment variable mappings
        if self._settings.label_mappings:
            try:
                env_mappings = json.loads(self._settings.label_mappings)
                for key, labels in env_mappings.items():
                    try:
                        task_type = TaskType(key.upper())
                        mappings[task_type] = labels
                        logger.debug(
                            f"Applied env mapping: {task_type.value} -> {labels}"
                        )
                    except ValueError:
                        logger.warning(
                            f"Unknown TaskType in env mapping: {key}, skipping"
                        )
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid LABEL_MAPPINGS JSON: {e}, using defaults")

        # Apply custom mappings (highest priority)
        if custom_mappings:
            for task_type, labels in custom_mappings.items():
                mappings[task_type] = labels
                logger.debug(f"Applied custom mapping: {task_type.value} -> {labels}")

        return mappings

    @property
    def is_auto_triage_enabled(self) -> bool:
        """Check if automatic triaging is enabled."""
        return self._settings.enable_auto_triage

    def get_labels_for_type(self, task_type: TaskType) -> list[str]:
        """
        Get the labels to apply for a given task type.

        Args:
            task_type: The detected TaskType.

        Returns:
            List of label names to apply.
        """
        return self._mappings.get(task_type, [])

    def has_agent_labels(self, labels: list[str]) -> bool:
        """
        Check if the issue already has agent-related labels.

        Args:
            labels: List of existing label names.

        Returns:
            True if any agent label prefix is found.
        """
        for label in labels:
            label_lower = label.lower()
            for prefix in self.AGENT_LABEL_PREFIXES:
                if label_lower.startswith(prefix):
                    return True
        return False

    def filter_existing_labels(
        self,
        labels_to_apply: list[str],
        existing_labels: list[str],
    ) -> tuple[list[str], list[str]]:
        """
        Filter out labels that already exist on the issue.

        Args:
            labels_to_apply: Labels we want to apply.
            existing_labels: Labels already on the issue.

        Returns:
            Tuple of (labels_to_add, already_present).
        """
        existing_lower = {label.lower() for label in existing_labels}
        to_add = []
        already_present = []

        for label in labels_to_apply:
            if label.lower() in existing_lower:
                already_present.append(label)
            else:
                to_add.append(label)

        return to_add, already_present

    def triage_issue(
        self,
        detected_type: TaskType,
        existing_labels: list[str] | None = None,
    ) -> TriageResult:
        """
        Determine the labels to apply for an issue based on detected type.

        This method handles:
        1. Checking if auto-triage is enabled
        2. Checking if issue already has agent labels
        3. Getting the appropriate labels for the type
        4. Filtering out labels that already exist

        Args:
            detected_type: The detected TaskType from parsing.
            existing_labels: Labels already on the issue.

        Returns:
            TriageResult with labels to apply and metadata.
        """
        existing_labels = existing_labels or []

        # Check if auto-triage is enabled
        if not self._settings.enable_auto_triage:
            return TriageResult(
                detected_type=detected_type,
                labels_to_apply=[],
                skipped=True,
                reason="Auto-triage is disabled by configuration",
            )

        # Check if issue already has agent labels
        if self.has_agent_labels(existing_labels):
            return TriageResult(
                detected_type=detected_type,
                labels_to_apply=[],
                already_present=existing_labels,
                skipped=True,
                reason="Issue already has agent-related labels",
            )

        # Get labels for the detected type
        labels_to_apply = self.get_labels_for_type(detected_type)

        # Filter out labels that already exist
        labels_to_add, already_present = self.filter_existing_labels(
            labels_to_apply, existing_labels
        )

        reason = f"Detected type: {detected_type.value}"
        if already_present:
            reason += f", {len(already_present)} labels already present"

        return TriageResult(
            detected_type=detected_type,
            labels_to_apply=labels_to_add,
            already_present=already_present,
            skipped=False,
            reason=reason,
        )

    def update_mappings(self, new_mappings: dict[TaskType, list[str]]) -> None:
        """
        Update the label mappings at runtime.

        Args:
            new_mappings: New mappings to apply (merged with existing).
        """
        self._mappings.update(new_mappings)
        logger.info(f"Updated label mappings: {list(new_mappings.keys())}")

    def get_all_mappings(self) -> dict[TaskType, list[str]]:
        """
        Get all current label mappings.

        Returns:
            Copy of the current mappings dictionary.
        """
        return dict(self._mappings)


class TriageService:
    """
    High-level service for issue triaging.

    Combines the Issue Body Parser and Template Label Mapper
    to provide end-to-end triaging functionality.

    Example:
        ```python
        from src.notifier.parsers.issue_parser import IssueBodyParser
        from src.notifier.services.label_service import TriageService

        parser = IssueBodyParser()
        service = TriageService(parser=parser)

        result = service.triage(
            body="# [Bug] Something is broken",
            labels=["priority:high"],
            title="Fix this bug",
        )
        print(result.labels_to_apply)  # ["agent:queued", "bug"]
        ```
    """

    def __init__(
        self,
        parser: Any = None,  # IssueBodyParser type hint avoided to prevent circular import
        mapper: TemplateLabelMapper | None = None,
    ):
        """
        Initialize the Triage Service.

        Args:
            parser: Optional IssueBodyParser instance. If not provided,
                   a default parser will be created lazily.
            mapper: Optional TemplateLabelMapper instance. If not provided,
                   a default mapper will be created.
        """
        self._parser = parser
        self._mapper = mapper or TemplateLabelMapper()

    @property
    def parser(self):
        """Get or create the parser instance."""
        if self._parser is None:
            from src.notifier.parsers.issue_parser import IssueBodyParser

            self._parser = IssueBodyParser()
        return self._parser

    @property
    def mapper(self) -> TemplateLabelMapper:
        """Get the mapper instance."""
        return self._mapper

    def triage(
        self,
        body: str | None,
        labels: list[str] | None = None,
        title: str | None = None,
    ) -> TriageResult:
        """
        Perform full triaging on an issue.

        This method:
        1. Parses the issue body to detect the template type
        2. Maps the detected type to appropriate labels
        3. Returns a TriageResult with labels to apply

        Args:
            body: The issue body text.
            labels: Existing labels on the issue.
            title: Optional issue title for enhanced detection.

        Returns:
            TriageResult with triaging decision and labels.
        """
        # Parse the issue body with context
        parse_result = self.parser.parse_with_fallback(body, labels, title)

        # Map to labels
        triage_result = self._mapper.triage_issue(
            detected_type=parse_result.detected_type,
            existing_labels=labels,
        )

        # Add parse metadata to reason
        if parse_result.matched_pattern:
            triage_result.reason += f" (matched: {parse_result.matched_pattern})"

        logger.info(
            f"Triage result: type={triage_result.detected_type.value}, "
            f"labels={triage_result.labels_to_apply}, "
            f"skipped={triage_result.skipped}"
        )

        return triage_result

    def is_enabled(self) -> bool:
        """Check if auto-triage is enabled."""
        return self._mapper.is_auto_triage_enabled


# Module-level convenience instances
_default_mapper: TemplateLabelMapper | None = None
_default_service: TriageService | None = None


def get_default_mapper() -> TemplateLabelMapper:
    """Get or create the default label mapper instance."""
    global _default_mapper
    if _default_mapper is None:
        _default_mapper = TemplateLabelMapper()
    return _default_mapper


def get_default_service() -> TriageService:
    """Get or create the default triage service instance."""
    global _default_service
    if _default_service is None:
        _default_service = TriageService()
    return _default_service


def triage_issue(
    body: str | None,
    labels: list[str] | None = None,
    title: str | None = None,
) -> TriageResult:
    """
    Convenience function for quick issue triaging.

    Uses default parser and mapper instances.

    Args:
        body: The issue body text.
        labels: Existing labels on the issue.
        title: Optional issue title.

    Returns:
        TriageResult with triaging decision and labels.

    Example:
        >>> result = triage_issue("# [Bug] Something broken", [], "Fix bug")
        >>> result.labels_to_apply
        ['agent:queued', 'bug']
    """
    return get_default_service().triage(body, labels, title)
