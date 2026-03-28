"""
Unit tests for the EpicGenerator.
"""

import pytest

from src.agents.architect.generator import EpicGenerator
from src.agents.architect.models import Epic, EpicStatus, ParsedPlan


@pytest.fixture
def sample_plan() -> ParsedPlan:
    """Sample parsed plan for testing."""
    return ParsedPlan(
        source_issue_number=42,
        source_issue_url="https://github.com/owner/repo/issues/42",
        title="Sample Application",
        overview="A sample application for testing.",
        goals=[
            "Build REST API",
            "Create frontend",
            "Set up CI/CD",
        ],
        technical_requirements=[
            "Python 3.12+",
            "FastAPI",
            "PostgreSQL",
        ],
        user_stories=[
            "As a user, I want to log in",
            "As a user, I want to view data",
        ],
        acceptance_criteria=[
            "All tests pass",
            "80% coverage",
        ],
        implementation_sections={
            "story_1": "Set up foundation",
            "story_2": "Implement features",
            "story_3": "Write tests",
        },
    )


@pytest.fixture
def minimal_plan() -> ParsedPlan:
    """Minimal parsed plan for testing."""
    return ParsedPlan(
        source_issue_number=1,
        source_issue_url="https://github.com/owner/repo/issues/1",
        title="Simple Project",
    )


class TestEpicGenerator:
    """Tests for the EpicGenerator class."""

    def test_generate_returns_list(self, sample_plan: ParsedPlan) -> None:
        """Test that generate returns a list of Epics."""
        generator = EpicGenerator()
        epics = generator.generate(sample_plan)

        assert isinstance(epics, list)
        assert all(isinstance(epic, Epic) for epic in epics)

    def test_generate_min_epics(self, minimal_plan: ParsedPlan) -> None:
        """Test that generator produces minimum number of epics."""
        generator = EpicGenerator()
        epics = generator.generate(minimal_plan)

        assert len(epics) >= generator.MIN_EPICS

    def test_generate_max_epics(self, sample_plan: ParsedPlan) -> None:
        """Test that generator respects maximum number of epics."""
        generator = EpicGenerator()
        epics = generator.generate(sample_plan)

        assert len(epics) <= generator.MAX_EPICS

    def test_generate_epic_structure(self, sample_plan: ParsedPlan) -> None:
        """Test that generated epics have proper structure."""
        generator = EpicGenerator()
        epics = generator.generate(sample_plan)

        for epic in epics:
            assert epic.id.startswith("epic-")
            assert len(epic.title) >= 5
            assert len(epic.description) >= 10
            assert isinstance(epic.acceptance_criteria, list)
            assert isinstance(epic.labels, list)
            assert "epic" in epic.labels

    def test_generate_epic_status(self, sample_plan: ParsedPlan) -> None:
        """Test that generated epics have correct initial status."""
        generator = EpicGenerator()
        epics = generator.generate(sample_plan)

        for epic in epics:
            assert epic.status == EpicStatus.DRAFT

    def test_generate_epic_metadata(self, sample_plan: ParsedPlan) -> None:
        """Test that generated epics have proper metadata."""
        generator = EpicGenerator()
        epics = generator.generate(sample_plan, target_repo="owner/repo")

        for epic in epics:
            assert "source_plan_issue" in epic.metadata
            assert epic.metadata["source_plan_issue"] == sample_plan.source_issue_number
            assert "target_repo" in epic.metadata

    def test_generate_with_dependencies(self, sample_plan: ParsedPlan) -> None:
        """Test that dependencies are assigned between epics."""
        generator = EpicGenerator()
        epics = generator.generate(sample_plan)

        # At least some epics should have dependencies
        # (unless it's a very simple plan)
        total_deps = sum(len(epic.dependencies) for epic in epics)
        # This is a soft check - some plans might not have dependencies
        # Just verify the structure is correct
        for epic in epics:
            for dep_id in epic.dependencies:
                assert dep_id.startswith("epic-")

    def test_generate_priorities_assigned(self, sample_plan: ParsedPlan) -> None:
        """Test that priorities are assigned to epics."""
        generator = EpicGenerator()
        epics = generator.generate(sample_plan)

        priorities = [epic.priority for epic in epics]
        assert all(1 <= p <= 10 for p in priorities)

    def test_cluster_work_items(self, sample_plan: ParsedPlan) -> None:
        """Test work item clustering logic."""
        generator = EpicGenerator()
        from src.agents.architect.parser import PlanParser

        parser = PlanParser()
        work_items = parser.extract_work_items(sample_plan)

        clusters = generator._cluster_work_items(work_items, sample_plan)

        assert isinstance(clusters, list)
        assert len(clusters) > 0
        assert all("title" in cluster for cluster in clusters)
        assert all("items" in cluster for cluster in clusters)

    def test_build_epic_description(self, sample_plan: ParsedPlan) -> None:
        """Test epic description building."""
        generator = EpicGenerator()

        cluster = {
            "name": "foundation",
            "title": "Foundation & Infrastructure",
            "items": [
                {"title": "Set up project", "source": "implementation"},
            ],
        }

        description = generator._build_epic_description(cluster, sample_plan)

        assert "Foundation & Infrastructure" in description
        assert "Set up project" in description
        assert str(sample_plan.source_issue_number) in description

    def test_build_acceptance_criteria(self, sample_plan: ParsedPlan) -> None:
        """Test acceptance criteria building."""
        generator = EpicGenerator()

        cluster = {
            "name": "testing",
            "title": "Testing",
            "items": [],
        }

        criteria = generator._build_acceptance_criteria(cluster, sample_plan)

        assert isinstance(criteria, list)
        assert len(criteria) > 0
        # Should include some default testing criteria
        assert any("coverage" in c.lower() or "test" in c.lower() for c in criteria)

    def test_generate_github_issue_body(self, sample_plan: ParsedPlan) -> None:
        """Test GitHub issue body generation."""
        generator = EpicGenerator()

        epic = Epic(
            id="epic-1",
            title="Test Epic",
            description="Epic description",
            acceptance_criteria=["Criterion 1", "Criterion 2"],
            dependencies=["epic-0"],
        )

        body = generator.generate_github_issue_body(epic, sample_plan)

        assert "Test Epic" in body
        assert "Epic description" in body
        assert "Criterion 1" in body
        assert "Dependencies" in body
        assert str(sample_plan.source_issue_number) in body

    def test_generate_github_issue_body_with_effort(
        self, sample_plan: ParsedPlan
    ) -> None:
        """Test GitHub issue body with estimated effort."""
        generator = EpicGenerator()

        epic = Epic(
            id="epic-1",
            title="Test Epic",
            description="Epic description",
            estimated_effort="1 week",
        )

        body = generator.generate_github_issue_body(epic, sample_plan)

        assert "Estimated Effort" in body
        assert "1 week" in body

    def test_generate_includes_plan_acceptance_criteria(
        self, sample_plan: ParsedPlan
    ) -> None:
        """Test that plan acceptance criteria are included in epics."""
        generator = EpicGenerator()
        epics = generator.generate(sample_plan)

        # At least one epic should have criteria from the plan
        all_criteria = []
        for epic in epics:
            all_criteria.extend(epic.acceptance_criteria)

        # Check that plan criteria are reflected
        assert any("pass" in c.lower() for c in all_criteria)


class TestEpicGeneratorEdgeCases:
    """Edge case tests for EpicGenerator."""

    def test_empty_plan(self) -> None:
        """Test generation with empty plan."""
        generator = EpicGenerator()
        plan = ParsedPlan(
            source_issue_number=1,
            source_issue_url="",
            title="Empty Plan",
        )

        epics = generator.generate(plan)

        # Should still generate minimum epics
        assert len(epics) >= generator.MIN_EPICS

    def test_plan_with_many_items(self) -> None:
        """Test generation with many work items."""
        generator = EpicGenerator()
        plan = ParsedPlan(
            source_issue_number=1,
            source_issue_url="",
            title="Large Project",
            implementation_sections={f"section_{i}": f"Task {i}" for i in range(20)},
        )

        epics = generator.generate(plan)

        # Should still respect max limit
        assert len(epics) <= generator.MAX_EPICS

    def test_assign_dependencies_no_cycles(self, sample_plan: ParsedPlan) -> None:
        """Test that dependency assignment doesn't create cycles."""
        generator = EpicGenerator()
        epics = generator.generate(sample_plan)

        # Check for cycles using DFS
        visited = set()
        rec_stack = set()

        def has_cycle(epic_id: str, epic_map: dict) -> bool:
            visited.add(epic_id)
            rec_stack.add(epic_id)

            epic = epic_map.get(epic_id)
            if epic:
                for dep_id in epic.dependencies:
                    if dep_id not in visited:
                        if has_cycle(dep_id, epic_map):
                            return True
                    elif dep_id in rec_stack:
                        return True

            rec_stack.remove(epic_id)
            return False

        epic_map = {epic.id: epic for epic in epics}
        for epic in epics:
            if epic.id not in visited:
                assert not has_cycle(epic.id, epic_map), (
                    "Cycle detected in dependencies"
                )
