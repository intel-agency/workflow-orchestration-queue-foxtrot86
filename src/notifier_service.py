"""
FastAPI Webhook Receiver Service ("The Ear") for the Sentinel Orchestrator.

This module implements a hardened FastAPI application that receives GitHub webhook
events, validates HMAC signatures, parses payloads, and maps events to WorkItems
for the execution queue.

Security Features:
- HMAC-SHA256 signature verification using hmac.compare_digest()
- No secret leakage in error responses
- Environment variable validation at startup

Performance:
- Responds within GitHub's 10-second timeout (returns 202 immediately)
- Async processing for non-blocking operation

Usage:
    Run with uvicorn:
    $ uvicorn src.notifier_service:app --host 0.0.0.0 --port 8080

Environment Variables:
    GITHUB_WEBHOOK_SECRET: Secret token for HMAC signature verification
"""

import hashlib
import hmac
import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from pydantic_settings import BaseSettings

from src.models.github_events import (
    GitHubEventType,
    GitHubIssueCommentEvent,
    GitHubIssuesEvent,
    GitHubPingEvent,
    IssueAction,
    parse_webhook_payload,
)
from src.models.work_item import TaskType, WorkItem, WorkItemStatus

# Configure structured JSON logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("notifier_service")

# Context variable for request correlation
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

# Sentinel ID for correlation
SENTINEL_ID = os.environ.get("SENTINEL_ID", "notifier-service")


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Environment variables are validated at startup to fail fast
    if required configuration is missing.
    """

    github_webhook_secret: str = ""
    environment: str = "development"
    log_level: str = "INFO"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

    def validate_webhook_secret(self) -> None:
        """
        Validate that the webhook secret is configured.

        Raises:
            ValueError: If the secret is not configured.
        """
        if not self.github_webhook_secret:
            raise ValueError(
                "GITHUB_WEBHOOK_SECRET environment variable is required. "
                "Set it to the secret configured in your GitHub webhook settings."
            )


# Initialize settings
settings = Settings()

# Validate webhook secret at startup (fail fast)
try:
    settings.validate_webhook_secret()
except ValueError as e:
    logger.error(f"Configuration error: {e}")
    # In production, we want to fail fast; in testing, we may allow missing secret
    if os.environ.get("ALLOW_MISSING_WEBHOOK_SECRET", "").lower() != "true":
        raise


# ============================================================================
# Application Lifecycle
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager for startup and shutdown events.

    Handles initialization and cleanup tasks for the FastAPI application.
    """
    # Startup
    logger.info(
        "Notifier service starting up",
        extra={
            "environment": settings.environment,
            "sentinel_id": SENTINEL_ID,
        },
    )
    yield
    # Shutdown
    logger.info(
        "Notifier service shutting down",
        extra={
            "sentinel_id": SENTINEL_ID,
        },
    )


# Create FastAPI application
app = FastAPI(
    title="Sentinel Orchestrator Webhook Receiver",
    description="Secure webhook endpoint for GitHub events",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ============================================================================
# Exception Handlers - Story 2.1.5: Error Handling & Response Standards
# ============================================================================


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """
    Handle request validation errors.

    Returns a 400 Bad Request without exposing internal details.
    """
    correlation_id = correlation_id_var.get()
    logger.error(
        "Request validation failed",
        extra={
            "correlation_id": correlation_id,
            "error_type": "validation_error",
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Bad Request",
            "message": "Invalid request format",
            "correlation_id": correlation_id,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """
    Handle HTTP exceptions with structured responses.

    Never includes sensitive information in error responses.
    """
    correlation_id = correlation_id_var.get()
    logger.error(
        f"HTTP exception: {exc.status_code}",
        extra={
            "correlation_id": correlation_id,
            "error_type": "http_exception",
            "status_code": exc.status_code,
            "path": request.url.path,
        },
    )

    # Map status codes to user-friendly messages
    error_messages = {
        status.HTTP_401_UNAUTHORIZED: "Authentication failed",
        status.HTTP_400_BAD_REQUEST: "Invalid request",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "Internal server error",
    }

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": error_messages.get(exc.status_code, "Error"),
            "message": "An error occurred processing your request",
            "correlation_id": correlation_id,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Handle unexpected exceptions.

    Logs the full error but returns a generic message to avoid
    leaking sensitive information.
    """
    correlation_id = correlation_id_var.get()
    logger.exception(
        "Unexpected error processing request",
        extra={
            "correlation_id": correlation_id,
            "error_type": type(exc).__name__,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred",
            "correlation_id": correlation_id,
        },
    )


# ============================================================================
# HMAC Signature Verification - Story 2.1.2
# ============================================================================


def verify_github_signature(
    payload: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """
    Verify the HMAC-SHA256 signature of a GitHub webhook payload.

    Uses hmac.compare_digest() for constant-time comparison to prevent
    timing attacks.

    Args:
        payload: The raw request body bytes.
        signature_header: The X-Hub-Signature-256 header value.
        secret: The webhook secret configured in GitHub.

    Returns:
        True if the signature is valid, False otherwise.

    Security:
        - Uses constant-time comparison to prevent timing attacks
        - Handles missing/invalid header formats gracefully
        - Never exposes secret in logs or errors

    Example:
        >>> valid = verify_github_signature(body, signature, secret)
        >>> if not valid:
        ...     raise HTTPException(status_code=401)
    """
    if not signature_header:
        logger.warning("Missing X-Hub-Signature-256 header")
        return False

    # GitHub sends signature in format "sha256=<hex>"
    if not signature_header.startswith("sha256="):
        logger.warning("Invalid signature header format")
        return False

    # Extract hex digest from header
    expected_signature = signature_header[7:]  # Remove "sha256=" prefix

    # Compute HMAC-SHA256 of payload
    computed_signature = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(computed_signature, expected_signature)


async def get_raw_body(request: Request) -> bytes:
    """
    Get the raw request body for signature verification.

    The body must be read before any other parsing to ensure
    accurate signature verification.

    Args:
        request: The FastAPI request object.

    Returns:
        The raw request body bytes.
    """
    return await request.body()


def require_valid_signature(
    request: Request,
    body: bytes = Depends(get_raw_body),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> bytes:
    """
    Dependency that validates the GitHub webhook signature.

    This dependency should be used for any endpoint that receives
    GitHub webhooks. It returns the raw body bytes for further processing.

    Args:
        request: The FastAPI request object.
        body: The raw request body (injected via Depends).
        x_hub_signature_256: The signature header (injected via Header).

    Returns:
        The raw request body bytes if signature is valid.

    Raises:
        HTTPException: 401 Unauthorized if signature is invalid or missing.

    Example:
        @app.post("/webhooks/github")
        async def handle_webhook(body: bytes = Depends(require_valid_signature)):
            # body is guaranteed to have a valid signature
            ...
    """
    correlation_id = correlation_id_var.get()

    if not verify_github_signature(
        body, x_hub_signature_256, settings.github_webhook_secret
    ):
        logger.warning(
            "Invalid webhook signature",
            extra={
                "correlation_id": correlation_id,
                "error_type": "signature_verification_failed",
                "path": request.url.path,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    logger.debug(
        "Webhook signature verified",
        extra={
            "correlation_id": correlation_id,
            "path": request.url.path,
        },
    )

    return body


# ============================================================================
# Health Check - Story 2.1.1
# ============================================================================


@app.get("/health", tags=["Monitoring"])
async def health_check() -> dict[str, str]:
    """
    Health check endpoint for service monitoring.

    Returns a simple status indicating the service is running.
    Does not perform deep health checks (database, external services).

    Returns:
        A JSON object with status "healthy".
    """
    return {
        "status": "healthy",
        "service": "notifier-service",
        "version": "0.1.0",
    }


@app.get("/ready", tags=["Monitoring"])
async def readiness_check() -> dict[str, Any]:
    """
    Readiness check endpoint for service orchestration.

    Performs basic validation to ensure the service can handle requests.

    Returns:
        A JSON object with readiness status and checks.
    """
    checks = {
        "webhook_secret_configured": bool(settings.github_webhook_secret),
        "environment": settings.environment,
    }

    all_healthy = all(v for k, v in checks.items() if k != "environment")

    return {
        "ready": all_healthy,
        "checks": checks,
    }


# ============================================================================
# Webhook Endpoint - Stories 2.1.3, 2.1.4, 2.1.5
# ============================================================================


@app.post("/webhooks/github", status_code=status.HTTP_202_ACCEPTED)
async def handle_github_webhook(
    request: Request,
    body: bytes = Depends(require_valid_signature),
    x_github_event: str = Header(..., alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
) -> dict[str, Any]:
    """
    Handle incoming GitHub webhook events.

    This endpoint:
    1. Validates the HMAC signature (via dependency)
    2. Parses the event type from headers
    3. Validates and parses the payload
    4. Maps the event to a WorkItem
    5. Queues the item for processing

    Returns 202 Accepted immediately to meet GitHub's 10-second timeout.
    Processing continues asynchronously.

    Args:
        request: The FastAPI request object.
        body: The validated raw request body.
        x_github_event: The event type (issues, issue_comment, etc.).
        x_github_delivery: Unique delivery ID for this webhook.

    Returns:
        A JSON response acknowledging receipt of the webhook.

    Raises:
        HTTPException: 401 if signature invalid, 400 if payload malformed.
    """
    correlation_id = correlation_id_var.get()
    delivery_id = x_github_delivery or "unknown"

    logger.info(
        f"Received GitHub webhook: {x_github_event}",
        extra={
            "correlation_id": correlation_id,
            "delivery_id": delivery_id,
            "event_type": x_github_event,
            "sentinel_id": SENTINEL_ID,
        },
    )

    try:
        # Parse the JSON payload
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error(
                f"Invalid JSON payload: {e}",
                extra={
                    "correlation_id": correlation_id,
                    "delivery_id": delivery_id,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload",
            )

        # Handle ping event (webhook verification)
        if x_github_event == GitHubEventType.PING.value:
            logger.info(
                "Received ping event - webhook verified",
                extra={
                    "correlation_id": correlation_id,
                    "delivery_id": delivery_id,
                },
            )
            return {
                "status": "accepted",
                "event_type": "ping",
                "message": "Webhook verified successfully",
                "correlation_id": correlation_id,
            }

        # Parse the webhook payload into typed model
        event = parse_webhook_payload(x_github_event, payload)

        if event is None:
            logger.warning(
                f"Unsupported event type: {x_github_event}",
                extra={
                    "correlation_id": correlation_id,
                    "delivery_id": delivery_id,
                },
            )
            # Still acknowledge to avoid GitHub retries
            return {
                "status": "ignored",
                "event_type": x_github_event,
                "message": "Event type not supported",
                "correlation_id": correlation_id,
            }

        # Map event to WorkItem
        work_item = map_event_to_work_item(event)

        if work_item is None:
            logger.info(
                f"Event does not require processing",
                extra={
                    "correlation_id": correlation_id,
                    "delivery_id": delivery_id,
                    "event_type": x_github_event,
                },
            )
            return {
                "status": "ignored",
                "event_type": x_github_event,
                "message": "Event does not require processing",
                "correlation_id": correlation_id,
            }

        # Log the WorkItem creation
        logger.info(
            f"Mapped event to WorkItem: {work_item.id}",
            extra={
                "correlation_id": correlation_id,
                "delivery_id": delivery_id,
                "work_item_id": work_item.id,
                "target_repo": work_item.target_repo_slug,
                "task_type": work_item.task_type.value,
                "sentinel_id": SENTINEL_ID,
            },
        )

        # TODO: Queue the WorkItem for processing
        # This would integrate with GitHubQueue or a message queue
        # For now, we just acknowledge receipt
        # await queue.add_to_queue(work_item)

        return {
            "status": "accepted",
            "event_type": x_github_event,
            "work_item_id": str(work_item.id),
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            f"Error processing webhook: {e}",
            extra={
                "correlation_id": correlation_id,
                "delivery_id": delivery_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ============================================================================
# Event to WorkItem Mapping - Story 2.1.4
# ============================================================================


def map_event_to_work_item(
    event: GitHubIssuesEvent | GitHubIssueCommentEvent,
) -> WorkItem | None:
    """
    Map a GitHub webhook event to a WorkItem for the execution queue.

    This function extracts relevant information from the event and
    creates a standardized WorkItem that can be processed by the
    orchestration system.

    Args:
        event: The parsed GitHub webhook event (issues or issue_comment).

    Returns:
        A WorkItem if the event should be processed, None otherwise.

    Filtering Logic:
        - Issues with orchestration-related labels are processed
        - Issue comments from specific users or with specific patterns
          may trigger processing
        - Other events are ignored

    Example:
        >>> event = GitHubIssuesEvent(...)
        >>> work_item = map_event_to_work_item(event)
        >>> if work_item:
        ...     await queue.add_to_queue(work_item)
    """
    # Determine if this event should trigger processing
    if not should_process_event(event):
        return None

    if isinstance(event, GitHubIssuesEvent):
        return _map_issues_event_to_work_item(event)
    elif isinstance(event, GitHubIssueCommentEvent):
        return _map_issue_comment_event_to_work_item(event)

    return None


def should_process_event(
    event: GitHubIssuesEvent | GitHubIssueCommentEvent,
) -> bool:
    """
    Determine if an event should trigger processing.

    Filtering criteria:
    - Issues with orchestration-related labels (agent:*, orchestration:*, implementation:*)
    - Issue comments containing specific trigger patterns
    - Events in open state

    Args:
        event: The parsed GitHub webhook event.

    Returns:
        True if the event should be processed, False otherwise.
    """
    # Get labels from the issue
    labels = [label.name.lower() for label in event.issue.labels]

    # Check for orchestration-related labels
    orchestration_prefixes = [
        "agent:",
        "orchestration:",
        "implementation:",
        "type:",
        "task:",
    ]

    has_orchestration_label = any(
        any(label.startswith(prefix) for prefix in orchestration_prefixes)
        for label in labels
    )

    if has_orchestration_label:
        return True

    # For issue comments, check if the comment body contains trigger patterns
    if isinstance(event, GitHubIssueCommentEvent):
        if event.comment.body:
            trigger_patterns = [
                "/orchestrate",
                "/implement",
                "@orchestrator",
                "@agent",
            ]
            if any(
                pattern in event.comment.body.lower() for pattern in trigger_patterns
            ):
                return True

    # Check for label changes that add orchestration labels
    if isinstance(event, GitHubIssuesEvent):
        if event.action == IssueAction.LABELED and event.label:
            label_name = event.label.name.lower()
            if any(label_name.startswith(prefix) for prefix in orchestration_prefixes):
                return True

    return has_orchestration_label


def _map_issues_event_to_work_item(event: GitHubIssuesEvent) -> WorkItem:
    """
    Map an issues event to a WorkItem.

    Args:
        event: The GitHub issues event.

    Returns:
        A WorkItem ready for queue processing.
    """
    # Determine task type from labels
    task_type = _determine_task_type(event.issue.labels)

    # Build context body from issue
    context_body = _build_context_body(
        title=event.issue.title,
        body=event.issue.body,
        action=event.action.value,
        event_type="issues",
    )

    # Build metadata
    metadata = {
        "action": event.action.value,
        "event_type": "issues",
        "issue_node_id": event.issue.node_id,
        "issue_number": event.issue.number,
        "labels": [label.name for label in event.issue.labels],
        "sender": event.sender.login,
        "repository_node_id": event.repository.node_id,
        "created_at": event.issue.created_at,
        "updated_at": event.issue.updated_at,
    }

    # Add label info if available
    if event.label:
        metadata["added_label"] = event.label.name

    return WorkItem(
        id=event.issue.number,
        source_url=event.issue.html_url,
        context_body=context_body,
        target_repo_slug=event.repository.full_name,
        task_type=task_type,
        status=WorkItemStatus.QUEUED,
        metadata=metadata,
    )


def _map_issue_comment_event_to_work_item(event: GitHubIssueCommentEvent) -> WorkItem:
    """
    Map an issue_comment event to a WorkItem.

    Args:
        event: The GitHub issue_comment event.

    Returns:
        A WorkItem ready for queue processing.
    """
    # Determine task type from labels and comment content
    task_type = _determine_task_type(event.issue.labels)

    # Override with PLAN if comment contains /plan
    if event.comment.body and "/plan" in event.comment.body.lower():
        task_type = TaskType.PLAN

    # Build context body including comment
    context_body = _build_context_body(
        title=event.issue.title,
        body=event.issue.body,
        action=event.action.value,
        event_type="issue_comment",
        comment_body=event.comment.body,
        comment_author=event.comment.user.login,
    )

    # Build metadata
    metadata = {
        "action": event.action.value,
        "event_type": "issue_comment",
        "issue_node_id": event.issue.node_id,
        "issue_number": event.issue.number,
        "comment_id": event.comment.id,
        "comment_node_id": event.comment.node_id,
        "labels": [label.name for label in event.issue.labels],
        "sender": event.sender.login,
        "repository_node_id": event.repository.node_id,
        "created_at": event.issue.created_at,
        "updated_at": event.issue.updated_at,
    }

    return WorkItem(
        id=event.issue.number,
        source_url=event.issue.html_url,
        context_body=context_body,
        target_repo_slug=event.repository.full_name,
        task_type=task_type,
        status=WorkItemStatus.QUEUED,
        metadata=metadata,
    )


def _determine_task_type(labels: list[Any]) -> TaskType:
    """
    Determine the task type from issue labels.

    Args:
        labels: List of GitHub label objects.

    Returns:
        The determined TaskType (PLAN or IMPLEMENT).
    """
    label_names = [label.name.lower() for label in labels]

    # Check for plan-related labels
    plan_indicators = [
        "type:plan",
        "task:plan",
        "orchestration:plan",
        "plan",
    ]

    for label in label_names:
        if any(indicator in label for indicator in plan_indicators):
            return TaskType.PLAN

    return TaskType.IMPLEMENT


def _build_context_body(
    title: str,
    body: str | None,
    action: str,
    event_type: str,
    comment_body: str | None = None,
    comment_author: str | None = None,
) -> str:
    """
    Build a context body for the WorkItem from event data.

    Args:
        title: Issue title.
        body: Issue body.
        action: Event action.
        event_type: Type of GitHub event.
        comment_body: Optional comment body.
        comment_author: Optional comment author.

    Returns:
        A formatted context string for the WorkItem.
    """
    parts = [f"# {title}", ""]

    if body:
        parts.append("## Issue Description")
        parts.append(body)
        parts.append("")

    parts.append("## Event Context")
    parts.append(f"- Event Type: {event_type}")
    parts.append(f"- Action: {action}")
    parts.append("")

    if comment_body:
        parts.append(f"## Comment by @{comment_author}")
        parts.append(comment_body)
        parts.append("")

    return "\n".join(parts)


# ============================================================================
# Middleware for Request Correlation
# ============================================================================


@app.middleware("http")
async def add_correlation_id(request: Request, call_next: Any) -> Any:
    """
    Middleware to add correlation IDs to requests for tracing.

    Generates or extracts a correlation ID for each request and
    makes it available via context variable for logging.
    """
    # Try to get correlation ID from header, or generate new one
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    correlation_id_var.set(correlation_id)

    response = await call_next(request)

    # Add correlation ID to response headers
    response.headers["X-Correlation-ID"] = correlation_id

    return response
