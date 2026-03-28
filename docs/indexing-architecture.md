# Indexing Architecture

This document describes the proactive workspace indexing system implemented in Epic 3.3.

## Overview

The proactive workspace indexing system ensures that the AI orchestrator always has an up-to-date vector-indexed view of the codebase. This enables faster and more accurate responses when agents need to search or analyze code.

## Architecture

### Components

```
src/agents/
├── indexing/
│   ├── __init__.py          # Module exports
│   ├── models.py             # Data models (IndexStatus, IndexConfig, etc.)
│   └── index_manager.py      # IndexManager class
├── sentinel/
│   ├── __init__.py           # Module exports
│   └── indexing_trigger.py   # SentinelIndexingTrigger, SentinelIndexingHook
└── worker/
    ├── __init__.py           # Module exports
    └── index_verification.py # IndexVerifier, WorkerVerificationHook
```

### Sentinel Agent (Indexing Trigger)

The Sentinel agent is responsible for triggering proactive indexing after repository operations:

- **SentinelIndexingTrigger**: Core class that triggers indexing after clone operations
- **SentinelIndexingHook**: Hook interface for integrating into workflows

```python
from src.agents.sentinel import SentinelIndexingTrigger

trigger = SentinelIndexingTrigger()
result = await trigger.trigger_after_clone()

if result.success:
    print(f"Index ready in {result.duration_seconds}s")
```

### Worker Agent (Index Verification)

The Worker agent verifies index presence and freshness before generation tasks:

- **IndexVerifier**: Core class that verifies index readiness
- **WorkerVerificationHook**: Hook interface for pre-task verification

```python
from src.agents.worker import IndexVerifier

verifier = IndexVerifier()
result = await verifier.verify_before_task()

if result.can_proceed:
    print("Index verified, proceeding with task")
else:
    print(f"Cannot proceed: {result.message}")
```

## Data Models

### IndexStatus

Represents the current state of the workspace index:

| Field | Type | Description |
|-------|------|-------------|
| is_present | bool | Whether index files exist |
| is_fresh | bool | Whether index is within freshness threshold |
| last_updated | datetime | Timestamp of last update |
| error_message | str | Error if indexing failed |
| status_level | IndexStatusLevel | Computed: HEALTHY, STALE, MISSING, or ERROR |

### IndexConfig

Configuration for indexing operations:

| Field | Default | Description |
|-------|---------|-------------|
| freshness_threshold_seconds | 3600 | Maximum age before stale |
| warning_threshold_seconds | 1800 | Age for warning logs |
| max_retries | 3 | Retry attempts |
| retry_delay_seconds | 5.0 | Initial retry delay |
| allow_stale_index | True | Allow proceeding with stale index |
| fallback_on_failure | True | Allow non-indexed mode |

### VerificationResult

Result of Worker verification:

| Field | Type | Description |
|-------|------|-------------|
| action | VerificationAction | PROCEED, PROCEED_WITH_WARNING, WAIT, or BLOCK |
| can_proceed | bool | Whether task can proceed |
| message | str | Human-readable status |
| freshness_result | IndexFreshnessResult | Detailed freshness check |

## Workflow Integration

### Post-Clone Hook

The Sentinel agent integrates after repository clone:

```python
from src.agents.sentinel import SentinelIndexingHook

hook = SentinelIndexingHook()

# After clone completes
result = await hook.on_clone_complete(
    repo_url="https://github.com/owner/repo",
    branch="main"
)
```

### Pre-Task Hook

The Worker agent integrates before generation tasks:

```python
from src.agents.worker import WorkerVerificationHook

hook = WorkerVerificationHook()

# Before code generation
result = await hook.before_code_generation()

# Before analysis (strict mode)
result = await hook.before_analysis_task()
```

## Error Handling

### Retry Logic

The IndexManager implements exponential backoff retry:

1. First attempt
2. Wait `retry_delay_seconds`
3. Second attempt
4. Wait `retry_delay_seconds * backoff_multiplier`
5. Third attempt
6. Return failure if all attempts fail

### Fallback Mode

When `fallback_on_failure=True`:

- Missing index: Proceed with warning
- Indexing failure: Proceed with warning
- Stale index (if allowed): Proceed with warning

When `fallback_on_failure=False`:

- Missing index: Block task
- Indexing failure: Block task
- Stale index (strict mode): Block task

## Status Reporting

Both agents provide status reporting for the orchestration layer:

```python
# Sentinel status report
report = await trigger.report_status()
# Returns: { "agent": "sentinel", "status": "healthy", ... }

# Worker status report
report = await verifier.report_status()
# Returns: { "agent": "worker", "status": "healthy", ... }
```

## Configuration

### Environment Variables

- `GITHUB_TOKEN`: GitHub API token for fetching remote indices

### Script Integration

The system leverages the existing `scripts/update-remote-indices.ps1` script:

- Fetches remote instruction modules
- Updates local index files
- Reports changes

## Metrics

Key metrics for monitoring:

- **Indexing latency**: Time to complete indexing
- **Index freshness**: Age of current index
- **Retry rate**: Percentage of operations requiring retries
- **Fallback rate**: Percentage of operations using fallback mode

## Troubleshooting

### Index Always Stale

1. Check `freshness_threshold_seconds` configuration
2. Verify system clock is accurate
3. Check for file system issues

### Indexing Fails

1. Verify PowerShell (`pwsh`) is installed
2. Check `GITHUB_TOKEN` is set
3. Review script logs for errors

### Worker Blocks on Missing Index

1. Set `fallback_on_failure=True` to allow fallback mode
2. Trigger manual indexing first
3. Check index directory permissions
