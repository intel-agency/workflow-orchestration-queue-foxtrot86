# Architect Sub-Agent

> **Part of:** Phase 3 — Deep Orchestration Layer

## Overview

The Architect Sub-Agent is a specialized LangChain agent that analyzes "Application Plan" issues and decomposes them into "Epic" issues. This enables parallelizable development by breaking complex projects into manageable, dependency-aware units.

## Problem Solved

Manual decomposition of application plans into actionable work items is time-consuming and error-prone. The Architect automates this process while respecting dependencies between tasks.

## Architecture

### Core Components

```
src/agents/architect/
├── __init__.py           # Module exports
├── agent.py              # LangChain Architect agent
├── parser.py             # Plan parsing logic
├── generator.py          # Epic generation logic
├── resolver.py           # Dependency resolution
├── github_manager.py     # GitHub API operations
└── models.py             # Pydantic data models
```

### Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| `ArchitectAgent` | Orchestrates the decomposition workflow |
| `PlanParser` | Parses Application Plan markdown into structured data |
| `EpicGenerator` | Creates Epic definitions from parsed plan |
| `DependencyResolver` | Analyzes dependencies and determines execution order |
| `GitHubIssueManager` | Creates Epic issues via GitHub API |

## Usage

### Basic Usage

```python
import asyncio
from src.agents.architect import ArchitectAgent

async def main():
    # Initialize the agent
    agent = ArchitectAgent(github_token="ghp_...")
    
    # Decompose a plan into epics
    result = await agent.decompose_plan(
        repo_slug="owner/repo",
        plan_issue_number=42
    )
    
    if result.success:
        print(f"Created {len(result.created_issue_numbers)} epics:")
        for num in result.created_issue_numbers:
            print(f"  - #{num}")
    else:
        print(f"Failed: {result.error}")
    
    # Clean up
    await agent.close()

asyncio.run(main())
```

### Dry Run Mode

Test decomposition without creating GitHub issues:

```python
result = await agent.decompose_plan(
    repo_slug="owner/repo",
    plan_issue_number=42,
    dry_run=True  # Don't create issues
)

# Review generated epics
for epic in result.epics:
    print(f"{epic.id}: {epic.title}")
    print(f"  Dependencies: {epic.dependencies}")
```

### Custom Configuration

```python
from src.agents.architect.agent import ArchitectAgentConfig

config = ArchitectAgentConfig(
    model_name="glm-5",
    temperature=0.7,
    max_tokens=4000,
    min_epics=3,
    max_epics=5,
)

agent = ArchitectAgent(
    github_token="ghp_...",
    config=config
)
```

## Data Models

### ParsedPlan

Represents a parsed Application Plan:

```python
class ParsedPlan(BaseModel):
    source_issue_number: int
    source_issue_url: str
    title: str
    overview: str | None
    goals: list[str]
    scope: dict[str, list[str]]
    technical_requirements: list[str]
    user_stories: list[str]
    acceptance_criteria: list[str]
    implementation_sections: dict[str, str]
    risks: list[dict[str, str]]
    timeline: str | None
    raw_content: str
```

### Epic

Represents a generated Epic:

```python
class Epic(BaseModel):
    id: str                    # e.g., "epic-1"
    title: str
    description: str
    acceptance_criteria: list[str]
    dependencies: list[str]    # Epic IDs this depends on
    priority: int              # 1 = highest
    labels: list[str]
    status: EpicStatus
    estimated_effort: str | None
    metadata: dict[str, Any]
```

### Dependency

Represents a dependency relationship:

```python
class Dependency(BaseModel):
    source_epic_id: str
    target_epic_id: str
    dependency_type: DependencyType
    description: str | None
```

## Plan Parsing

### Supported Sections

The parser recognizes these markdown sections:

| Section | Aliases |
|---------|---------|
| Overview | Summary, Description, Background |
| Goals | Objectives |
| Scope | In-Scope, Scope & Boundaries |
| Technical Requirements | Tech Stack, Technology Stack, Architecture |
| User Stories | Use Cases, Features |
| Acceptance Criteria | Success Criteria, Definition of Done |
| Implementation Plan | Implementation, Development Plan |
| Risks | Risk Assessment, Risks & Mitigations |
| Timeline | Milestones, Schedule |

### Example Plan Format

```markdown
# My Application Plan

## Overview
This plan describes a web application for task management.

## Goals
- Build REST API
- Create web frontend
- Set up CI/CD

## Scope
### In-Scope
- User authentication
- Task CRUD operations

### Out-of-Scope
- Mobile application

## Technical Requirements
- Python 3.12+
- FastAPI
- PostgreSQL

## User Stories
- As a user, I want to create tasks
- As a user, I want to assign tasks

## Acceptance Criteria
- All endpoints return proper status codes
- Tests pass with 80% coverage

## Implementation Plan
### Story 1: Foundation
Set up project structure and dependencies.

### Story 2: Core Features
Implement main application logic.

### Story 3: Testing
Write comprehensive tests.

## Risks
| Risk | Mitigation |
|------|------------|
| Scope creep | Define clear boundaries |

## Timeline
- Week 1: Foundation
- Week 2-3: Core features
```

## Dependency Resolution

### Features

- **Topological Sorting**: Determines safe execution order
- **Cycle Detection**: Identifies circular dependencies
- **Parallelization Analysis**: Groups epics that can run concurrently
- **Validation**: Ensures all dependencies reference existing epics

### Example

```python
from src.agents.architect import DependencyResolver, Epic

resolver = DependencyResolver()

epics = [
    Epic(id="epic-1", title="Foundation", dependencies=[]),
    Epic(id="epic-2", title="Core", dependencies=["epic-1"]),
    Epic(id="epic-3", title="Integration", dependencies=["epic-1", "epic-2"]),
]

result = resolver.resolve(epics)

print(result.execution_order)      # ["epic-1", "epic-2", "epic-3"]
print(result.parallel_groups)      # [["epic-1"], ["epic-2"], ["epic-3"]]
print(result.cycles_detected)      # []
```

### Circular Dependency Detection

```python
epics = [
    Epic(id="epic-1", dependencies=["epic-3"]),
    Epic(id="epic-2", dependencies=["epic-1"]),
    Epic(id="epic-3", dependencies=["epic-2"]),
]

result = resolver.resolve(epics)

if result.cycles_detected:
    print("Circular dependencies found!")
    for cycle in result.cycles_detected:
        print(f"  Cycle: {' -> '.join(cycle)}")
```

## GitHub Integration

### Issue Creation

The agent creates Epic issues with:
- Proper title and description
- Acceptance criteria as task list
- Dependency information
- Labels (`epic`, `implementation:ready`, `orchestration:epic-ready`)
- Link back to parent Plan issue

### Task List Format

Generated epics are added to the Plan issue as a task list:

```markdown
## Generated Epics

- [ ] #101 - Foundation & Infrastructure
- [ ] #102 - Core Feature Implementation
- [ ] #103 - Integration & API
- [ ] #104 - Testing & Quality Assurance
```

## Testing

### Running Tests

```bash
# Run all architect tests
pytest tests/agents/architect/ -v

# Run specific test file
pytest tests/agents/architect/test_parser.py -v

# Run with coverage
pytest tests/agents/architect/ --cov=src/agents/architect
```

### Test Categories

| File | Coverage |
|------|----------|
| `test_parser.py` | Plan parsing, section extraction |
| `test_generator.py` | Epic generation, clustering |
| `test_resolver.py` | Dependency resolution, cycle detection |
| `test_github_manager.py` | GitHub API operations |
| `test_agent.py` | End-to-end agent behavior |

## Troubleshooting

### Common Issues

#### "GitHub token is required"

Set the `GITHUB_TOKEN` environment variable or pass it explicitly:

```python
agent = ArchitectAgent(github_token="ghp_...")
```

#### "Plan issue not found"

Verify:
- The issue number exists
- The repository slug is correct (`owner/repo` format)
- The token has `repo` scope

#### Circular Dependencies Detected

Review the generated epics and manually adjust dependencies:

```python
result = await agent.decompose_plan(..., dry_run=True)

if result.resolution.cycles_detected:
    # Review and fix manually
    for cycle in result.resolution.cycles_detected:
        print(f"Cycle: {cycle}")
```

### Debugging

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GITHUB_TOKEN` | GitHub Personal Access Token | Yes |
| `ZHIPU_API_KEY` | ZhipuAI API key for LLM | Optional |

### Agent Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `model_name` | `glm-5` | LLM model to use |
| `temperature` | `0.7` | LLM temperature |
| `max_tokens` | `4000` | Max tokens per response |
| `min_epics` | `3` | Minimum epics to generate |
| `max_epics` | `5` | Maximum epics to generate |

## API Reference

### ArchitectAgent

```python
class ArchitectAgent:
    def __init__(
        self,
        github_token: str | None = None,
        config: ArchitectAgentConfig | None = None,
    ) -> None: ...
    
    async def decompose_plan(
        self,
        repo_slug: str,
        plan_issue_number: int,
        dry_run: bool = False,
    ) -> DecompositionResult: ...
    
    async def close(self) -> None: ...
```

### DecompositionResult

```python
class DecompositionResult:
    success: bool
    plan: ParsedPlan | None
    epics: list[Epic]
    resolution: ResolutionResult | None
    created_issue_numbers: list[int]
    error: str | None
```

## Security

### Secret Scrubbing

All content posted to GitHub is automatically scrubbed for:
- GitHub tokens (`ghp_`, `ghs_`, `gho_`, `github_pat_`)
- OpenAI keys (`sk-`, `sk-proj-`)
- ZhipuAI keys
- Google/Gemini keys
- AWS keys
- Private keys (PEM format)
- Generic tokens and API keys

### Token Permissions

Required GitHub token scopes:
- `repo` - Create and manage issues
- `workflow` - Trigger workflows (optional)

## Related Documentation

- [Phase 3 Overview](../../plan_docs/phase3-overview.md)
- [Sentinel Orchestrator](../../src/sentinel/README.md)
- [GitHub Queue](../../src/queue/README.md)
