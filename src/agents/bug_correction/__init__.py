"""
Bug Correction Sub-Agent Module.

This module implements the autonomous bug correction loop for the Sentinel
Orchestration system. It handles PR review feedback and automatically
re-queues work items for iterative refinement until approval.

Components:
- StatusTransitionHandler: Transitions issue status based on PR review events
- FeedbackContextInjector: Injects reviewer feedback into Worker prompts
- IterationLoopOrchestrator: Manages the iteration cycle until PR approval
"""

from .feedback_injector import FeedbackContextInjector
from .iteration_orchestrator import IterationLoopOrchestrator
from .status_transition import StatusTransitionHandler

__all__ = [
    "StatusTransitionHandler",
    "FeedbackContextInjector",
    "IterationLoopOrchestrator",
]
