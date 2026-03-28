# Sentinel Orchestrator

AI-powered workflow orchestration system.

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

```python
from src.models import WorkItem, TaskType, WorkItemStatus

item = WorkItem(
    id="123",
    source_url="https://github.com/owner/repo/issues/123",
    context_body="Implement feature X",
    target_repo_slug="owner/repo",
    task_type=TaskType.IMPLEMENT,
)
```

## Testing

```bash
pytest
```
