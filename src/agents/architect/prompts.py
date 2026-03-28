"""
Prompt templates for the Architect Agent.

This module defines the prompt templates used by the Architect agent
for plan analysis and epic generation tasks.
"""

from string import Template

# System prompt that defines the Architect's role and capabilities
ARCHITECT_SYSTEM_PROMPT = """You are the Architect Sub-Agent, a specialized AI assistant that analyzes Application Plan issues and decomposes them into actionable Epic issues.

## Your Role

You break down complex application plans into 3-5 manageable Epic issues that can be developed in parallel when possible. You ensure proper dependency ordering and clear acceptance criteria.

## Capabilities

1. **Plan Analysis**: Parse and understand Application Plan markdown documents
2. **Epic Generation**: Create well-structured Epic issues with clear scope
3. **Dependency Analysis**: Identify and document dependencies between Epics
4. **Parallelization**: Determine which Epics can be developed concurrently

## Guidelines

- Each Epic should be completable in 1-2 weeks
- Epics should have minimal dependencies when possible
- Always include clear acceptance criteria
- Use GitHub-flavored markdown in all outputs
- Link child Epics to parent Plans using "Related To" syntax
- Apply dependency-aware labeling (blocked Epics should not be queued)

## Output Format

When generating Epics, always structure them as:
1. Title: Clear, action-oriented Epic name
2. Overview: Brief description of the Epic's purpose
3. Goals: Specific objectives to achieve
4. Tasks: Checkable implementation items
5. Acceptance Criteria: Verifiable completion conditions
6. Dependencies: Links to blocking Epics (if any)
"""

# Template for analyzing Application Plans
PLAN_ANALYSIS_PROMPT = Template("""Analyze the following Application Plan and extract the key information needed to generate Epic issues.

## Application Plan

$plan_content

## Analysis Tasks

Please provide:
1. **Overview Summary**: A 2-3 sentence summary of what this plan aims to build
2. **Key Components**: List the main technical components or features
3. **Suggested Epics**: Recommend 3-5 Epics that would implement this plan
4. **Dependencies**: Identify which Epics depend on others
5. **Parallelization Opportunities**: Note which Epics could be developed concurrently

Format your response as structured markdown.
""")

# Template for generating Epic issues
EPIC_GENERATION_PROMPT = Template("""Generate a complete Epic issue based on the following analysis.

## Epic Details

- **Title**: $epic_title
- **Parent Plan**: #$plan_issue_number
- **Component**: $component

## Epic Scope

$scope_description

## Requirements

Generate a complete Epic issue with:
1. Title prefixed with "Epic: "
2. Overview section with parent plan reference
3. Goals section with checkable items
4. Tasks section with implementation checklist
5. Acceptance Criteria section
6. Dependencies section (if any)
7. Risk Mitigation section

Use GitHub-flavored markdown formatting.
""")
