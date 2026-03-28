"""
Issue Body Parser Module for Intelligent Template Triaging.

This module provides functionality to parse GitHub issue bodies and detect
the template type based on markdown headers and patterns.

Story 2.2.1: Issue Body Parser Module
"""

import re
import logging
import threading
from enum import Enum
from dataclasses import dataclass
from typing import Any

from src.models import TaskType

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """
    Result of parsing an issue body.

    Attributes:
        detected_type: The detected TaskType based on template patterns.
        confidence: Confidence level of the detection (0.0 to 1.0).
        matched_pattern: The pattern that matched, if any.
        raw_header: The raw header text that was matched.
    """

    detected_type: TaskType
    confidence: float = 1.0
    matched_pattern: str | None = None
    raw_header: str | None = None


class IssueBodyParser:
    """
    Parser for detecting template types in GitHub issue bodies.

    This class uses regex patterns to identify common template headers
    and map them to TaskType enum values.

    Example:
        ```python
        parser = IssueBodyParser()
        result = parser.parse("# [Application Plan]\\nThis is a plan...")
        print(result.detected_type)  # TaskType.PLAN
        ```
    """

    # Confidence threshold for high-confidence matches
    HIGH_CONFIDENCE_THRESHOLD: float = 0.8

    # Regex patterns for template detection
    # Patterns are ordered by specificity - more specific patterns first
    # Using conditional regex to ensure balanced brackets: (?(1)\]) means "if group 1 matched, require ]"
    TEMPLATE_PATTERNS: list[tuple[str, TaskType]] = [
        # Application Plan patterns
        (r"^\s*#\s*(\[)?Application Plan(?(1)\])", TaskType.PLAN),
        (r"^\s*#\s*(\[)?App Plan(?(1)\])", TaskType.PLAN),
        (r"^\s*#\s*(\[)?Plan(?(1)\])", TaskType.PLAN),
        (
            r"^\s*##\s*Overview\s*\n\s*This epic implements",
            TaskType.PLAN,
        ),  # Epic format
        (r"^\s*##\s*Implementation Plan", TaskType.PLAN),
        # Bug report patterns
        (r"^\s*#\s*(\[)?Bug(?(1)\])", TaskType.BUG),
        (r"^\s*#\s*(\[)?Bug Report(?(1)\])", TaskType.BUG),
        (r"^\s*##\s*Bug Description", TaskType.BUG),
        (r"^\s*##\s*Steps to Reproduce", TaskType.BUG),
        (r"^\s*##\s*Expected [Bb]ehavior", TaskType.BUG),
        (r"^\s*##\s*Actual [Bb]ehavior", TaskType.BUG),
        # Feature request patterns
        (r"^\s*#\s*(\[)?Feature(?(1)\])", TaskType.FEATURE),
        (r"^\s*#\s*(\[)?Feature Request(?(1)\])", TaskType.FEATURE),
        (r"^\s*##\s*Feature Description", TaskType.FEATURE),
        (r"^\s*##\s*Proposed [Ff]eature", TaskType.FEATURE),
        (r"^\s*##\s*User [Ss]tory", TaskType.FEATURE),
        (r"^\s*##\s*Acceptance [Cc]riteria", TaskType.FEATURE),
        # Enhancement patterns
        (r"^\s*#\s*(\[)?Enhancement(?(1)\])", TaskType.ENHANCEMENT),
        (r"^\s*#\s*\[?Improve", TaskType.ENHANCEMENT),
        (r"^\s*##\s*Enhancement", TaskType.ENHANCEMENT),
        (r"^\s*##\s*Improvement", TaskType.ENHANCEMENT),
        (r"^\s*##\s*Proposed [Ii]mprovement", TaskType.ENHANCEMENT),
        # Epic patterns (often have "Epic:" in title or body)
        (r"^\s*#\s*Epic:", TaskType.PLAN),
        (r"^\s*##\s*Epic\s+Stories", TaskType.PLAN),
    ]

    # Secondary patterns for content-based detection (lower confidence)
    CONTENT_PATTERNS: list[tuple[str, TaskType, float]] = [
        # Plan-related content
        (r"##\s*(Implementation|Execution|Development)\s+Plan\b", TaskType.PLAN, 0.8),
        (r"##\s*(Goals|Objectives|Milestones|Timeline)\b", TaskType.PLAN, 0.7),
        (r"##\s*Dependencies\b", TaskType.PLAN, 0.6),
        (r"##\s*Technology\s+Stack\b", TaskType.PLAN, 0.6),
        (r"##\s*Component\s+Architecture\b", TaskType.PLAN, 0.6),
        # Bug-related content
        (r"##\s*(Reproduce|Steps|Error|Stack\s*Trace)\b", TaskType.BUG, 0.7),
        (r"(?i)(crash|exception|error|broken|fail)", TaskType.BUG, 0.5),
        (r"##\s*Workaround\b", TaskType.BUG, 0.6),
        # Feature-related content
        (r"##\s*(User\s*Story|Use\s*Case|Scenario)\b", TaskType.FEATURE, 0.7),
        (r"(?i)(would\s+like|wish|request|suggest)", TaskType.FEATURE, 0.5),
        (r"##\s*Benefits\b", TaskType.FEATURE, 0.6),
        # Enhancement-related content
        (r"(?i)(improve|optimize|refactor|enhance|better)", TaskType.ENHANCEMENT, 0.5),
    ]

    def __init__(self, custom_patterns: list[tuple[str, TaskType]] | None = None):
        """
        Initialize the Issue Body Parser.

        Args:
            custom_patterns: Optional list of custom (pattern, TaskType) tuples
                           to add to the default patterns. These are added at
                           the beginning of the pattern list for higher priority.
        """
        self._patterns = list(self.TEMPLATE_PATTERNS)
        if custom_patterns:
            # Custom patterns get highest priority
            self._patterns = custom_patterns + self._patterns

        # Compile patterns for efficiency
        self._compiled_patterns = [
            (re.compile(pattern, re.MULTILINE | re.IGNORECASE), task_type)
            for pattern, task_type in self._patterns
        ]
        self._compiled_content_patterns = [
            (re.compile(pattern, re.MULTILINE | re.IGNORECASE), task_type, confidence)
            for pattern, task_type, confidence in self.CONTENT_PATTERNS
        ]

        logger.debug(
            f"IssueBodyParser initialized with {len(self._patterns)} header patterns "
            f"and {len(self.CONTENT_PATTERNS)} content patterns"
        )

    def parse(self, body: str | None) -> ParseResult:
        """
        Parse an issue body and detect the template type.

        Args:
            body: The issue body text to parse. Can be None or empty.

        Returns:
            ParseResult containing the detected type and metadata.

        Example:
            >>> parser = IssueBodyParser()
            >>> result = parser.parse("# [Bug] Something is broken")
            >>> result.detected_type
            <TaskType.BUG: 'BUG'>
        """
        if not body or not body.strip():
            logger.debug("Empty or None body, returning GENERIC type")
            return ParseResult(
                detected_type=TaskType.GENERIC,
                confidence=1.0,
                matched_pattern=None,
                raw_header=None,
            )

        # First pass: check header patterns (high confidence)
        for pattern, task_type in self._compiled_patterns:
            match = pattern.search(body)
            if match:
                logger.debug(
                    f"Matched header pattern '{pattern.pattern}' -> {task_type.value}"
                )
                return ParseResult(
                    detected_type=task_type,
                    confidence=1.0,
                    matched_pattern=pattern.pattern,
                    raw_header=match.group(0).strip(),
                )

        # Second pass: check content patterns (lower confidence)
        best_match: tuple[float, TaskType, str] | None = None
        for pattern, task_type, confidence in self._compiled_content_patterns:
            match = pattern.search(body)
            if match:
                # Take the highest confidence match
                if best_match is None or confidence > best_match[0]:
                    best_match = (confidence, task_type, pattern.pattern)

        if best_match:
            confidence, task_type, pattern_str = best_match
            logger.debug(
                f"Matched content pattern '{pattern_str}' -> {task_type.value} "
                f"(confidence: {confidence})"
            )
            return ParseResult(
                detected_type=task_type,
                confidence=confidence,
                matched_pattern=pattern_str,
                raw_header=None,
            )

        # No patterns matched - return generic
        logger.debug("No patterns matched, returning GENERIC type")
        return ParseResult(
            detected_type=TaskType.GENERIC,
            confidence=0.5,
            matched_pattern=None,
            raw_header=None,
        )

    def parse_with_fallback(
        self,
        body: str | None,
        labels: list[str] | None = None,
        title: str | None = None,
    ) -> ParseResult:
        """
        Parse an issue body with fallback to label and title analysis.

        This method provides enhanced detection by also checking existing
        labels and title when the body doesn't match any pattern.

        Args:
            body: The issue body text to parse.
            labels: Optional list of existing label names.
            title: Optional issue title.

        Returns:
            ParseResult containing the detected type and metadata.
        """
        # First try body parsing
        result = self.parse(body)

        # If high confidence match, return it
        if result.confidence >= self.HIGH_CONFIDENCE_THRESHOLD:
            return result

        # Fallback to label analysis
        if labels:
            label_result = self._detect_from_labels(labels)
            if label_result and label_result.confidence > result.confidence:
                logger.debug(
                    f"Label-based detection ({label_result.detected_type.value}) "
                    f"overrides body detection ({result.detected_type.value})"
                )
                return label_result

        # Fallback to title analysis
        if title:
            title_result = self._detect_from_title(title)
            if title_result and title_result.confidence > result.confidence:
                logger.debug(
                    f"Title-based detection ({title_result.detected_type.value}) "
                    f"overrides body detection ({result.detected_type.value})"
                )
                return title_result

        return result

    def _detect_from_labels(self, labels: list[str]) -> ParseResult | None:
        """
        Detect template type from existing labels.

        Args:
            labels: List of label names.

        Returns:
            ParseResult if a label indicates a type, None otherwise.
        """
        label_lower = [label.lower() for label in labels]

        # Check for type-indicating labels (exact match to avoid false positives)
        if any(label == "bug" for label in label_lower):
            return ParseResult(
                detected_type=TaskType.BUG,
                confidence=0.9,
                matched_pattern="label:bug",
                raw_header=None,
            )
        if any(label == "feature" for label in label_lower):
            return ParseResult(
                detected_type=TaskType.FEATURE,
                confidence=0.9,
                matched_pattern="label:feature",
                raw_header=None,
            )
        if any(label == "enhancement" for label in label_lower):
            return ParseResult(
                detected_type=TaskType.ENHANCEMENT,
                confidence=0.9,
                matched_pattern="label:enhancement",
                raw_header=None,
            )
        if any(label in ("plan", "epic") for label in label_lower):
            return ParseResult(
                detected_type=TaskType.PLAN,
                confidence=0.9,
                matched_pattern="label:plan/epic",
                raw_header=None,
            )

        return None

    def _detect_from_title(self, title: str) -> ParseResult | None:
        """
        Detect template type from the issue title.

        Args:
            title: The issue title.

        Returns:
            ParseResult if the title indicates a type, None otherwise.
        """
        title_lower = title.lower()

        # Check for type-indicating patterns in title
        if any(
            pattern in title_lower for pattern in ["[bug]", "bug:", "fix:", "error:"]
        ):
            return ParseResult(
                detected_type=TaskType.BUG,
                confidence=0.8,
                matched_pattern="title:bug",
                raw_header=title,
            )
        if any(
            pattern in title_lower for pattern in ["[feature]", "feature:", "feat:"]
        ):
            return ParseResult(
                detected_type=TaskType.FEATURE,
                confidence=0.8,
                matched_pattern="title:feature",
                raw_header=title,
            )
        if any(
            pattern in title_lower
            for pattern in ["[enhancement]", "enhancement:", "improve:"]
        ):
            return ParseResult(
                detected_type=TaskType.ENHANCEMENT,
                confidence=0.8,
                matched_pattern="title:enhancement",
                raw_header=title,
            )
        if any(
            pattern in title_lower for pattern in ["[plan]", "plan:", "epic:", "task:"]
        ):
            return ParseResult(
                detected_type=TaskType.PLAN,
                confidence=0.8,
                matched_pattern="title:plan/epic",
                raw_header=title,
            )

        return None


# Module-level convenience function
_default_parser: IssueBodyParser | None = None
_parser_lock = threading.Lock()


def parse_issue_body(body: str | None) -> ParseResult:
    """
    Parse an issue body using the default parser.

    This is a convenience function for simple use cases.

    Args:
        body: The issue body text to parse.

    Returns:
        ParseResult containing the detected type.

    Example:
        >>> result = parse_issue_body("# [Bug] Something is broken")
        >>> result.detected_type
        <TaskType.BUG: 'BUG'>
    """
    global _default_parser
    if _default_parser is None:
        with _parser_lock:
            # Double-checked locking pattern
            if _default_parser is None:
                _default_parser = IssueBodyParser()
    return _default_parser.parse(body)


def parse_issue_with_context(
    body: str | None,
    labels: list[str] | None = None,
    title: str | None = None,
) -> ParseResult:
    """
    Parse an issue with full context using the default parser.

    This is a convenience function that uses body, labels, and title
    for enhanced detection.

    Args:
        body: The issue body text to parse.
        labels: Optional list of existing label names.
        title: Optional issue title.

    Returns:
        ParseResult containing the detected type.
    """
    global _default_parser
    if _default_parser is None:
        with _parser_lock:
            # Double-checked locking pattern
            if _default_parser is None:
                _default_parser = IssueBodyParser()
    return _default_parser.parse_with_fallback(body, labels, title)
