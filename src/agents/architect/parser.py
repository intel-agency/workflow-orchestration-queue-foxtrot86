"""
Plan Parser for the Architect Sub-Agent.

This module provides functionality to parse Application Plan markdown
content into structured data that can be used for Epic generation.
"""

import re
from typing import Any

from .models import ParsedPlan, PlanSection


class PlanParser:
    """
    Parses Application Plan markdown content into structured data.

    This class extracts key sections from an Application Plan issue
    and structures them for Epic generation.

    Example:
        ```python
        parser = PlanParser()
        plan = parser.parse(
            issue_number=42,
            issue_url="https://github.com/owner/repo/issues/42",
            markdown_content="..."
        )
        print(plan.goals)
        ```
    """

    # Regex patterns for section extraction
    SECTION_PATTERNS: dict[PlanSection, list[str]] = {
        PlanSection.OVERVIEW: [
            r"^##\s*Overview\s*$",
            r"^##\s*Summary\s*$",
            r"^##\s*Description\s*$",
            r"^##\s*Background\s*$",
        ],
        PlanSection.GOALS: [
            r"^##\s*Goals\s*$",
            r"^##\s*Objectives\s*$",
            r"^##\s*Goals\s*&\s*Objectives\s*$",
        ],
        PlanSection.SCOPE: [
            r"^##\s*Scope\s*$",
            r"^##\s*Scope\s*&\s*Boundaries\s*$",
            r"^##\s*In\s*Scope\s*$",
        ],
        PlanSection.TECHNICAL_REQUIREMENTS: [
            r"^##\s*Technical\s*Requirements\s*$",
            r"^##\s*Tech\s*Stack\s*$",
            r"^##\s*Technology\s*Stack\s*$",
            r"^##\s*Architecture\s*$",
        ],
        PlanSection.USER_STORIES: [
            r"^##\s*User\s*Stories\s*$",
            r"^##\s*Use\s*Cases\s*$",
            r"^##\s*Features\s*$",
        ],
        PlanSection.ACCEPTANCE_CRITERIA: [
            r"^##\s*Acceptance\s*Criteria\s*$",
            r"^##\s*Success\s*Criteria\s*$",
            r"^##\s*Definition\s*of\s*Done\s*$",
        ],
        PlanSection.IMPLEMENTATION_PLAN: [
            r"^##\s*Implementation\s*Plan\s*$",
            r"^##\s*Implementation\s*$",
            r"^##\s*Development\s*Plan\s*$",
            r"^##\s*Execution\s*Plan\s*$",
        ],
        PlanSection.RISKS: [
            r"^##\s*Risks?\s*$",
            r"^##\s*Risk\s*Assessment\s*$",
            r"^##\s*Risks\s*&\s*Mitigations\s*$",
        ],
        PlanSection.TIMELINE: [
            r"^##\s*Timeline\s*$",
            r"^##\s*Milestones\s*$",
            r"^##\s*Schedule\s*$",
        ],
    }

    def parse(
        self,
        issue_number: int,
        issue_url: str,
        markdown_content: str,
    ) -> ParsedPlan:
        """
        Parse an Application Plan markdown document.

        Args:
            issue_number: GitHub issue number of the source plan.
            issue_url: URL to the source plan issue.
            markdown_content: The markdown content to parse.

        Returns:
            A ParsedPlan containing structured data extracted from the plan.
        """
        # Extract title (first # heading or first line)
        title = self._extract_title(markdown_content)

        # Parse all sections
        sections = self._extract_sections(markdown_content)

        return ParsedPlan(
            source_issue_number=issue_number,
            source_issue_url=issue_url,
            title=title,
            overview=sections.get("overview"),
            goals=self._extract_list_items(sections.get("goals", "")),
            scope=self._extract_scope(sections.get("scope", "")),
            technical_requirements=self._extract_list_items(
                sections.get("technical_requirements", "")
            ),
            user_stories=self._extract_list_items(sections.get("user_stories", "")),
            acceptance_criteria=self._extract_list_items(
                sections.get("acceptance_criteria", "")
            ),
            implementation_sections=self._extract_implementation_sections(
                sections.get("implementation_plan", "")
            ),
            risks=self._extract_risks(sections.get("risks", "")),
            timeline=sections.get("timeline"),
            raw_content=markdown_content,
        )

    def _extract_title(self, content: str) -> str:
        """Extract the title from markdown content."""
        # Look for first # heading
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()

        # Fallback to first non-empty line
        lines = content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                return line[:100]  # Limit title length

        return "Untitled Plan"

    def _extract_sections(self, content: str) -> dict[str, str]:
        """Extract all recognized sections from the markdown content."""
        sections: dict[str, str] = {}
        lines = content.split("\n")

        current_section: str | None = None
        current_content: list[str] = []

        for line in lines:
            # Check if this line starts a new section
            section_type = self._identify_section(line)

            if section_type != PlanSection.UNKNOWN:
                # Save previous section if exists
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()

                current_section = section_type.value
                current_content = []
            elif current_section:
                # Add content to current section (skip the section header)
                current_content.append(line)

        # Save the last section
        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return sections

    def _identify_section(self, line: str) -> PlanSection:
        """Identify which section a header line belongs to."""
        for section_type, patterns in self.SECTION_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, line, re.IGNORECASE):
                    return section_type
        return PlanSection.UNKNOWN

    def _extract_list_items(self, content: str) -> list[str]:
        """Extract list items from markdown content."""
        items: list[str] = []
        lines = content.split("\n")

        for line in lines:
            stripped = line.strip()
            # Match bullet points (-, *, +) or numbered lists (1., 2., etc.)
            match = re.match(r"^[-*+]\s+(.+)$|^\d+\.\s+(.+)$", stripped)
            if match:
                item = match.group(1) or match.group(2)
                items.append(item.strip())

        return items

    def _extract_scope(self, content: str) -> dict[str, list[str]]:
        """Extract scope information (in-scope and out-of-scope items)."""
        scope: dict[str, list[str]] = {"in_scope": [], "out_of_scope": []}

        # Look for in-scope/out-of-scope subsections
        in_scope_match = re.search(
            r"(?:###\s*)?In[ -]?Scope:?\s*\n([\s\S]*?)(?=(?:###\s*)?(?:Out|Non|$))",
            content,
            re.IGNORECASE,
        )
        out_scope_match = re.search(
            r"(?:###\s*)?Out[ -]?of[ -]?Scope:?\s*\n([\s\S]*?)(?=(?:###|$))",
            content,
            re.IGNORECASE,
        )

        if in_scope_match:
            scope["in_scope"] = self._extract_list_items(in_scope_match.group(1))
        if out_scope_match:
            scope["out_of_scope"] = self._extract_list_items(out_scope_match.group(1))

        # If no subsections found, treat all items as in-scope
        if not scope["in_scope"] and not scope["out_of_scope"]:
            scope["in_scope"] = self._extract_list_items(content)

        return scope

    def _extract_implementation_sections(self, content: str) -> dict[str, str]:
        """Extract implementation plan subsections."""
        sections: dict[str, str] = {}

        # Match ### level headings within implementation plan
        pattern = r"###\s+(.+?)\s*\n([\s\S]*?)(?=###|$)"
        matches = re.findall(pattern, content)

        for title, body in matches:
            sections[title.strip().lower().replace(" ", "_")] = body.strip()

        # If no subsections, store the whole content
        if not sections and content.strip():
            sections["main"] = content.strip()

        return sections

    def _extract_risks(self, content: str) -> list[dict[str, str]]:
        """Extract risks and their mitigations."""
        risks: list[dict[str, str]] = []

        # Pattern for risk table rows or list items with mitigation
        table_pattern = r"\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|"
        list_pattern = r"^[-*+]\s*(.+?)(?::\s*|[-–]\s*)(.+)$"

        lines = content.split("\n")

        # First try table format
        for line in lines:
            match = re.match(table_pattern, line)
            if match:
                risk = match.group(1).strip()
                mitigation = match.group(2).strip()
                # Filter out header rows and separator rows
                if risk.lower() not in ("risk", "mitigation", "risks", "mitigations"):
                    # Skip rows that are just dashes (markdown table separators)
                    if not (re.match(r"^-+$", risk) or re.match(r"^-+$", mitigation)):
                        risks.append({"risk": risk, "mitigation": mitigation})

        # If no table found, try list format
        if not risks:
            for line in lines:
                match = re.match(list_pattern, line.strip(), re.IGNORECASE)
                if match:
                    risks.append(
                        {
                            "risk": match.group(1).strip(),
                            "mitigation": match.group(2).strip(),
                        }
                    )

        return risks

    def extract_work_items(self, plan: ParsedPlan) -> list[dict[str, Any]]:
        """
        Extract potential work items from a parsed plan.

        This method identifies discrete work items that could become Epics.

        Args:
            plan: The parsed plan to extract work items from.

        Returns:
            List of work item dictionaries with title, description, and source.
        """
        work_items: list[dict[str, Any]] = []

        # Extract from implementation sections
        for section_name, content in plan.implementation_sections.items():
            items = self._extract_list_items(content)
            for item in items:
                work_items.append(
                    {
                        "title": item,
                        "description": f"From implementation section: {section_name}",
                        "source": "implementation_plan",
                    }
                )

        # Extract from user stories
        for story in plan.user_stories:
            work_items.append(
                {
                    "title": story,
                    "description": f"User story from plan",
                    "source": "user_stories",
                }
            )

        # Extract from technical requirements
        for req in plan.technical_requirements:
            work_items.append(
                {
                    "title": req,
                    "description": "Technical requirement from plan",
                    "source": "technical_requirements",
                }
            )

        return work_items
