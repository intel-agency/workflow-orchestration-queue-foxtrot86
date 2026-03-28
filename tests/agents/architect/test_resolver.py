"""
Unit tests for the Dependency Resolver module.

Tests cover:
- Dependency graph construction
- Cycle detection
- Topological sorting
- Parallel group analysis
- Resolution validation
"""

import pytest

from src.agents.architect.resolver import (
    CircularDependencyError,
    DependencyError,
    DependencyGraph,
    DependencyResolver,
    DependencyType,
    ResolutionResult,
)
from src.models.plan import (
    Epic,
    EpicDependency,
    EpicPriority,
)


def create_epic(
    epic_id: str,
    title: str = "Test Epic",
    dependencies: list[str] | None = None,
) -> Epic:
    """Helper to create an Epic with optional dependencies."""
    epic = Epic(
        id=epic_id,
        title=title,
        overview=f"Overview for {title}",
        priority=EpicPriority.MEDIUM,
    )
    if dependencies:
        for dep_id in dependencies:
            epic.dependencies.append(
                EpicDependency(epic_id=dep_id, dependency_type="blocks")
            )
    return epic


class TestDependencyError:
    """Tests for dependency exceptions."""

    def test_dependency_error(self) -> None:
        """Test base dependency error."""
        with pytest.raises(DependencyError):
            raise DependencyError("Test error")

    def test_circular_dependency_error(self) -> None:
        """Test circular dependency error."""
        error = CircularDependencyError(["a", "b", "c", "a"])
        assert "a -> b -> c -> a" in str(error)
        assert error.cycle == ["a", "b", "c", "a"]


class TestResolutionResult:
    """Tests for ResolutionResult dataclass."""

    def test_success_result(self) -> None:
        """Test successful resolution result."""
        result = ResolutionResult(
            success=True,
            execution_order=["a", "b", "c"],
            parallel_groups=[["a"], ["b", "c"]],
        )
        assert result.success is True
        assert len(result.execution_order) == 3
        assert len(result.parallel_groups) == 2

    def test_failure_result(self) -> None:
        """Test failed resolution result."""
        result = ResolutionResult(
            success=False,
            errors=["Cycle detected"],
        )
        assert result.success is False
        assert "Cycle detected" in result.errors


class TestDependencyGraph:
    """Tests for DependencyGraph class."""

    def test_empty_graph(self) -> None:
        """Test empty graph initialization."""
        graph = DependencyGraph()
        assert graph.node_count == 0
        assert graph.epic_ids == []

    def test_add_epic(self) -> None:
        """Test adding an Epic to the graph."""
        graph = DependencyGraph()
        epic = create_epic("epic-1", "First Epic")

        graph.add_epic(epic)

        assert graph.node_count == 1
        assert "epic-1" in graph.epic_ids

    def test_add_dependency(self) -> None:
        """Test adding a dependency relationship."""
        graph = DependencyGraph()
        graph.add_epic(create_epic("epic-1"))
        graph.add_epic(create_epic("epic-2"))

        graph.add_dependency("epic-2", "epic-1", "blocks")

        deps = graph.get_dependencies("epic-2")
        assert "epic-1" in deps

    def test_get_dependencies_empty(self) -> None:
        """Test getting dependencies for non-existent Epic."""
        graph = DependencyGraph()
        deps = graph.get_dependencies("nonexistent")
        assert deps == []

    def test_get_dependents(self) -> None:
        """Test getting dependents for an Epic."""
        graph = DependencyGraph()
        graph.add_epic(create_epic("epic-1"))
        graph.add_epic(create_epic("epic-2"))
        graph.add_dependency("epic-2", "epic-1", "blocks")

        dependents = graph.get_dependents("epic-1")
        assert "epic-2" in dependents

    def test_detect_no_cycle(self) -> None:
        """Test cycle detection with no cycle."""
        graph = DependencyGraph()
        graph.add_epic(create_epic("epic-1"))
        graph.add_epic(create_epic("epic-2", dependencies=["epic-1"]))
        graph.add_epic(create_epic("epic-3", dependencies=["epic-2"]))

        cycle = graph.detect_cycle()
        assert cycle is None

    def test_detect_simple_cycle(self) -> None:
        """Test cycle detection with simple cycle."""
        graph = DependencyGraph()
        graph.add_epic(create_epic("epic-1", dependencies=["epic-2"]))
        graph.add_epic(create_epic("epic-2", dependencies=["epic-1"]))

        cycle = graph.detect_cycle()
        assert cycle is not None
        assert len(cycle) >= 2

    def test_detect_three_node_cycle(self) -> None:
        """Test cycle detection with three-node cycle."""
        graph = DependencyGraph()
        graph.add_epic(create_epic("epic-1", dependencies=["epic-3"]))
        graph.add_epic(create_epic("epic-2", dependencies=["epic-1"]))
        graph.add_epic(create_epic("epic-3", dependencies=["epic-2"]))

        cycle = graph.detect_cycle()
        assert cycle is not None

    def test_topological_sort_simple(self) -> None:
        """Test topological sort with simple dependencies."""
        graph = DependencyGraph()
        graph.add_epic(create_epic("epic-1"))
        graph.add_epic(create_epic("epic-2", dependencies=["epic-1"]))
        graph.add_epic(create_epic("epic-3", dependencies=["epic-2"]))

        order = graph.topological_sort()

        # epic-1 should come before epic-2, which should come before epic-3
        assert order.index("epic-1") < order.index("epic-2")
        assert order.index("epic-2") < order.index("epic-3")

    def test_topological_sort_with_cycle(self) -> None:
        """Test topological sort raises error on cycle."""
        graph = DependencyGraph()
        graph.add_epic(create_epic("epic-1", dependencies=["epic-2"]))
        graph.add_epic(create_epic("epic-2", dependencies=["epic-1"]))

        with pytest.raises(CircularDependencyError):
            graph.topological_sort()

    def test_find_parallel_groups(self) -> None:
        """Test finding parallel execution groups."""
        graph = DependencyGraph()
        graph.add_epic(create_epic("epic-1"))
        graph.add_epic(create_epic("epic-2"))
        graph.add_epic(create_epic("epic-3", dependencies=["epic-1", "epic-2"]))

        groups = graph.find_parallel_groups()

        assert len(groups) >= 1
        # First group should have epic-1 and epic-2 (no dependencies)
        first_group = groups[0]
        assert "epic-1" in first_group
        assert "epic-2" in first_group

    def test_find_parallel_groups_with_cycle(self) -> None:
        """Test parallel groups returns empty on cycle."""
        graph = DependencyGraph()
        graph.add_epic(create_epic("epic-1", dependencies=["epic-2"]))
        graph.add_epic(create_epic("epic-2", dependencies=["epic-1"]))

        groups = graph.find_parallel_groups()
        assert groups == []

    def test_is_blocked(self) -> None:
        """Test checking if an Epic is blocked."""
        graph = DependencyGraph()
        graph.add_epic(create_epic("epic-1"))
        graph.add_epic(create_epic("epic-2", dependencies=["epic-1"]))

        # epic-2 is blocked when epic-1 is not complete
        assert graph.is_blocked("epic-2", set()) is True
        assert graph.is_blocked("epic-2", {"epic-1"}) is False

    def test_is_blocked_no_deps(self) -> None:
        """Test is_blocked for Epic with no dependencies."""
        graph = DependencyGraph()
        graph.add_epic(create_epic("epic-1"))

        assert graph.is_blocked("epic-1", set()) is False


class TestDependencyResolver:
    """Tests for DependencyResolver class."""

    def test_empty_resolver(self) -> None:
        """Test resolver with no Epics."""
        resolver = DependencyResolver()
        result = resolver.resolve()

        assert result.success is True
        assert result.execution_order == []
        assert result.parallel_groups == []

    def test_single_epic(self) -> None:
        """Test resolver with single Epic."""
        resolver = DependencyResolver()
        resolver.add_epic(create_epic("epic-1"))

        result = resolver.resolve()

        assert result.success is True
        assert result.execution_order == ["epic-1"]
        assert result.parallel_groups == [["epic-1"]]

    def test_linear_dependencies(self) -> None:
        """Test resolver with linear dependency chain."""
        resolver = DependencyResolver()
        resolver.add_epic(create_epic("epic-1"))
        resolver.add_epic(create_epic("epic-2", dependencies=["epic-1"]))
        resolver.add_epic(create_epic("epic-3", dependencies=["epic-2"]))

        result = resolver.resolve()

        assert result.success is True
        assert len(result.execution_order) == 3
        assert result.execution_order.index("epic-1") < result.execution_order.index(
            "epic-2"
        )
        assert result.execution_order.index("epic-2") < result.execution_order.index(
            "epic-3"
        )

    def test_diamond_dependencies(self) -> None:
        """Test resolver with diamond dependency pattern."""
        resolver = DependencyResolver()
        # epic-1 <- epic-2, epic-3 <- epic-4
        resolver.add_epic(create_epic("epic-1"))
        resolver.add_epic(create_epic("epic-2", dependencies=["epic-1"]))
        resolver.add_epic(create_epic("epic-3", dependencies=["epic-1"]))
        resolver.add_epic(create_epic("epic-4", dependencies=["epic-2", "epic-3"]))

        result = resolver.resolve()

        assert result.success is True
        assert len(result.execution_order) == 4
        # epic-1 should come first
        assert result.execution_order[0] == "epic-1"
        # epic-4 should come last
        assert result.execution_order[-1] == "epic-4"

    def test_circular_dependency_detection(self) -> None:
        """Test resolver detects circular dependencies."""
        resolver = DependencyResolver()
        resolver.add_epic(create_epic("epic-1", dependencies=["epic-2"]))
        resolver.add_epic(create_epic("epic-2", dependencies=["epic-1"]))

        result = resolver.resolve()

        assert result.success is False
        assert any("circular" in e.lower() for e in result.errors)

    def test_validate_dependencies(self) -> None:
        """Test dependency validation."""
        resolver = DependencyResolver()
        resolver.add_epic(create_epic("epic-1", dependencies=["nonexistent"]))

        errors = resolver.validate_dependencies()

        assert len(errors) > 0
        assert any("nonexistent" in e for e in errors)

    def test_validate_self_dependency(self) -> None:
        """Test detection of self-dependency."""
        resolver = DependencyResolver()
        resolver.add_epic(create_epic("epic-1", dependencies=["epic-1"]))

        errors = resolver.validate_dependencies()

        assert any("self-dependency" in e.lower() for e in errors)

    def test_get_ready_epics(self) -> None:
        """Test getting ready Epics."""
        resolver = DependencyResolver()
        resolver.add_epic(create_epic("epic-1"))
        resolver.add_epic(create_epic("epic-2", dependencies=["epic-1"]))
        resolver.add_epic(create_epic("epic-3"))

        ready = resolver.get_ready_epics(set())

        # epic-1 and epic-3 have no dependencies
        assert "epic-1" in ready
        assert "epic-3" in ready
        assert "epic-2" not in ready

    def test_get_ready_epics_after_completion(self) -> None:
        """Test getting ready Epics after completing some."""
        resolver = DependencyResolver()
        resolver.add_epic(create_epic("epic-1"))
        resolver.add_epic(create_epic("epic-2", dependencies=["epic-1"]))

        # After completing epic-1, epic-2 should be ready
        ready = resolver.get_ready_epics({"epic-1"})

        assert "epic-2" in ready

    def test_warnings_for_many_dependencies(self) -> None:
        """Test warning generation for Epics with many dependencies."""
        resolver = DependencyResolver()
        resolver.add_epic(create_epic("epic-1"))
        resolver.add_epic(create_epic("epic-2"))
        resolver.add_epic(create_epic("epic-3"))
        resolver.add_epic(create_epic("epic-4"))
        resolver.add_epic(
            create_epic("epic-5", dependencies=["epic-1", "epic-2", "epic-3", "epic-4"])
        )

        result = resolver.resolve()

        # Should generate a warning about too many dependencies
        assert any("dependencies" in w.lower() for w in result.warnings)


class TestDependencyType:
    """Tests for DependencyType enum."""

    def test_dependency_types(self) -> None:
        """Test dependency type values."""
        assert DependencyType.BLOCKS.value == "blocks"
        assert DependencyType.REQUIRES.value == "requires"
        assert DependencyType.RELATES_TO.value == "relates_to"
