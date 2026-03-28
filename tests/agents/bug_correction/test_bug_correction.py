"""Tests for the Bug Correction Agent module."""

import pytest

from src.agents.bug_correction import (
    FeedbackContextInjector,
    IterationLoopOrchestrator,
    StatusTransitionHandler,
)
from src.agents.bug_correction.feedback_injector import (
    CommentPriority,
    FeedbackContext,
    ReviewComment,
)
from src.agents.bug_correction.iteration_orchestrator import (
    IterationState,
    IterationStatus,
)
from src.agents.bug_correction.status_transition import (
    IssueStatus,
    StatusTransitionResult,
)


class TestStatusTransitionHandler:
    """Tests for StatusTransitionHandler."""

    def test_init_default_values(self):
        """Test handler initialization with default values."""
        handler = StatusTransitionHandler()
        assert handler.github_client is None
        assert handler.dry_run is False
        assert handler.audit_log == []

    def test_init_with_dry_run(self):
        """Test handler initialization with dry_run enabled."""
        handler = StatusTransitionHandler(dry_run=True)
        assert handler.dry_run is True

    def test_is_valid_transition(self):
        """Test transition validation logic."""
        handler = StatusTransitionHandler()

        # Valid transitions from success
        assert handler._is_valid_transition(
            IssueStatus.SUCCESS.value, IssueStatus.QUEUED.value
        )
        assert handler._is_valid_transition(
            IssueStatus.SUCCESS.value, IssueStatus.REVIEW.value
        )

        # Invalid transitions
        assert not handler._is_valid_transition(
            IssueStatus.SUCCESS.value, IssueStatus.IN_PROGRESS.value
        )

    def test_build_transition_comment(self):
        """Test comment generation for transitions."""
        handler = StatusTransitionHandler()

        comment = handler._build_transition_comment(
            from_status=IssueStatus.SUCCESS.value,
            to_status=IssueStatus.QUEUED.value,
            reason="PR review feedback received",
            pr_number=123,
            review_state="changes_requested",
        )

        assert "Status changed" in comment
        assert IssueStatus.SUCCESS.value in comment
        assert IssueStatus.QUEUED.value in comment
        assert "PR review feedback received" in comment
        assert "#123" in comment
        assert "changes_requested" in comment

    @pytest.mark.asyncio
    async def test_dry_run_transition(self):
        """Test dry run mode doesn't make actual changes."""
        handler = StatusTransitionHandler(dry_run=True)

        result = await handler.transition_to_queued(
            issue_number=123,
            repo_slug="owner/repo",
            reason="Test transition",
        )

        assert result.success is True
        assert result.to_status == IssueStatus.QUEUED.value
        assert result.metadata is not None
        assert result.metadata.get("dry_run") is True
        assert len(handler.audit_log) == 1


class TestFeedbackContextInjector:
    """Tests for FeedbackContextInjector."""

    def test_init_default_values(self):
        """Test injector initialization with default values."""
        injector = FeedbackContextInjector()
        assert injector.prioritize_blocking is True
        assert injector.include_diff_context is True
        assert injector.max_comment_length == 2000

    def test_calculate_priority_critical(self):
        """Test critical priority detection."""
        injector = FeedbackContextInjector()

        # Critical keywords
        assert (
            injector._calculate_priority(
                "This is a security vulnerability", "commented"
            )
            == CommentPriority.CRITICAL
        )
        assert (
            injector._calculate_priority("This is blocking the release", "commented")
            == CommentPriority.CRITICAL
        )

    def test_calculate_priority_high(self):
        """Test high priority detection."""
        injector = FeedbackContextInjector()

        # Changes requested state
        assert (
            injector._calculate_priority("Please fix this", "changes_requested")
            == CommentPriority.HIGH
        )

        # High priority keywords
        assert (
            injector._calculate_priority("This is important", "commented")
            == CommentPriority.HIGH
        )

    def test_calculate_priority_low(self):
        """Test low priority detection."""
        injector = FeedbackContextInjector()

        # Low priority keywords
        assert (
            injector._calculate_priority("nit: minor typo", "commented")
            == CommentPriority.LOW
        )
        assert (
            injector._calculate_priority("minor suggestion", "commented")
            == CommentPriority.LOW
        )

    def test_is_blocking(self):
        """Test blocking detection."""
        injector = FeedbackContextInjector()

        # Changes requested is always blocking
        assert injector._is_blocking("any text", "changes_requested") is True

        # Blocking keywords
        assert injector._is_blocking("This is a security issue", "commented") is True

        # Non-blocking
        assert injector._is_blocking("Nice work!", "approved") is False

    def test_extract_action_items(self):
        """Test action item extraction."""
        injector = FeedbackContextInjector()

        # Numbered list
        items = injector._extract_action_items(
            "1. Fix the bug\n2. Add tests\n3. Update docs"
        )
        assert len(items) == 3
        assert "Fix the bug" in items[0]

        # Checkbox items
        items = injector._extract_action_items(
            "- [ ] Implement feature\n* [ ] Add tests"
        )
        assert len(items) == 2

        # Imperative sentences
        items = injector._extract_action_items(
            "Fix the broken code and update the tests"
        )
        assert len(items) >= 1

    def test_generate_summary(self):
        """Test summary generation."""
        injector = FeedbackContextInjector()

        # Approved
        assert "approved" in injector._generate_summary(None, "approved").lower()

        # Changes requested
        assert (
            "changes" in injector._generate_summary(None, "changes_requested").lower()
        )

        # With body
        summary = injector._generate_summary(
            "This is a long review comment about the code quality.", "commented"
        )
        assert "long review comment" in summary

    def test_sort_comments_by_priority(self):
        """Test comment sorting by priority."""
        injector = FeedbackContextInjector()

        comments = [
            ReviewComment(id=1, body="low priority", priority=CommentPriority.LOW),
            ReviewComment(id=2, body="critical", priority=CommentPriority.CRITICAL),
            ReviewComment(id=3, body="medium", priority=CommentPriority.MEDIUM),
            ReviewComment(id=4, body="high", priority=CommentPriority.HIGH),
        ]

        sorted_comments = injector._sort_comments_by_priority(comments)

        assert sorted_comments[0].priority == CommentPriority.CRITICAL
        assert sorted_comments[1].priority == CommentPriority.HIGH
        assert sorted_comments[2].priority == CommentPriority.MEDIUM
        assert sorted_comments[3].priority == CommentPriority.LOW

    def test_format_comment(self):
        """Test comment formatting."""
        injector = FeedbackContextInjector()

        comment = ReviewComment(
            id=1,
            body="This is a test comment",
            path="src/main.py",
            author="reviewer",
            priority=CommentPriority.HIGH,
        )

        formatted = injector._format_comment(comment, 1)

        assert "Comment 1" in formatted
        assert "HIGH" in formatted
        assert "src/main.py" in formatted
        assert "@reviewer" in formatted
        assert "This is a test comment" in formatted

    def test_build_prompt_context(self):
        """Test full prompt context building."""
        injector = FeedbackContextInjector()

        feedback = FeedbackContext(
            pr_number=123,
            pr_title="Test PR",
            pr_url="https://github.com/owner/repo/pull/123",
            reviewer="testuser",
            review_state="changes_requested",
            comments=[
                ReviewComment(
                    id=1,
                    body="Please fix this",
                    priority=CommentPriority.HIGH,
                )
            ],
            action_items=["Fix the bug"],
            iteration_number=1,
        )

        context = injector.build_prompt_context(feedback)

        assert "#123" in context
        assert "Test PR" in context
        assert "@testuser" in context
        assert "changes_requested" in context
        assert "Please fix this" in context
        assert "Fix the bug" in context


class TestIterationLoopOrchestrator:
    """Tests for IterationLoopOrchestrator."""

    def test_init_default_values(self):
        """Test orchestrator initialization."""
        orchestrator = IterationLoopOrchestrator()
        assert orchestrator.default_max_iterations == 5
        assert orchestrator.statuses == {}

    def test_init_custom_max_iterations(self):
        """Test orchestrator with custom max iterations."""
        orchestrator = IterationLoopOrchestrator(max_iterations=3)
        assert orchestrator.default_max_iterations == 3

    def test_start_iteration(self):
        """Test starting a new iteration."""
        orchestrator = IterationLoopOrchestrator()

        status = orchestrator.start_iteration(
            issue_number=123,
            pr_number=456,
        )

        assert status.issue_number == 123
        assert status.state == IterationState.IN_PROGRESS
        assert status.current_iteration == 1
        assert len(status.iterations) == 1
        assert status.iterations[0].pr_number == 456

    def test_start_multiple_iterations(self):
        """Test multiple iterations on the same issue."""
        orchestrator = IterationLoopOrchestrator()

        # First iteration
        orchestrator.start_iteration(issue_number=123, pr_number=456)

        # Second iteration
        status = orchestrator.start_iteration(issue_number=123, pr_number=457)

        assert status.current_iteration == 2
        assert len(status.iterations) == 2

    def test_handle_review_approved(self):
        """Test handling an approved review."""
        orchestrator = IterationLoopOrchestrator()
        orchestrator.start_iteration(issue_number=123, pr_number=456)

        status = orchestrator.handle_review(
            issue_number=123,
            review_state="approved",
            feedback_summary="LGTM!",
        )

        assert status.state == IterationState.APPROVED

    def test_handle_review_changes_requested(self):
        """Test handling a changes requested review."""
        orchestrator = IterationLoopOrchestrator()
        orchestrator.start_iteration(issue_number=123, pr_number=456)

        status = orchestrator.handle_review(
            issue_number=123,
            review_state="changes_requested",
            feedback_summary="Please fix X",
        )

        assert status.state == IterationState.PENDING_REVIEW

    def test_max_iterations_reached(self):
        """Test max iterations limit."""
        orchestrator = IterationLoopOrchestrator(max_iterations=2)

        # First iteration
        orchestrator.start_iteration(issue_number=123, pr_number=456)
        orchestrator.handle_review(issue_number=123, review_state="changes_requested")

        # Second iteration
        orchestrator.start_iteration(issue_number=123, pr_number=457)
        status = orchestrator.handle_review(
            issue_number=123, review_state="changes_requested"
        )

        assert status.state == IterationState.MAX_ITERATIONS_REACHED

    def test_is_iteration_allowed(self):
        """Test iteration permission check."""
        orchestrator = IterationLoopOrchestrator(max_iterations=2)

        # No status - allowed
        assert orchestrator.is_iteration_allowed(123) is True

        # First iteration
        orchestrator.start_iteration(issue_number=123, pr_number=456)
        assert orchestrator.is_iteration_allowed(123) is True

        # After first iteration
        orchestrator.handle_review(issue_number=123, review_state="changes_requested")

        # Second iteration
        orchestrator.start_iteration(issue_number=123, pr_number=457)
        assert orchestrator.is_iteration_allowed(123) is False

    def test_get_iteration_count(self):
        """Test getting iteration count."""
        orchestrator = IterationLoopOrchestrator()

        # Not tracked
        assert orchestrator.get_iteration_count(123) == 0

        # After starting
        orchestrator.start_iteration(issue_number=123, pr_number=456)
        assert orchestrator.get_iteration_count(123) == 1

    def test_complete_loop(self):
        """Test completing the loop."""
        orchestrator = IterationLoopOrchestrator()
        orchestrator.start_iteration(issue_number=123, pr_number=456)

        status = orchestrator.complete_loop(123)

        assert status.state == IterationState.APPROVED

    def test_reset_loop(self):
        """Test resetting the loop."""
        orchestrator = IterationLoopOrchestrator()
        orchestrator.start_iteration(issue_number=123, pr_number=456)

        orchestrator.reset_loop(123)

        assert orchestrator.get_status(123) is None
        assert orchestrator.get_iteration_count(123) == 0

    def test_get_summary(self):
        """Test getting iteration summary."""
        orchestrator = IterationLoopOrchestrator()
        orchestrator.start_iteration(issue_number=123, pr_number=456)

        summary = orchestrator.get_summary(123)

        assert summary["tracked"] is True
        assert summary["current_iteration"] == 1
        assert summary["max_iterations"] == 5

    def test_get_all_active_iterations(self):
        """Test getting all active iterations."""
        orchestrator = IterationLoopOrchestrator()

        orchestrator.start_iteration(issue_number=123, pr_number=456)
        orchestrator.start_iteration(issue_number=456, pr_number=789)
        orchestrator.handle_review(issue_number=456, review_state="approved")

        active = orchestrator.get_all_active_iterations()

        assert len(active) == 1
        assert active[0].issue_number == 123

    def test_set_error(self):
        """Test setting error state."""
        orchestrator = IterationLoopOrchestrator()

        status = orchestrator.set_error(123, "Something went wrong")

        assert status.state == IterationState.ERROR
        assert status.error_message == "Something went wrong"

    def test_record_changes(self):
        """Test recording changes made."""
        orchestrator = IterationLoopOrchestrator()
        orchestrator.start_iteration(issue_number=123, pr_number=456)

        status = orchestrator.record_changes(123, "Fixed the bug")

        assert status.iterations[-1].changes_made == "Fixed the bug"
