"""
Sentinel Status Feedback System.

This package provides the Automated Status Feedback system for the Sentinel
Orchestrator, providing real-time visibility into task execution through
GitHub Issue interactions.

Modules:
    config: Sentinel configuration and unique instance identification
    logging_config: Structured logging with sentinel_id (Epic 1.5, Story 2)
    orchestrator: Main Sentinel orchestrator class
    status_feedback: Main manager class for status feedback operations
    label_manager: GitHub Issue label transition management
    heartbeat: Async heartbeat loop for long-running tasks
    locking: Assign-then-verify locking pattern for race condition prevention

Features:
    - Unique instance identification via SENTINEL_ID (Epic 1.5)
    - Structured logging with sentinel_id in all messages (Epic 1.5, Story 2)
    - Label transition management (queued → in-progress → success/error)
    - Claim comments when Sentinel starts work
    - Heartbeat updates for long-running tasks
    - Contextual error labeling (infra vs impl failures)
    - Assign-then-verify locking for race condition prevention
    - Credential scrubbing for all posted content
"""

from src.sentinel.config import (
    SENTINEL_ID_ENV_VAR,
    SentinelConfig,
    get_or_create_sentinel_id,
    get_sentinel_id_short,
)
from src.sentinel.heartbeat import (
    HeartbeatLoop,
    format_elapsed_time,
    get_heartbeat_interval,
    run_heartbeat_sync,
    start_heartbeat,
)
from src.sentinel.label_manager import (
    AgentLabel,
    LabelManager,
    get_label_for_status,
)
from src.sentinel.logging_config import (
    SentinelJsonFormatter,
    SentinelLogContext,
    SentinelLogFilter,
    SentinelTextFormatter,
    configure_sentinel_logging,
    get_sentinel_logger,
)
from src.sentinel.locking import (
    LockAcquisitionError,
    LockManager,
    acquire_lock,
)
from src.sentinel.orchestrator import (
    Sentinel,
    create_sentinel,
)
from src.sentinel.status_feedback import (
    ErrorPhase,
    StatusFeedbackManager,
    create_status_feedback,
)

__all__ = [
    # Configuration & ID (Epic 1.5)
    "SENTINEL_ID_ENV_VAR",
    "SentinelConfig",
    "get_or_create_sentinel_id",
    "get_sentinel_id_short",
    # Logging (Epic 1.5, Story 2)
    "SentinelLogFilter",
    "SentinelJsonFormatter",
    "SentinelTextFormatter",
    "SentinelLogContext",
    "configure_sentinel_logging",
    "get_sentinel_logger",
    # Orchestrator (Epic 1.5)
    "Sentinel",
    "create_sentinel",
    # Label management
    "AgentLabel",
    "LabelManager",
    "get_label_for_status",
    # Locking
    "LockManager",
    "LockAcquisitionError",
    "acquire_lock",
    # Heartbeat
    "HeartbeatLoop",
    "get_heartbeat_interval",
    "format_elapsed_time",
    "start_heartbeat",
    "run_heartbeat_sync",
    # Status feedback
    "StatusFeedbackManager",
    "ErrorPhase",
    "create_status_feedback",
]
