"""
Epic Generator for the Architect Sub-Agent.

This module provides functionality to generate Epic issues from
parsed Application Plan data.
"""

from typing import Any

from .models import Epic, EpicStatus, ParsedPlan
from .parser import PlanParser
from .resolver import DependencyResolver


class EpicGenerator:
    """
    Generates Epic issues from a parsed Application Plan.

    This class takes a ParsedPlan and generates 3-5 well-structured
    Epic issues that cover the plan's requirements.

    Example:
        ```python
        parser = PlanParser()
        plan = parser.parse(issue_number=42, issue_url="...", markdown_content="...")

        generator = EpicGenerator()
        epics = generator.generate(plan)
        for epic in epics:
            print(f"{epic.id}: {epic.title}")
        ```
    """

    # Minimum and maximum number of epics to generate
    MIN_EPICS = 3
    MAX_EPICS = 5

    def __init__(self) -> None:
        """Initialize the EpicGenerator."""
        self._resolver = DependencyResolver()

    def generate(
        self,
        plan: ParsedPlan,
        target_repo: str = "",
    ) -> list[Epic]:
        """
        Generate Epics from a parsed Application Plan.

        Args:
            plan: The parsed plan to generate epics from.
            target_repo: Target repository in "owner/repo" format.

        Returns:
            List of generated Epic objects.
        """
        # Extract work items from the plan
        parser = PlanParser()
        work_items = parser.extract_work_items(plan)

        # Cluster work items into logical groups
        clusters = self._cluster_work_items(work_items, plan)

        # Generate epics from clusters
        epics = self._create_epics_from_clusters(clusters, plan, target_repo)

        # Resolve dependencies
        if epics:
            self._assign_dependencies(epics, plan)
            self._resolver.resolve(epics)

        # Assign priorities
        self._assign_priorities(epics)

        # Ensure we have at least MIN_EPICS
        while len(epics) < self.MIN_EPICS:
            # Add a placeholder epic if needed
            epic_num = len(epics) + 1
            epics.append(
                Epic(
                    id=f"epic-{epic_num}",
                    title=f"Additional Implementation Task {epic_num}",
                    description=f"Additional tasks identified from the plan: {plan.title}",
                    labels=["epic", "implementation:ready"],
                    status=EpicStatus.DRAFT,
                    priority=epic_num,
                    metadata={
                        "source_plan_issue": plan.source_issue_number,
                        "target_repo": target_repo,
                        "work_item_count": 0,
                    },
                )
            )

        # Limit to MAX_EPICS
        return epics[: self.MAX_EPICS]

    def _cluster_work_items(
        self,
        work_items: list[dict[str, Any]],
        plan: ParsedPlan,
    ) -> list[dict[str, Any]]:
        """
        Cluster work items into logical groups for Epic generation.

        This method groups related work items based on their source
        and content similarity.

        Args:
            work_items: List of extracted work items.
            plan: The source plan for context.

        Returns:
            List of cluster dictionaries containing title, items, and source.
        """
        clusters: dict[str, list[dict[str, Any]]] = {
            "foundation": [],
            "core_features": [],
            "integration": [],
            "testing": [],
            "documentation": [],
        }

        # Categorize work items by source and keywords
        for item in work_items:
            title = item.get("title", "").lower()
            source = item.get("source", "")

            # Foundation items (setup, infrastructure, core)
            if any(
                kw in title
                for kw in [
                    "setup",
                    "config",
                    "initial",
                    "foundation",
                    "infrastructure",
                    "base",
                    "core",
                ]
            ):
                clusters["foundation"].append(item)
            # Testing items
            elif any(
                kw in title for kw in ["test", "testing", "qa", "quality", "coverage"]
            ):
                clusters["testing"].append(item)
            # Documentation items
            elif any(kw in title for kw in ["doc", "documentation", "readme", "guide"]):
                clusters["documentation"].append(item)
            # Integration items
            elif any(
                kw in title for kw in ["integrate", "integration", "api", "connect"]
            ):
                clusters["integration"].append(item)
            # Core features (default for implementation items)
            elif source == "implementation_plan":
                clusters["core_features"].append(item)
            else:
                clusters["core_features"].append(item)

        # Convert to list format, filtering empty clusters
        result: list[dict[str, Any]] = []
        cluster_metadata = {
            "foundation": {
                "title": "Foundation & Infrastructure",
                "priority": 1,
            },
            "core_features": {
                "title": "Core Feature Implementation",
                "priority": 2,
            },
            "integration": {
                "title": "Integration & API",
                "priority": 3,
            },
            "testing": {
                "title": "Testing & Quality Assurance",
                "priority": 4,
            },
            "documentation": {
                "title": "Documentation & Training",
                "priority": 5,
            },
        }

        for cluster_name, items in clusters.items():
            if items:
                meta = cluster_metadata.get(cluster_name, {})
                result.append(
                    {
                        "name": cluster_name,
                        "title": meta.get("title", cluster_name.title()),
                        "items": items,
                        "priority": meta.get("priority", 99),
                    }
                )

        # Sort by priority
        result.sort(key=lambda x: x.get("priority", 99))

        return result

    def _create_epics_from_clusters(
        self,
        clusters: list[dict[str, Any]],
        plan: ParsedPlan,
        target_repo: str,
    ) -> list[Epic]:
        """
        Create Epic objects from clustered work items.

        Args:
            clusters: List of work item clusters.
            plan: Source plan for context.
            target_repo: Target repository.

        Returns:
            List of Epic objects.
        """
        epics: list[Epic] = []

        for idx, cluster in enumerate(clusters, start=1):
            items = cluster.get("items", [])

            # Build epic description
            description = self._build_epic_description(cluster, plan)

            # Build acceptance criteria
            acceptance_criteria = self._build_acceptance_criteria(cluster, plan)

            epic = Epic(
                id=f"epic-{idx}",
                title=f"{plan.title}: {cluster.get('title', f'Task {idx}')}",
                description=description,
                acceptance_criteria=acceptance_criteria,
                labels=["epic", "implementation:ready", "orchestration:epic-ready"],
                status=EpicStatus.DRAFT,
                priority=idx,
                metadata={
                    "cluster_name": cluster.get("name"),
                    "source_plan_issue": plan.source_issue_number,
                    "target_repo": target_repo,
                    "work_item_count": len(items),
                },
            )

            epics.append(epic)

        return epics

    def _build_epic_description(
        self,
        cluster: dict[str, Any],
        plan: ParsedPlan,
    ) -> str:
        """
        Build the description for an Epic.

        Args:
            cluster: The work item cluster.
            plan: Source plan for context.

        Returns:
            Formatted description string.
        """
        items = cluster.get("items", [])
        cluster_title = cluster.get("title", "Implementation Tasks")

        lines = [
            f"## {cluster_title}",
            "",
            f"Part of Application Plan: [{plan.title}]({plan.source_issue_url})",
            "",
            "### Tasks",
            "",
        ]

        for item in items:
            title = item.get("title", "Untitled task")
            source = item.get("source", "unknown")
            lines.append(f"- {title} _(from {source})_")

        # Add context from plan overview if available
        if plan.overview:
            lines.extend(
                [
                    "",
                    "### Context",
                    "",
                    plan.overview[:500],  # Limit overview length
                ]
            )

        return "\n".join(lines)

    def _build_acceptance_criteria(
        self,
        cluster: dict[str, Any],
        plan: ParsedPlan,
    ) -> list[str]:
        """
        Build acceptance criteria for an Epic.

        Args:
            cluster: The work item cluster.
            plan: Source plan for context.

        Returns:
            List of acceptance criteria strings.
        """
        criteria: list[str] = []

        # Add criteria from the plan
        for criterion in plan.acceptance_criteria[:5]:  # Limit to 5
            criteria.append(criterion)

        # Add default criteria based on cluster type
        cluster_name = cluster.get("name", "")
        items = cluster.get("items", [])

        if cluster_name == "foundation":
            criteria.extend(
                [
                    "Development environment is properly configured",
                    "Core infrastructure components are deployed",
                    "Basic functionality is accessible",
                ]
            )
        elif cluster_name == "core_features":
            criteria.extend(
                [
                    "All features are implemented as specified",
                    "Features pass unit tests",
                    "Code meets quality standards",
                ]
            )
        elif cluster_name == "integration":
            criteria.extend(
                [
                    "APIs are properly integrated",
                    "Integration tests pass",
                    "External services are connected",
                ]
            )
        elif cluster_name == "testing":
            criteria.extend(
                [
                    "Test coverage meets target (80%+)",
                    "All tests pass in CI",
                    "Edge cases are covered",
                ]
            )
        elif cluster_name == "documentation":
            criteria.extend(
                [
                    "Documentation is complete and accurate",
                    "README is updated",
                    "API documentation is generated",
                ]
            )

        # Add task-specific criteria
        for item in items[:3]:
            title = item.get("title", "")
            if title:
                criteria.append(f"Complete: {title}")

        return list(dict.fromkeys(criteria))  # Remove duplicates while preserving order

    def _assign_dependencies(
        self,
        epics: list[Epic],
        plan: ParsedPlan,
    ) -> None:
        """
        Assign dependencies between epics based on logical ordering.

        This method establishes a dependency chain based on the
        typical software development lifecycle.

        Args:
            epics: List of epics to update.
            plan: Source plan for context.
        """
        if len(epics) < 2:
            return

        # Create a dependency chain based on cluster type
        cluster_order = [
            "foundation",
            "core_features",
            "integration",
            "testing",
            "documentation",
        ]

        for i, epic in enumerate(epics):
            cluster_name = epic.metadata.get("cluster_name", "")
            cluster_idx = (
                cluster_order.index(cluster_name)
                if cluster_name in cluster_order
                else 99
            )

            # Find dependencies from earlier clusters
            for j, other_epic in enumerate(epics):
                if i == j:
                    continue

                other_cluster = other_epic.metadata.get("cluster_name", "")
                other_idx = (
                    cluster_order.index(other_cluster)
                    if other_cluster in cluster_order
                    else 99
                )

                # If this epic comes after in the order, add dependency
                if cluster_idx > other_idx:
                    if other_epic.id not in epic.dependencies:
                        epic.dependencies.append(other_epic.id)

    def _assign_priorities(self, epics: list[Epic]) -> None:
        """
        Assign priorities to epics based on their position in the dependency chain.

        Args:
            epics: List of epics to update.
        """
        # Resolve to get execution order
        result = self._resolver.resolve(epics)

        # Assign priorities based on execution order
        for idx, epic_id in enumerate(result.execution_order):
            for epic in epics:
                if epic.id == epic_id:
                    epic.priority = idx + 1
                    break

    def generate_github_issue_body(
        self,
        epic: Epic,
        plan: ParsedPlan,
    ) -> str:
        """
        Generate the full GitHub issue body for an Epic.

        Args:
            epic: The Epic to generate the issue body for.
            plan: Source plan for context.

        Returns:
            Formatted markdown string for the GitHub issue.
        """
        lines = [
            f"# {epic.title}",
            "",
            f"> **Part of:** #{plan.source_issue_number} ({plan.title})",
            "",
            "---",
            "",
            epic.description,
            "",
            "---",
            "",
            "## Acceptance Criteria",
            "",
        ]

        for criterion in epic.acceptance_criteria:
            lines.append(f"- [ ] {criterion}")

        if epic.dependencies:
            lines.extend(
                [
                    "",
                    "## Dependencies",
                    "",
                    f"Blocked by: {', '.join(epic.dependencies)}",
                ]
            )

        if epic.estimated_effort:
            lines.extend(
                [
                    "",
                    "## Estimated Effort",
                    "",
                    epic.estimated_effort,
                ]
            )

        lines.extend(
            [
                "",
                "---",
                "",
                f"*Generated by Architect Agent from Plan #{plan.source_issue_number}*",
            ]
        )

        return "\n".join(lines)
