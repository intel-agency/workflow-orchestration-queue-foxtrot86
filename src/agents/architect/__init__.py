"""
Architect Agent module.

The Architect Sub-Agent is a specialized LangChain agent that analyzes
"Application Plan" issues and decomposes them into "Epic" issues.
This enables parallelizable development by breaking complex projects
into manageable, dependency-aware units.
"""

from src.agents.architect.agent import ArchitectAgent
from src.agents.architect.prompts import (
    ARCHITECT_SYSTEM_PROMPT,
    PLAN_ANALYSIS_PROMPT,
    EPIC_GENERATION_PROMPT,
)

__all__ = [
    "ArchitectAgent",
    "ARCHITECT_SYSTEM_PROMPT",
    "PLAN_ANALYSIS_PROMPT",
    "EPIC_GENERATION_PROMPT",
]
