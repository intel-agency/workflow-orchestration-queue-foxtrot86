"""
Unit tests for the DependencyResolver.
"""

import pytest

from src.agents.architect.models import Epic, EpicStatus
from src.agents.architect.resolver import DependencyResolver, ResolutionResult


@pytest.fixture
def simple_epics() -> list[Epic]:
    """Simple list of epics without dependencies."""
    return [
        Epic(
            id="epic-1",
            title="Epic 1",
            description="First epic",
        ),
        Epic(
            id="epic-2",
            title="Epic 2",
            description="Second epic",
        ),
        Epic(
            id="epic-3",
            title="Epic 3",
            description="Third epic",
        ),
    ]


@pytest.fixture
def dependent_epics() -> list[Epic]:
    """List of epics with dependencies."""
    return [
        Epic(
            id="epic-1",
            title="Foundation",
            description="Foundation epic",
            dependencies=[],
        ),
        Epic(
            id="epic-2",
            title="Core Features",
            description="Core features epic",
            dependencies=["epic-1"],
        ),
        Epic(
            id="epic-3",
            title="Integration",
            description="Integration epic",
            dependencies=["epic-1", "epic-2"],
        ),
        Epic(
            id="epic-4",
            title="Testing",
            description="Testing epic",
            dependencies=["epic-2"],
        ),
    ]


@pytest.fixture
def circular_epics() -> list[Epic]:
    """List of epics with circular dependencies."""
    return [
        Epic(
            id="epic-1",
            title="Epic 1",
            description="First epic",
            dependencies=["epic-3"],
        ),
        Epic(
            id="epic-2",
            title="Epic 2",
            description="Second epic",
            dependencies=["epic-1"],
        ),
        Epic(
            id="epic-3",
            title="Epic 3",
            description="Third epic",
            dependencies=["epic-2"],
        ),
    ]


class TestDependencyResolver:
    """Tests for the DependencyResolver class."""

    def test_resolve_returns_result(self, simple_epics: list[Epic]) -> None:
        """Test that resolve returns a ResolutionResult."""
        resolver = DependencyResolver()
        result = resolver.resolve(simple_epics)

        assert isinstance(result, ResolutionResult)

    def test_resolve_simple_epics(self, simple_epics: list[Epic]) -> None:
        """Test resolving epics without dependencies."""
        resolver = DependencyResolver()
        result = resolver.resolve(simple_epics)

        assert len(result.execution_order) == 3
        assert len(result.cycles_detected) == 0
        assert len(result.blocked_epics) == 0

    def test_resolve_execution_order(self, dependent_epics: list[Epic]) -> None:
        """Test that execution order respects dependencies."""
        resolver = DependencyResolver()
        result = resolver.resolve(dependent_epics)

        order = result.execution_order

        # epic-1 must come before epic-2
        assert order.index("epic-1") < order.index("epic-2")

        # epic-2 must come before epic-3 and epic-4
        assert order.index("epic-2") < order.index("epic-3")
        assert order.index("epic-2") < order.index("epic-4")

        # epic-1 must come before epic-3
        assert order.index("epic-1") < order.index("epic-3")

    def test_resolve_detects_cycles(self, circular_epics: list[Epic]) -> None:
        """Test that circular dependencies are detected."""
        resolver = DependencyResolver()
        result = resolver.resolve(circular_epics)

        assert len(result.cycles_detected) > 0
        assert len(result.warnings) > 0

    def test_resolve_parallel_groups_no_deps(self, simple_epics: list[Epic]) -> None:
        """Test parallel grouping with no dependencies."""
        resolver = DependencyResolver()
        result = resolver.resolve(simple_epics)

        # All epics should be in the same group (level 0)
        assert len(result.parallel_groups) >= 1
        assert len(result.parallel_groups[0]) == 3

    def test_resolve_parallel_groups_with_deps(
        self, dependent_epics: list[Epic]
    ) -> None:
        """Test parallel grouping with dependencies."""
        resolver = DependencyResolver()
        result = resolver.resolve(dependent_epics)

        # Should have multiple levels
        assert len(result.parallel_groups) >= 1

        # epic-4 and epic-3 should be in different groups than epic-1
        group_0_ids = result.parallel_groups[0] if result.parallel_groups else []
        assert "epic-1" in group_0_ids

    def test_get_dependencies(self, dependent_epics: list[Epic]) -> None:
        """Test getting dependencies for an epic."""
        resolver = DependencyResolver()
        resolver.resolve(dependent_epics)

        deps = resolver.get_dependencies("epic-3")

        assert len(deps) == 2
        dep_ids = {d.target_epic_id for d in deps}
        assert "epic-1" in dep_ids
        assert "epic-2" in dep_ids

    def test_get_dependents(self, dependent_epics: list[Epic]) -> None:
        """Test getting dependents for an epic."""
        resolver = DependencyResolver()
        resolver.resolve(dependent_epics)

        dependents = resolver.get_dependents("epic-1")

        assert "epic-2" in dependents
        assert "epic-3" in dependents

    def test_validate_dependencies_valid(self, dependent_epics: list[Epic]) -> None:
        """Test validation with valid dependencies."""
        resolver = DependencyResolver()
        is_valid, errors = resolver.validate_dependencies(dependent_epics)

        assert is_valid
        assert len(errors) == 0

    def test_validate_dependencies_invalid(self) -> None:
        """Test validation with invalid dependencies."""
        resolver = DependencyResolver()
        epics = [
            Epic(
                id="epic-1",
                title="Epic 1",
                description="First epic",
                dependencies=["epic-999"],  # Non-existent dependency
            ),
        ]

        is_valid, errors = resolver.validate_dependencies(epics)

        assert not is_valid
        assert len(errors) == 1
        assert "epic-999" in errors[0]

    def test_can_parallelize_no_deps(self, simple_epics: list[Epic]) -> None:
        """Test parallelization check with no dependencies."""
        resolver = DependencyResolver()
        resolver.resolve(simple_epics)

        # All epics should be parallelizable with each other
        assert resolver.can_parallelize("epic-1", "epic-2")
        assert resolver.can_parallelize("epic-1", "epic-3")
        assert resolver.can_parallelize("epic-2", "epic-3")

    def test_can_parallelize_with_deps(self, dependent_epics: list[Epic]) -> None:
        """Test parallelization check with dependencies."""
        resolver = DependencyResolver()
        resolver.resolve(dependent_epics)

        # epic-1 and epic-2 are not parallelizable (epic-2 depends on epic-1)
        assert not resolver.can_parallelize("epic-1", "epic-2")

        # epic-3 and epic-4 both depend on epic-2 (share common dependency)
        # so they are NOT parallelizable by our definition
        assert not resolver.can_parallelize("epic-3", "epic-4")

    def test_topological_sort_deterministic(self, simple_epics: list[Epic]) -> None:
        """Test that topological sort is deterministic."""
        resolver1 = DependencyResolver()
        resolver2 = DependencyResolver()

        result1 = resolver1.resolve(simple_epics)
        result2 = resolver2.resolve(simple_epics)

        # Results should be the same order
        assert result1.execution_order == result2.execution_order


class TestDependencyResolverEdgeCases:
    """Edge case tests for DependencyResolver."""

    def test_empty_epic_list(self) -> None:
        """Test resolving an empty list."""
        resolver = DependencyResolver()
        result = resolver.resolve([])

        assert result.execution_order == []
        assert result.parallel_groups == []
        assert result.cycles_detected == []

    def test_single_epic(self) -> None:
        """Test resolving a single epic."""
        resolver = DependencyResolver()
        epics = [
            Epic(
                id="epic-1",
                title="Only Epic",
                description="Single epic",
            ),
        ]

        result = resolver.resolve(epics)

        assert result.execution_order == ["epic-1"]
        assert len(result.parallel_groups) == 1
        assert result.parallel_groups[0] == ["epic-1"]

    def test_self_dependency(self) -> None:
        """Test handling of self-dependency (should be detected as cycle)."""
        resolver = DependencyResolver()
        epics = [
            Epic(
                id="epic-1",
                title="Self-referencing Epic",
                description="Epic that depends on itself",
                dependencies=["epic-1"],
            ),
        ]

        result = resolver.resolve(epics)

        # Self-dependency should be detected as a cycle
        assert len(result.cycles_detected) > 0

    def test_diamond_dependency(self) -> None:
        """Test diamond dependency pattern."""
        resolver = DependencyResolver()
        epics = [
            Epic(
                id="epic-1",
                title="Root Epic",
                description="Root node of diamond",
                dependencies=[],
            ),
            Epic(
                id="epic-2",
                title="Branch 1 Epic",
                description="First branch",
                dependencies=["epic-1"],
            ),
            Epic(
                id="epic-3",
                title="Branch 2 Epic",
                description="Second branch",
                dependencies=["epic-1"],
            ),
            Epic(
                id="epic-4",
                title="Merge Epic",
                description="Merges both branches",
                dependencies=["epic-2", "epic-3"],
            ),
        ]

        result = resolver.resolve(epics)

        # epic-1 must come before epic-2 and epic-3
        assert result.execution_order.index("epic-1") < result.execution_order.index(
            "epic-2"
        )
        assert result.execution_order.index("epic-1") < result.execution_order.index(
            "epic-3"
        )

        # epic-2 and epic-3 must come before epic-4
        assert result.execution_order.index("epic-2") < result.execution_order.index(
            "epic-4"
        )
        assert result.execution_order.index("epic-3") < result.execution_order.index(
            "epic-4"
        )

        # No cycles should be detected
        assert len(result.cycles_detected) == 0

    def test_get_dependencies_nonexistent(self) -> None:
        """Test getting dependencies for a non-existent epic."""
        resolver = DependencyResolver()
        resolver.resolve([])

        deps = resolver.get_dependencies("epic-999")

        assert deps == []

    def test_get_dependents_nonexistent(self) -> None:
        """Test getting dependents for a non-existent epic."""
        resolver = DependencyResolver()
        resolver.resolve([])

        dependents = resolver.get_dependents("epic-999")

        assert dependents == []
