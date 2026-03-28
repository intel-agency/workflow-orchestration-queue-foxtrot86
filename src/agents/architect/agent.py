"""
LangChain Architect Agent for Plan Decomposition.

This module provides the ArchitectAgent class that orchestrates the
decomposition of Application Plans into Epics using LangChain.
"""

import asyncio
import logging
import os
from typing import Any

from .generator import EpicGenerator
from .github_manager import GitHubIssueManager
from .models import Epic, EpicStatus, ParsedPlan
from .parser import PlanParser
from .resolver import DependencyResolver, ResolutionResult

logger = logging.getLogger(__name__)


class ArchitectAgentConfig:
    """Configuration for the Architect Agent."""

    def __init__(
        self,
        model_name: str = "glm-5",
        temperature: float = 0.7,
        max_tokens: int = 4000,
        min_epics: int = 3,
        max_epics: int = 5,
    ) -> None:
        """
        Initialize the agent configuration.

        Args:
            model_name: Name of the LLM model to use.
            temperature: Temperature for LLM responses.
            max_tokens: Maximum tokens for LLM responses.
            min_epics: Minimum number of epics to generate.
            max_epics: Maximum number of epics to generate.
        """
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.min_epics = min_epics
        self.max_epics = max_epics


class DecompositionResult:
    """Result of plan decomposition."""

    def __init__(
        self,
        success: bool,
        plan: ParsedPlan | None = None,
        epics: list[Epic] | None = None,
        resolution: ResolutionResult | None = None,
        created_issue_numbers: list[int] | None = None,
        error: str | None = None,
    ) -> None:
        """
        Initialize the decomposition result.

        Args:
            success: Whether the decomposition was successful.
            plan: The parsed plan (if successful).
            epics: The generated epics (if successful).
            resolution: The dependency resolution result (if successful).
            created_issue_numbers: List of created GitHub issue numbers.
            error: Error message (if unsuccessful).
        """
        self.success = success
        self.plan = plan
        self.epics = epics or []
        self.resolution = resolution
        self.created_issue_numbers = created_issue_numbers or []
        self.error = error


class ArchitectAgent:
    """
    LangChain-based Architect Agent for plan decomposition.

    This agent analyzes Application Plan issues and decomposes them
    into Epic issues with proper dependency relationships.

    The agent uses:
    - PlanParser to extract structured data from markdown plans
    - EpicGenerator to create well-structured Epic definitions
    - DependencyResolver to analyze and validate dependencies
    - GitHubIssueManager to create Epic issues via GitHub API

    Example:
        ```python
        async def main():
            agent = ArchitectAgent(github_token="ghp_...")
            result = await agent.decompose_plan(
                repo_slug="owner/repo",
                plan_issue_number=42
            )
            if result.success:
                print(f"Created {len(result.created_issue_numbers)} epics")

        asyncio.run(main())
        ```
    """

    # Prompt template for plan analysis
    ANALYSIS_PROMPT_TEMPLATE = """You are an expert software architect analyzing an Application Plan.

Your task is to decompose this plan into 3-5 logical Epic issues that can be
executed independently while respecting dependencies.

Plan Title: {title}

Plan Content:
{content}

Analyze the plan and identify:
1. Key work areas that can become separate Epics
2. Dependencies between these areas
3. Logical execution order
4. Acceptance criteria for each Epic

Respond with a structured breakdown of the Epics."""

    def __init__(
        self,
        github_token: str | None = None,
        config: ArchitectAgentConfig | None = None,
    ) -> None:
        """
        Initialize the Architect Agent.

        Args:
            github_token: GitHub Personal Access Token for API operations.
            config: Agent configuration. Uses defaults if not provided.
        """
        self.config = config or ArchitectAgentConfig()
        self._github_token = github_token or os.environ.get("GITHUB_TOKEN")

        # Initialize components
        self._parser = PlanParser()
        self._generator = EpicGenerator()
        self._resolver = DependencyResolver()
        self._github_manager: GitHubIssueManager | None = None

        # LLM client (lazy initialization)
        self._llm: Any = None

    @property
    def github_manager(self) -> GitHubIssueManager:
        """Get the GitHub issue manager, creating it if necessary."""
        if self._github_manager is None:
            if not self._github_token:
                raise ValueError(
                    "GitHub token is required. Pass it to the constructor or "
                    "set the GITHUB_TOKEN environment variable."
                )
            self._github_manager = GitHubIssueManager(token=self._github_token)
        return self._github_manager

    def _get_llm(self) -> Any:
        """
        Get the LLM client, creating it if necessary.

        Returns:
            LangChain LLM client instance.
        """
        if self._llm is None:
            # Try to load an LLM provider if available
            # Priority: ZhipuAI -> OpenAI -> MockLLM

            # Try ZhipuAI (if langchain-zhipu is installed)
            try:
                from langchain_zhipu import ChatZhipuAI  # type: ignore[import-not-found]

                api_key = os.environ.get("ZHIPU_API_KEY")
                if api_key:
                    self._llm = ChatZhipuAI(
                        model=self.config.model_name,
                        temperature=self.config.temperature,
                        max_tokens=self.config.max_tokens,
                    )
                    logger.info(
                        f"Initialized ZhipuAI LLM with model {self.config.model_name}"
                    )
            except ImportError:
                pass  # langchain-zhipu not available, try next provider

            # Try OpenAI (if langchain-openai is installed)
            if self._llm is None:
                try:
                    from langchain_openai import ChatOpenAI  # type: ignore[import-not-found]

                    api_key = os.environ.get("OPENAI_API_KEY")
                    if api_key:
                        self._llm = ChatOpenAI(
                            model="gpt-4",
                            temperature=self.config.temperature,
                            max_tokens=self.config.max_tokens,
                        )
                        logger.info("Initialized OpenAI LLM")
                except ImportError:
                    pass  # langchain-openai not available

            # Fallback to mock LLM if no provider available
            if self._llm is None:
                self._llm = MockLLM()
                logger.info("Using MockLLM (no LLM provider configured)")

        return self._llm

    async def decompose_plan(
        self,
        repo_slug: str,
        plan_issue_number: int,
        dry_run: bool = False,
    ) -> DecompositionResult:
        """
        Decompose an Application Plan into Epic issues.

        This is the main entry point for plan decomposition.

        Args:
            repo_slug: Repository in "owner/repo" format.
            plan_issue_number: GitHub issue number of the plan.
            dry_run: If True, don't create GitHub issues.

        Returns:
            DecompositionResult containing the decomposition outcome.
        """
        try:
            logger.info(
                f"Starting plan decomposition for issue #{plan_issue_number} in {repo_slug}"
            )

            # Step 1: Fetch the plan issue
            plan_issue = await self.github_manager.get_issue(
                repo_slug, plan_issue_number
            )
            if not plan_issue:
                return DecompositionResult(
                    success=False,
                    error=f"Plan issue #{plan_issue_number} not found",
                )

            # Step 2: Parse the plan
            plan = self._parser.parse(
                issue_number=plan_issue_number,
                issue_url=plan_issue.get("html_url", ""),
                markdown_content=plan_issue.get("body", ""),
            )
            logger.info(f"Parsed plan: {plan.title}")

            # Step 3: Analyze with LLM (optional enhancement)
            analysis = await self._analyze_plan_with_llm(plan)

            # Step 4: Generate epics
            epics = self._generator.generate(plan, target_repo=repo_slug)
            logger.info(f"Generated {len(epics)} epics")

            # Step 5: Resolve dependencies
            resolution = self._resolver.resolve(epics)
            if resolution.cycles_detected:
                logger.warning(
                    f"Circular dependencies detected: {resolution.cycles_detected}"
                )

            # Step 6: Create GitHub issues (unless dry run)
            created_issue_numbers: list[int] = []
            if not dry_run:
                created_issue_numbers = await self._create_epic_issues(
                    repo_slug=repo_slug,
                    epics=epics,
                    plan=plan,
                    plan_issue_number=plan_issue_number,
                )
                logger.info(f"Created {len(created_issue_numbers)} GitHub issues")

            # Step 7: Update plan issue with task list
            if not dry_run and created_issue_numbers:
                await self._update_plan_with_task_list(
                    repo_slug=repo_slug,
                    plan_issue_number=plan_issue_number,
                    epic_issue_numbers=created_issue_numbers,
                    epics=epics,
                )

            return DecompositionResult(
                success=True,
                plan=plan,
                epics=epics,
                resolution=resolution,
                created_issue_numbers=created_issue_numbers,
            )

        except Exception as e:
            logger.exception(f"Plan decomposition failed: {e}")
            return DecompositionResult(
                success=False,
                error=str(e),
            )

    async def _analyze_plan_with_llm(self, plan: ParsedPlan) -> str:
        """
        Use LLM to analyze the plan for additional insights.

        Args:
            plan: The parsed plan to analyze.

        Returns:
            Analysis string from the LLM.
        """
        try:
            llm = self._get_llm()

            prompt = self.ANALYSIS_PROMPT_TEMPLATE.format(
                title=plan.title,
                content=plan.raw_content[:3000],  # Limit content length
            )

            # Run LLM call in executor to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: llm.invoke(prompt),
            )

            return (
                str(response.content) if hasattr(response, "content") else str(response)
            )

        except Exception as e:
            logger.warning(f"LLM analysis failed, continuing without it: {e}")
            return ""

    async def _create_epic_issues(
        self,
        repo_slug: str,
        epics: list[Epic],
        plan: ParsedPlan,
        plan_issue_number: int,
    ) -> list[int]:
        """
        Create GitHub issues for all epics.

        Args:
            repo_slug: Repository in "owner/repo" format.
            epics: List of epics to create issues for.
            plan: Source plan for context.
            plan_issue_number: Issue number of the source plan.

        Returns:
            List of created issue numbers.
        """
        created_numbers: list[int] = []
        epic_issue_map: dict[str, int] = {}

        # Create issues in dependency order
        for epic in epics:
            body = self._generator.generate_github_issue_body(epic, plan)

            issue = await self.github_manager.create_issue(
                repo_slug=repo_slug,
                title=epic.title,
                body=body,
                labels=epic.labels,
            )

            if issue:
                issue_number = issue.get("number")
                if isinstance(issue_number, int):
                    created_numbers.append(issue_number)
                    epic_issue_map[epic.id] = issue_number
                    epic.status = EpicStatus.CREATED
                    logger.info(f"Created epic issue #{issue_number}: {epic.title}")

        # Add "Related To" links to parent plan
        if created_numbers:
            await self.github_manager.add_related_links(
                repo_slug=repo_slug,
                parent_issue_number=plan_issue_number,
                child_issue_numbers=created_numbers,
            )

        return created_numbers

    async def _update_plan_with_task_list(
        self,
        repo_slug: str,
        plan_issue_number: int,
        epic_issue_numbers: list[int],
        epics: list[Epic],
    ) -> None:
        """
        Update the plan issue with a task list of epic issues.

        Args:
            repo_slug: Repository in "owner/repo" format.
            plan_issue_number: Issue number of the source plan.
            epic_issue_numbers: List of created epic issue numbers.
            epics: List of epics with metadata.
        """
        # Build task list
        task_items = []
        for i, issue_num in enumerate(epic_issue_numbers):
            epic = epics[i] if i < len(epics) else None
            title = epic.title if epic else f"Epic {i + 1}"
            # Truncate title for task list
            short_title = title[:50] + "..." if len(title) > 50 else title
            task_items.append(f"- [ ] #{issue_num} - {short_title}")

        task_list = "\n".join(task_items)

        # Get current issue body
        issue = await self.github_manager.get_issue(repo_slug, plan_issue_number)
        if not issue:
            return

        current_body = issue.get("body", "")

        # Append task list section
        new_body = current_body.rstrip()
        if "---" in new_body:
            # Insert before the last ---
            parts = new_body.rsplit("---", 1)
            new_body = f"{parts[0]}\n\n---\n\n## Generated Epics\n\n{task_list}\n\n---{parts[1]}"
        else:
            new_body = f"{new_body}\n\n---\n\n## Generated Epics\n\n{task_list}"

        # Update the issue
        await self.github_manager.update_issue(
            repo_slug=repo_slug,
            issue_number=plan_issue_number,
            body=new_body,
        )

    async def close(self) -> None:
        """Close any open connections and release resources."""
        if self._github_manager:
            await self._github_manager.close()


class MockLLM:
    """
    Mock LLM for testing and fallback scenarios.

    This class provides a simple implementation that returns
    a placeholder response when no real LLM is available.
    """

    def invoke(self, prompt: str) -> Any:
        """
        Invoke the mock LLM.

        Args:
            prompt: The input prompt.

        Returns:
            A mock response.
        """

        class MockResponse:
            content = "Mock LLM analysis: The plan has been analyzed and is ready for decomposition."

        return MockResponse()
