"""
Dependency Resolution for the Architect Agent.

This module implements dependency graph analysis and resolution
for Epics extracted from Application Plans.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.models.plan import Epic, EpicDependency

logger = logging.getLogger(__name__)


class DependencyError(Exception):
    """Base exception for dependency-related errors."""

    pass


class CircularDependencyError(DependencyError):
    """Raised when a circular dependency is detected."""

    def __init__(self, cycle: list[str]) -> None:
        """Initialize with the detected cycle.

        Args:
            cycle: List of Epic IDs forming the circular dependency.
        """
        self.cycle = cycle
        super().__init__(f"Circular dependency detected: {' -> '.join(cycle)}")


class DependencyType(str, Enum):
    """Types of dependencies between Epics."""

    BLOCKS = "blocks"
    """Source Epic blocks target Epic."""

    REQUIRES = "requires"
    """Source Epic requires target Epic to be complete."""

    RELATES_TO = "relates_to"
    """Source Epic is related to target Epic (informational)."""


@dataclass
class DependencyNode:
    """A node in the dependency graph representing an Epic."""

    epic_id: str
    """Unique identifier for this Epic."""

    epic: Epic | None = None
    """Reference to the Epic object."""

    dependencies: list[str] = field(default_factory=list)
    """List of Epic IDs this Epic depends on."""

    dependents: list[str] = field(default_factory=list)
    """List of Epic IDs that depend on this Epic."""

    visited: bool = False
    """Flag for graph traversal algorithms."""

    in_stack: bool = False
    """Flag for cycle detection during DFS."""


@dataclass
class ResolutionResult:
    """Result of dependency resolution."""

    success: bool
    """Whether resolution was successful."""

    execution_order: list[str] = field(default_factory=list)
    """Ordered list of Epic IDs for execution."""

    parallel_groups: list[list[str]] = field(default_factory=list)
    """Groups of Epics that can be executed in parallel."""

    errors: list[str] = field(default_factory=list)
    """List of errors encountered during resolution."""

    warnings: list[str] = field(default_factory=list)
    """List of warnings generated during resolution."""


class DependencyGraph:
    """
    Dependency graph for Epic relationships.

    This class manages the dependency relationships between Epics
    and provides methods for cycle detection, topological sorting,
    and parallelization analysis.

    Example:
        ```python
        graph = DependencyGraph()

        # Add Epics
        graph.add_epic(epic1)
        graph.add_epic(epic2)

        # Add dependency: epic1 blocks epic2
        graph.add_dependency("epic-1", "epic-2", DependencyType.BLOCKS)

        # Get execution order
        result = graph.resolve()
        if result.success:
            for epic_id in result.execution_order:
                print(epic_id)
        ```
    """

    def __init__(self) -> None:
        """Initialize an empty dependency graph."""
        self._nodes: dict[str, DependencyNode] = {}

    def add_epic(self, epic: Epic) -> None:
        """
        Add an Epic to the graph.

        Args:
            epic: The Epic to add.
        """
        if epic.id not in self._nodes:
            self._nodes[epic.id] = DependencyNode(
                epic_id=epic.id,
                epic=epic,
            )
        else:
            # Update existing node with Epic reference
            self._nodes[epic.id].epic = epic

        # Add dependencies from Epic
        for dep in epic.dependencies:
            self._add_dependency_edge(epic.id, dep.epic_id, dep.dependency_type)

    def add_dependency(
        self,
        source_id: str,
        target_id: str,
        dependency_type: str = "blocks",
    ) -> None:
        """
        Add a dependency relationship between two Epics.

        Args:
            source_id: ID of the source Epic (the one with the dependency).
            target_id: ID of the target Epic (the one being depended on).
            dependency_type: Type of dependency relationship.
        """
        # Ensure both nodes exist
        if source_id not in self._nodes:
            self._nodes[source_id] = DependencyNode(epic_id=source_id)
        if target_id not in self._nodes:
            self._nodes[target_id] = DependencyNode(epic_id=target_id)

        self._add_dependency_edge(source_id, target_id, dependency_type)

    def _add_dependency_edge(
        self,
        source_id: str,
        target_id: str,
        dependency_type: str,
    ) -> None:
        """Internal method to add a dependency edge."""
        # For "blocks" and "requires", source depends on target
        if dependency_type in ("blocks", "requires"):
            self._nodes[source_id].dependencies.append(target_id)
            # Ensure target node exists before updating dependents
            if target_id not in self._nodes:
                self._nodes[target_id] = DependencyNode(epic_id=target_id)
            self._nodes[target_id].dependents.append(source_id)

    def detect_cycle(self) -> list[str] | None:
        """
        Detect if there's a circular dependency in the graph.

        Returns:
            List of Epic IDs forming a cycle, or None if no cycle exists.
        """
        # Reset visit flags
        for node in self._nodes.values():
            node.visited = False
            node.in_stack = False

        # DFS from each unvisited node
        for node_id in self._nodes:
            if not self._nodes[node_id].visited:
                cycle = self._detect_cycle_dfs(node_id, [])
                if cycle:
                    return cycle

        return None

    def _detect_cycle_dfs(self, node_id: str, path: list[str]) -> list[str] | None:
        """DFS-based cycle detection.

        Args:
            node_id: Current node being visited.
            path: Current path in the traversal.

        Returns:
            Cycle path if found, None otherwise.
        """
        node = self._nodes[node_id]
        node.visited = True
        node.in_stack = True
        path.append(node_id)

        for dep_id in node.dependencies:
            if dep_id not in self._nodes:
                # Dependency refers to non-existent node, skip
                continue

            dep_node = self._nodes[dep_id]
            if dep_node.in_stack:
                # Found cycle - reconstruct it
                cycle_start = path.index(dep_id)
                return path[cycle_start:] + [dep_id]

            if not dep_node.visited:
                cycle = self._detect_cycle_dfs(dep_id, path.copy())
                if cycle:
                    return cycle

        node.in_stack = False
        return None

    def topological_sort(self) -> list[str]:
        """
        Perform topological sort on the dependency graph.

        Returns:
            Ordered list of Epic IDs.

        Raises:
            CircularDependencyError: If a cycle is detected.
        """
        # Check for cycles first
        cycle = self.detect_cycle()
        if cycle:
            raise CircularDependencyError(cycle)

        # Reset visit flags
        for node in self._nodes.values():
            node.visited = False

        result: list[str] = []

        # DFS-based topological sort
        for node_id in self._nodes:
            if not self._nodes[node_id].visited:
                self._topo_sort_dfs(node_id, result)

        return result

    def _topo_sort_dfs(self, node_id: str, result: list[str]) -> None:
        """DFS-based topological sort helper."""
        node = self._nodes[node_id]
        node.visited = True

        for dep_id in node.dependencies:
            if dep_id in self._nodes and not self._nodes[dep_id].visited:
                self._topo_sort_dfs(dep_id, result)

        result.append(node_id)

    def find_parallel_groups(self) -> list[list[str]]:
        """
        Find groups of Epics that can be executed in parallel.

        Returns:
            List of groups, where each group contains Epic IDs
            that can be executed concurrently.
        """
        # Check for cycles first
        cycle = self.detect_cycle()
        if cycle:
            return []

        # Use Kahn's algorithm to find levels
        in_degree: dict[str, int] = {node_id: 0 for node_id in self._nodes}

        for node in self._nodes.values():
            for dep_id in node.dependencies:
                if dep_id in in_degree:
                    pass  # Don't increment, we want reverse direction

        # Count how many dependencies each node has
        for node_id, node in self._nodes.items():
            in_degree[node_id] = len([d for d in node.dependencies if d in self._nodes])

        groups: list[list[str]] = []
        remaining = set(self._nodes.keys())

        while remaining:
            # Find all nodes with no remaining dependencies
            current_group = [
                node_id for node_id in remaining if in_degree[node_id] == 0
            ]

            if not current_group:
                # This shouldn't happen if there's no cycle
                break

            groups.append(current_group)

            # Remove current group and update in-degrees
            for node_id in current_group:
                remaining.remove(node_id)
                # Update dependents
                for dependent_id in self._nodes[node_id].dependents:
                    if dependent_id in in_degree:
                        in_degree[dependent_id] -= 1

        return groups

    def get_dependencies(self, epic_id: str) -> list[str]:
        """
        Get all dependencies for an Epic.

        Args:
            epic_id: The Epic ID to get dependencies for.

        Returns:
            List of Epic IDs that the given Epic depends on.
        """
        if epic_id not in self._nodes:
            return []
        return self._nodes[epic_id].dependencies.copy()

    def get_dependents(self, epic_id: str) -> list[str]:
        """
        Get all Epics that depend on a given Epic.

        Args:
            epic_id: The Epic ID to get dependents for.

        Returns:
            List of Epic IDs that depend on the given Epic.
        """
        if epic_id not in self._nodes:
            return []
        return self._nodes[epic_id].dependents.copy()

    def is_blocked(self, epic_id: str, completed_epics: set[str]) -> bool:
        """
        Check if an Epic is blocked by incomplete dependencies.

        Args:
            epic_id: The Epic ID to check.
            completed_epics: Set of Epic IDs that are already complete.

        Returns:
            True if the Epic has incomplete blocking dependencies.
        """
        if epic_id not in self._nodes:
            return False

        for dep_id in self._nodes[epic_id].dependencies:
            if dep_id not in completed_epics:
                return True

        return False

    @property
    def node_count(self) -> int:
        """Get the number of nodes in the graph."""
        return len(self._nodes)

    @property
    def epic_ids(self) -> list[str]:
        """Get all Epic IDs in the graph."""
        return list(self._nodes.keys())


class DependencyResolver:
    """
    Resolver for analyzing and validating Epic dependencies.

    This class provides high-level methods for dependency analysis,
    including validation rules and execution planning.

    Example:
        ```python
        resolver = DependencyResolver()

        # Add Epics with dependencies
        resolver.add_epic(epic1)
        resolver.add_epic(epic2)

        # Resolve dependencies
        result = resolver.resolve()

        if result.success:
            print("Execution order:", result.execution_order)
            print("Parallel groups:", result.parallel_groups)
        else:
            print("Errors:", result.errors)
        ```
    """

    def __init__(self) -> None:
        """Initialize the dependency resolver."""
        self._graph = DependencyGraph()
        self._epics: dict[str, Epic] = {}

    def add_epic(self, epic: Epic) -> None:
        """
        Add an Epic to the resolver.

        Args:
            epic: The Epic to add.
        """
        self._epics[epic.id] = epic
        self._graph.add_epic(epic)

    def add_epics(self, epics: list[Epic]) -> None:
        """
        Add multiple Epics to the resolver.

        Args:
            epics: List of Epics to add.
        """
        for epic in epics:
            self.add_epic(epic)

    def resolve(self) -> ResolutionResult:
        """
        Resolve dependencies and determine execution order.

        Returns:
            ResolutionResult with execution order and parallel groups.
        """
        result = ResolutionResult(success=True)

        # Check for cycles
        cycle = self._graph.detect_cycle()
        if cycle:
            result.success = False
            result.errors.append(f"Circular dependency detected: {' -> '.join(cycle)}")
            return result

        try:
            # Get topological order
            result.execution_order = self._graph.topological_sort()

            # Get parallel groups
            result.parallel_groups = self._graph.find_parallel_groups()

            # Generate warnings for potential issues
            result.warnings = self._generate_warnings()

        except CircularDependencyError as e:
            result.success = False
            result.errors.append(str(e))

        except Exception as e:
            result.success = False
            result.errors.append(f"Resolution failed: {str(e)}")

        return result

    def _generate_warnings(self) -> list[str]:
        """Generate warnings for potential dependency issues."""
        warnings: list[str] = []

        # Check for Epics with many dependencies
        for epic_id in self._graph.epic_ids:
            deps = self._graph.get_dependencies(epic_id)
            if len(deps) > 3:
                warnings.append(
                    f"Epic '{epic_id}' has {len(deps)} dependencies - "
                    "consider splitting into smaller Epics"
                )

        # Check for Epics that block many others
        for epic_id in self._graph.epic_ids:
            dependents = self._graph.get_dependents(epic_id)
            if len(dependents) > 3:
                warnings.append(
                    f"Epic '{epic_id}' blocks {len(dependents)} other Epics - "
                    "prioritize this Epic"
                )

        return warnings

    def validate_dependencies(self) -> list[str]:
        """
        Validate all dependencies and return any issues found.

        Returns:
            List of validation error messages.
        """
        errors: list[str] = []

        # Check for dependencies on non-existent Epics
        for epic_id in self._graph.epic_ids:
            deps = self._graph.get_dependencies(epic_id)
            for dep_id in deps:
                if dep_id not in self._epics:
                    errors.append(
                        f"Epic '{epic_id}' depends on non-existent Epic '{dep_id}'"
                    )

        # Check for self-dependencies
        for epic_id in self._graph.epic_ids:
            deps = self._graph.get_dependencies(epic_id)
            if epic_id in deps:
                errors.append(f"Epic '{epic_id}' has a self-dependency")

        return errors

    def get_ready_epics(self, completed_epics: set[str]) -> list[str]:
        """
        Get Epics that are ready to be started.

        Args:
            completed_epics: Set of Epic IDs that are already complete.

        Returns:
            List of Epic IDs that have all dependencies satisfied.
        """
        ready: list[str] = []

        for epic_id in self._graph.epic_ids:
            if epic_id in completed_epics:
                continue

            if not self._graph.is_blocked(epic_id, completed_epics):
                ready.append(epic_id)

        return ready

    @property
    def graph(self) -> DependencyGraph:
        """Get the underlying dependency graph."""
        return self._graph
