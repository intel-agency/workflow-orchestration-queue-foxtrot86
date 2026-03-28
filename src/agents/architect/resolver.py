"""
Dependency Resolution for the Architect Sub-Agent.

This module provides functionality to analyze and resolve dependencies
between Epics, including topological sorting and cycle detection.
"""

from dataclasses import dataclass, field
from typing import Any

from .models import Dependency, DependencyType, Epic


@dataclass
class ResolutionResult:
    """
    Result of dependency resolution.

    Attributes:
        execution_order: List of epic IDs in safe execution order.
        parallel_groups: Groups of epic IDs that can be executed in parallel.
        blocked_epics: Epic IDs that are blocked by unresolved dependencies.
        cycles_detected: List of circular dependency chains found.
        warnings: Warning messages about potential issues.
    """

    execution_order: list[str] = field(default_factory=list)
    parallel_groups: list[list[str]] = field(default_factory=list)
    blocked_epics: list[str] = field(default_factory=list)
    cycles_detected: list[list[str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DependencyResolver:
    """
    Analyzes and resolves dependencies between Epics.

    This class provides:
    - Dependency graph construction
    - Topological sorting for execution order
    - Cycle detection
    - Parallelization analysis

    Example:
        ```python
        resolver = DependencyResolver()
        epics = [Epic(id="epic-1", ...), Epic(id="epic-2", dependencies=["epic-1"])]
        result = resolver.resolve(epics)
        print(result.execution_order)  # ["epic-1", "epic-2"]
        ```
    """

    def __init__(self) -> None:
        """Initialize the DependencyResolver."""
        self._graph: dict[str, set[str]] = {}
        self._reverse_graph: dict[str, set[str]] = {}

    def resolve(self, epics: list[Epic]) -> ResolutionResult:
        """
        Resolve dependencies for a list of Epics.

        Args:
            epics: List of Epic objects to resolve dependencies for.

        Returns:
            ResolutionResult containing execution order, parallel groups,
            blocked epics, and any detected cycles.
        """
        # Build the dependency graph
        self._build_graph(epics)

        # Detect cycles first
        cycles = self._detect_cycles()

        result = ResolutionResult(cycles_detected=cycles)

        if cycles:
            result.warnings.append(
                f"Circular dependencies detected: {cycles}. "
                "Cannot determine safe execution order."
            )
            # Mark all epics in cycles as blocked
            for cycle in cycles:
                result.blocked_epics.extend(cycle)
            return result

        # Perform topological sort
        execution_order = self._topological_sort()
        result.execution_order = execution_order

        # Determine parallel groups
        result.parallel_groups = self._find_parallel_groups(epics, execution_order)

        # Identify blocked epics (those with dependencies not in success state)
        result.blocked_epics = self._find_blocked_epics(epics, execution_order)

        return result

    def _build_graph(self, epics: list[Epic]) -> None:
        """
        Build the dependency graph from Epics.

        Creates both forward (epic -> depends_on) and reverse
        (epic -> blocked_by) graphs.
        """
        self._graph = {}
        self._reverse_graph = {}

        # Initialize all nodes
        for epic in epics:
            self._graph[epic.id] = set()
            self._reverse_graph[epic.id] = set()

        # Add edges for dependencies
        for epic in epics:
            for dep_id in epic.dependencies:
                if dep_id in self._graph:
                    # epic depends on dep_id
                    self._graph[epic.id].add(dep_id)
                    self._reverse_graph[dep_id].add(epic.id)

    def _detect_cycles(self) -> list[list[str]]:
        """
        Detect circular dependencies using DFS.

        Returns:
            List of cycles found, where each cycle is a list of epic IDs.
        """
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self._graph.get(node, set()):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            path.pop()
            rec_stack.remove(node)
            return False

        for node in self._graph:
            if node not in visited:
                dfs(node)

        return cycles

    def _topological_sort(self) -> list[str]:
        """
        Perform topological sort on the dependency graph.

        Uses Kahn's algorithm for deterministic ordering.

        Returns:
            List of epic IDs in topological order.
        """
        # Calculate in-degree for each node
        in_degree: dict[str, int] = {node: 0 for node in self._graph}
        for node in self._graph:
            for dep in self._graph[node]:
                # dep is depended upon, so doesn't increase its in-degree
                pass

        # Actually, in-degree = number of nodes that depend on this node
        # But for topological sort, we need: in-degree = number of dependencies
        in_degree = {node: len(self._graph[node]) for node in self._graph}

        # Start with nodes that have no dependencies
        queue = sorted([node for node, degree in in_degree.items() if degree == 0])
        result: list[str] = []

        while queue:
            # Take the first node (sorted for determinism)
            node = queue.pop(0)
            result.append(node)

            # Reduce in-degree for nodes that depend on this one
            for dependent in self._reverse_graph.get(node, set()):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    # Insert in sorted position for determinism
                    self._sorted_insert(queue, dependent)

        return result

    def _sorted_insert(self, lst: list[str], item: str) -> None:
        """Insert an item into a sorted list maintaining order."""
        for i, existing in enumerate(lst):
            if item < existing:
                lst.insert(i, item)
                return
        lst.append(item)

    def _find_parallel_groups(
        self, epics: list[Epic], execution_order: list[str]
    ) -> list[list[str]]:
        """
        Find groups of Epics that can be executed in parallel.

        Two epics can be parallelized if neither depends on the other
        and they share no common dependencies.

        Args:
            epics: List of all Epics.
            execution_order: Topologically sorted execution order.

        Returns:
            List of parallel groups, where each group is a list of epic IDs.
        """
        if not execution_order:
            return []

        # Group by "level" - epics at the same level can be parallelized
        levels: dict[str, int] = {}
        epic_map = {epic.id: epic for epic in epics}

        for epic_id in execution_order:
            epic = epic_map.get(epic_id)
            if not epic:
                continue

            # Level = max level of dependencies + 1
            if not epic.dependencies:
                levels[epic_id] = 0
            else:
                max_dep_level = max(levels.get(dep, -1) for dep in epic.dependencies)
                levels[epic_id] = max_dep_level + 1

        # Group epics by level
        max_level = max(levels.values()) if levels else 0
        groups: list[list[str]] = [[] for _ in range(max_level + 1)]

        for epic_id, level in levels.items():
            groups[level].append(epic_id)

        # Filter out empty groups
        return [g for g in groups if g]

    def _find_blocked_epics(
        self, epics: list[Epic], execution_order: list[str]
    ) -> list[str]:
        """
        Find epics that are blocked by incomplete dependencies.

        An epic is blocked if any of its dependencies are not in
        the success state.

        Note: This method identifies epics that would be blocked
        in a real execution context. For planning purposes, all
        epics in the execution_order are considered unblocked.

        Args:
            epics: List of all Epics.
            execution_order: Topologically sorted execution order.

        Returns:
            List of blocked epic IDs.
        """
        # In the planning phase, we don't have execution state
        # So we return empty list - blocking is determined at runtime
        return []

    def get_dependencies(self, epic_id: str) -> list[Dependency]:
        """
        Get all dependencies for a specific epic.

        Args:
            epic_id: The epic ID to get dependencies for.

        Returns:
            List of Dependency objects for the epic.
        """
        dependencies: list[Dependency] = []

        for dep_id in self._graph.get(epic_id, set()):
            dependencies.append(
                Dependency(
                    source_epic_id=epic_id,
                    target_epic_id=dep_id,
                    dependency_type=DependencyType.BLOCKED_BY,
                    description=f"{epic_id} is blocked by {dep_id}",
                )
            )

        return dependencies

    def get_dependents(self, epic_id: str) -> list[str]:
        """
        Get all epics that depend on a specific epic.

        Args:
            epic_id: The epic ID to get dependents for.

        Returns:
            List of epic IDs that depend on the specified epic.
        """
        return list(self._reverse_graph.get(epic_id, set()))

    def validate_dependencies(self, epics: list[Epic]) -> tuple[bool, list[str]]:
        """
        Validate that all dependencies reference existing epics.

        Args:
            epics: List of Epics to validate.

        Returns:
            Tuple of (is_valid, list_of_error_messages).
        """
        epic_ids = {epic.id for epic in epics}
        errors: list[str] = []

        for epic in epics:
            for dep_id in epic.dependencies:
                if dep_id not in epic_ids:
                    errors.append(f"Epic '{epic.id}' has unknown dependency '{dep_id}'")

        return len(errors) == 0, errors

    def can_parallelize(self, epic1_id: str, epic2_id: str) -> bool:
        """
        Check if two epics can be executed in parallel.

        Args:
            epic1_id: First epic ID.
            epic2_id: Second epic ID.

        Returns:
            True if the epics can be parallelized, False otherwise.
        """
        # They can be parallelized if neither depends on the other
        deps1 = self._graph.get(epic1_id, set())
        deps2 = self._graph.get(epic2_id, set())

        # Check if epic1 depends on epic2 or vice versa
        if epic2_id in deps1 or epic1_id in deps2:
            return False

        # Check if they share any common dependency
        return not (deps1 & deps2)
