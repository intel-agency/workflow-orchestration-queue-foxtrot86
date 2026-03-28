"""
Architect Sub-Agent Module.

This module provides the Architect Sub-Agent, a specialized LangChain agent
that analyzes "Application Plan" issues and decomposes them into "Epic" issues.

Components:
- ArchitectAgent: LangChain agent that orchestrates plan decomposition
- PlanParser: Parses Application Plan markdown into structured data
- EpicGenerator: Creates Epic issue content from parsed plan
- DependencyResolver: Analyzes and validates Epic dependencies
- GitHubIssueManager: Handles GitHub API operations for Epic creation
"""

from .agent import ArchitectAgent
from .generator import EpicGenerator
from .github_manager import GitHubIssueManager
from .models import (
    Dependency,
    DependencyType,
    Epic,
    EpicStatus,
    ParsedPlan,
    PlanSection,
)
from .parser import PlanParser
from .resolver import DependencyResolver, ResolutionResult

__all__ = [
    # Agent
    "ArchitectAgent",
    # Models
    "ParsedPlan",
    "PlanSection",
    "Epic",
    "EpicStatus",
    "Dependency",
    "DependencyType",
    # Components
    "PlanParser",
    "EpicGenerator",
    "DependencyResolver",
    "ResolutionResult",
    "GitHubIssueManager",
]
