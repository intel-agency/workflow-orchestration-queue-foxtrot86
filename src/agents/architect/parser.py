"""
Plan Parser for the Architect Agent.

This module implements parsing of Application Plan markdown content
into structured Plan and Epic objects.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from src.models.plan import (
    AcceptanceCriterion,
    Epic,
    EpicDependency,
    EpicPriority,
    ParsedSection,
    Plan,
    PlanStatus,
    WorkItem,
)

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """Result of parsing a plan document."""

    success: bool
    plan: Plan | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


class PlanParserError(Exception):
    """Error during plan parsing."""

    pass


class PlanParser:
    """
    Parser for Application Plan markdown documents.

    This class parses markdown content from Application Plan issues
    and extracts structured data including goals, work items,
    acceptance criteria, and suggested Epic breakdowns.

    Example:
        ```python
        parser = PlanParser()
        result = parser.parse(markdown_content)

        if result.success:
            plan = result.plan
            print(f"Plan: {plan.title}")
            print(f"Goals: {plan.goals}")
            for epic in plan.epics:
                print(f"Epic: {epic.title}")
        ```
    """

    # Common section heading patterns
    SECTION_PATTERNS = {
        "overview": re.compile(r"^#\s*(overview|summary|description)", re.IGNORECASE),
        "goals": re.compile(r"^#\s*(goals|objectives)", re.IGNORECASE),
        "stories": re.compile(r"^#\s*(stories|epics?|tasks)", re.IGNORECASE),
        "acceptance": re.compile(r"^#\s*(acceptance|criteria|ac)", re.IGNORECASE),
        "dependencies": re.compile(r"^#\s*(dependencies|deps)", re.IGNORECASE),
        "tech_stack": re.compile(r"^#\s*(tech|stack|technology)", re.IGNORECASE),
        "implementation": re.compile(
            r"^#\s*(implementation|tasks?|plan)", re.IGNORECASE
        ),
        "risks": re.compile(r"^#\s*(risks?|mitigation)", re.IGNORECASE),
    }

    # Patterns for extracting items
    CHECKBOX_PATTERN = re.compile(r"^\s*[-*]\s*\[([ x])\]\s*(.+)$", re.MULTILINE)
    LIST_ITEM_PATTERN = re.compile(r"^\s*[-*]\s*(.+)$", re.MULTILINE)
    HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

    def __init__(self, issue_number: int | str | None = None) -> None:
        """
        Initialize the Plan Parser.

        Args:
            issue_number: Optional issue number for the plan.
        """
        self.issue_number = issue_number

    def parse(self, content: str, source_url: str | None = None) -> ParseResult:
        """
        Parse markdown content into a Plan object.

        Args:
            content: Markdown content of the Application Plan.
            source_url: Optional URL to the original issue.

        Returns:
            ParseResult containing the parsed Plan or error.
        """
        if not content or not content.strip():
            return ParseResult(
                success=False,
                error="Content cannot be empty",
            )

        try:
            # Extract title from first heading
            title = self._extract_title(content)

            # Parse sections
            sections = self._parse_sections(content)

            # Create Plan object
            plan = Plan(
                id=str(self.issue_number) if self.issue_number else "unknown",
                title=title,
                source_url=source_url,
                raw_content=content,
                status=PlanStatus.DRAFT,
            )

            # Extract overview
            plan.overview = self._extract_overview(sections)

            # Extract goals
            plan.goals = self._extract_goals(sections, content)

            # Extract technology stack
            plan.technology_stack = self._extract_tech_stack(sections, content)

            # Extract suggested epics/stories
            plan.epics = self._extract_epics(sections, content, plan.id)

            # Extract acceptance criteria
            plan.acceptance_criteria = self._extract_acceptance_criteria(
                sections, content
            )

            logger.info(f"Successfully parsed plan: {title}")

            return ParseResult(
                success=True,
                plan=plan,
                warnings=self._generate_warnings(plan),
            )

        except Exception as e:
            logger.error(f"Failed to parse plan: {e}")
            return ParseResult(
                success=False,
                error=f"Parse error: {str(e)}",
            )

    def _extract_title(self, content: str) -> str:
        """Extract title from the first H1 heading."""
        match = self.HEADING_PATTERN.search(content)
        if match and match.group(1) == "#":
            return match.group(2).strip()

        # Fallback: try to find title in first line
        first_line = content.split("\n")[0].strip()
        if first_line and not first_line.startswith("#"):
            return first_line[:100]  # Limit title length

        return "Untitled Plan"

    def _parse_sections(self, content: str) -> list[ParsedSection]:
        """Parse content into sections based on headings."""
        sections: list[ParsedSection] = []
        lines = content.split("\n")

        current_section: ParsedSection | None = None
        current_content: list[str] = []

        for line in lines:
            heading_match = self.HEADING_PATTERN.match(line)
            if heading_match:
                # Save previous section
                if current_section:
                    current_section.content = "\n".join(current_content).strip()
                    sections.append(current_section)

                # Start new section
                level = len(heading_match.group(1))
                heading = heading_match.group(2).strip()
                current_section = ParsedSection(
                    heading=heading,
                    level=level,
                    content="",
                )
                current_content = []
            elif current_section:
                current_content.append(line)

        # Save last section
        if current_section:
            current_section.content = "\n".join(current_content).strip()
            sections.append(current_section)

        return sections

    def _find_section(
        self, sections: list[ParsedSection], pattern_key: str
    ) -> ParsedSection | None:
        """Find a section matching a pattern key."""
        pattern = self.SECTION_PATTERNS.get(pattern_key)
        if not pattern:
            return None

        for section in sections:
            if pattern.match(f"# {section.heading}"):
                return section

        return None

    def _extract_overview(self, sections: list[ParsedSection]) -> str | None:
        """Extract overview/summary from sections."""
        overview_section = self._find_section(sections, "overview")
        if overview_section:
            return overview_section.content[:500]  # Limit length

        # Fallback: use first paragraph after title
        for section in sections:
            if section.content.strip():
                return section.content.split("\n\n")[0][:500]

        return None

    def _extract_goals(self, sections: list[ParsedSection], content: str) -> list[str]:
        """Extract goals from the plan."""
        goals: list[str] = []

        goals_section = self._find_section(sections, "goals")
        if goals_section:
            # Extract list items
            goals.extend(self._extract_list_items(goals_section.content))

        # Also check for checkbox items marked as goals
        if not goals:
            for match in self.CHECKBOX_PATTERN.finditer(content):
                item_text = match.group(2).strip()
                if any(kw in item_text.lower() for kw in ["goal", "objective", "aim"]):
                    goals.append(item_text)

        return goals[:10]  # Limit to 10 goals

    def _extract_tech_stack(
        self, sections: list[ParsedSection], content: str
    ) -> list[str]:
        """Extract technology stack mentions."""
        tech_stack: list[str] = []

        tech_section = self._find_section(sections, "tech_stack")
        if tech_section:
            tech_stack.extend(self._extract_list_items(tech_section.content))

        # Also scan for common tech keywords
        tech_keywords = [
            "python",
            "javascript",
            "typescript",
            "react",
            "vue",
            "angular",
            "node",
            "fastapi",
            "django",
            "flask",
            "postgresql",
            "mysql",
            "mongodb",
            "redis",
            "docker",
            "kubernetes",
            "aws",
            "azure",
            "gcp",
            "langchain",
            "pydantic",
            "httpx",
            "pytest",
        ]

        content_lower = content.lower()
        for tech in tech_keywords:
            if tech in content_lower and tech not in [t.lower() for t in tech_stack]:
                tech_stack.append(tech.title())

        return tech_stack[:15]

    def _extract_epics(
        self,
        sections: list[ParsedSection],
        content: str,
        plan_id: str,
    ) -> list[Epic]:
        """Extract suggested Epics from the plan."""
        epics: list[Epic] = []

        # Pattern to match story/epic headings
        story_heading_pattern = re.compile(
            r"(?:story|epic)\s*(\d+)[:\s]+(.+)",
            re.IGNORECASE,
        )

        # Look for sections that are story/epic headings
        for section in sections:
            match = story_heading_pattern.match(section.heading)
            if match:
                epic_id = f"{plan_id}-epic-{match.group(1)}"
                epic_title = match.group(2).strip()
                overview = (
                    section.content[:200]
                    if section.content
                    else f"Epic extracted from plan: {epic_title}"
                )

                epics.append(
                    Epic(
                        id=epic_id,
                        title=epic_title,
                        overview=overview,
                        priority=EpicPriority.MEDIUM,
                    )
                )

        # Also check Stories section content for inline story definitions
        stories_section = self._find_section(sections, "stories")
        if stories_section:
            for line in stories_section.content.split("\n"):
                line = line.strip()
                epic_match = re.match(
                    r"(?:#+\s*)?(?:story|epic)\s*(\d+)[:\s]+(.+)",
                    line,
                    re.IGNORECASE,
                )
                if epic_match:
                    epic_id = f"{plan_id}-epic-{epic_match.group(1)}"
                    epic_title = epic_match.group(2).strip()

                    # Avoid duplicates
                    if not any(e.id == epic_id for e in epics):
                        epics.append(
                            Epic(
                                id=epic_id,
                                title=epic_title,
                                overview=f"Epic extracted from plan: {epic_title}",
                                priority=EpicPriority.MEDIUM,
                            )
                        )

        # Also check implementation section for tasks that could be epics
        if not epics:
            impl_section = self._find_section(sections, "implementation")
            if impl_section:
                items = self._extract_list_items(impl_section.content)
                for i, item in enumerate(items[:5], 1):  # Limit to 5
                    epics.append(
                        Epic(
                            id=f"{plan_id}-epic-{i}",
                            title=item[:100],
                            overview=f"Implementation task: {item}",
                            priority=EpicPriority.MEDIUM,
                        )
                    )

        return epics

    def _extract_acceptance_criteria(
        self, sections: list[ParsedSection], content: str
    ) -> list[AcceptanceCriterion]:
        """Extract acceptance criteria from the plan."""
        criteria: list[AcceptanceCriterion] = []

        ac_section = self._find_section(sections, "acceptance")
        if ac_section:
            items = self._extract_list_items(ac_section.content)
            for i, item in enumerate(items, 1):
                criteria.append(
                    AcceptanceCriterion(
                        id=f"ac-{i}",
                        description=item,
                        verified=False,
                    )
                )

        # Also look for checkbox items in acceptance section
        if ac_section:
            for match in self.CHECKBOX_PATTERN.finditer(ac_section.content):
                criteria.append(
                    AcceptanceCriterion(
                        id=f"ac-{len(criteria) + 1}",
                        description=match.group(2).strip(),
                        verified=match.group(1).lower() == "x",
                    )
                )

        return criteria[:15]

    def _extract_list_items(self, content: str) -> list[str]:
        """Extract plain list items from content."""
        items: list[str] = []

        for match in self.LIST_ITEM_PATTERN.finditer(content):
            item = match.group(1).strip()
            # Skip if it's a checkbox (handled separately)
            if not item.startswith("[") and item:
                items.append(item)

        return items

    def _generate_warnings(self, plan: Plan) -> list[str]:
        """Generate warnings for potential issues with the parsed plan."""
        warnings: list[str] = []

        if not plan.overview:
            warnings.append("No overview section found")

        if not plan.goals:
            warnings.append("No goals identified")

        if not plan.epics:
            warnings.append("No epics/stories extracted from plan")

        if not plan.acceptance_criteria:
            warnings.append("No acceptance criteria found")

        return warnings

    def parse_github_issue_url(self, url: str) -> dict[str, Any] | None:
        """
        Parse a GitHub issue URL to extract owner, repo, and issue number.

        Args:
            url: GitHub issue URL.

        Returns:
            Dictionary with owner, repo, issue_number or None if invalid.
        """
        pattern = r"github\.com/([^/]+)/([^/]+)/issues/(\d+)"
        match = re.search(pattern, url)
        if match:
            return {
                "owner": match.group(1),
                "repo": match.group(2),
                "issue_number": int(match.group(3)),
            }
        return None
